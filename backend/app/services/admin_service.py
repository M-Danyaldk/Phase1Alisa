import asyncio
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

from fastapi import HTTPException

from ..schemas.admin import (
    AdminInviteRequest,
    AdminPermissionsUpdateRequest,
    AdminSettingUpdateRequest,
    AdminSubscriptionUpdateRequest,
    AdminUserStatusUpdateRequest,
)
from .supabase_client import SupabaseClient, SupabaseClientError


ADMIN_ROLES = {'admin', 'super_admin'}
ALL_ADMIN_PERMISSIONS = {
    'manage_users',
    'manage_subscriptions',
    'manage_courses',
    'view_analytics',
    'refund_payments',
    'manage_admins',
    'manage_settings',
}
DEFAULT_ROLE_PERMISSIONS = {
    'admin': {'manage_users', 'manage_subscriptions', 'view_analytics'},
    'super_admin': ALL_ADMIN_PERMISSIONS,
}


class AdminService:
    def __init__(self) -> None:
        self.supabase = SupabaseClient()

    async def require_admin(self, authorization: str, permission: str | None = None) -> dict:
        token = self._bearer_token(authorization)
        try:
            user = await self.supabase.get_user(token)
            records = await self.supabase.select('profiles', f'id=eq.{quote(user["id"])}&limit=1')
        except SupabaseClientError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        if not records:
            raise HTTPException(status_code=403, detail='Admin profile not found.')
        profile = self._normalize_profile(records[0])
        if profile.get('role') not in ADMIN_ROLES:
            raise HTTPException(status_code=403, detail='Admin permission is required.')
        if profile.get('status') != 'active':
            raise HTTPException(status_code=403, detail='This admin account is not active.')
        if permission and permission not in self._permissions(profile):
            raise HTTPException(status_code=403, detail='This admin account does not have the required permission.')
        return profile

    async def overview(self, admin: dict) -> dict:
        students, assessments, llm_events, users, subscriptions, audit_logs = await asyncio.gather(
            self._safe_select('students', 'order=created_at.desc&limit=10'),
            self._safe_select('assessment_results', 'order=created_at.desc&limit=10'),
            self._safe_select('llm_events', 'order=created_at.desc&limit=20'),
            self._safe_select('profiles', 'order=created_at.desc&limit=500'),
            self._safe_select('child_access', 'order=created_at.desc&limit=500'),
            self.audit_logs(admin, limit=10),
        )
        return {
            'totals': {
                'users': len(users),
                'admins': len([user for user in users if user.get('role') in ADMIN_ROLES]),
                'parents': len([user for user in users if user.get('role') == 'parent']),
                'students': len(students),
                'active_subscriptions': len([row for row in subscriptions if row.get('access_status') == 'active']),
                'past_due_subscriptions': len([row for row in subscriptions if row.get('access_status') == 'past_due']),
            },
            'students': students,
            'assessments': assessments,
            'llm_events': llm_events,
            'audit_logs': audit_logs,
        }

    async def users(self, admin: dict, search: str = '', limit: int = 100) -> list[dict]:
        query = f'order=created_at.desc&limit={limit}'
        records = await self._safe_select('profiles', query)
        normalized = [self._normalize_profile(record) for record in records]
        if search.strip():
            term = search.strip().lower()
            normalized = [
                record for record in normalized
                if term in (record.get('email') or '').lower() or term in (record.get('full_name') or '').lower()
            ]
        return normalized

    async def update_user_status(self, admin: dict, user_id: str, payload: AdminUserStatusUpdateRequest) -> dict:
        if user_id == admin.get('id'):
            raise HTTPException(status_code=403, detail='Admins cannot change their own account status.')
        target = await self._profile(user_id)
        if target.get('role') == 'super_admin' and admin.get('role') != 'super_admin':
            raise HTTPException(status_code=403, detail='Only a super admin can change a super admin account.')
        updated = await self._update_profile(user_id, {
            'status': payload.status,
            'updated_at': datetime.now(UTC).isoformat(),
        })
        await self.log_action(admin, 'user_status_updated', 'profile', user_id, {
            'status': payload.status,
            'reason': payload.reason,
        })
        return self._normalize_profile(updated)

    async def subscriptions(self, admin: dict, limit: int = 100) -> list[dict]:
        access_rows = await self._safe_select('child_access', f'order=created_at.desc&limit={limit}')
        children = await self._safe_select('child_profiles', 'order=created_at.desc&limit=500')
        children_by_id = {child.get('id'): child for child in children}
        records = []
        for row in access_rows:
            child = children_by_id.get(row.get('child_id'), {})
            records.append({
                **self._subscription_admin_view(row),
                'child_name': child.get('name', 'Student'),
                'grade_level': child.get('grade_level'),
            })
        return records

    async def update_subscription(self, admin: dict, subscription_id: str, payload: AdminSubscriptionUpdateRequest) -> dict:
        now = datetime.now(UTC)
        update = {
            'access_status': payload.access_status,
            'plan_name': payload.plan_name.strip() or 'Phase 1 MVP',
            'updated_at': now.isoformat(),
        }
        if payload.access_status == 'trial':
            update['trial_ends_at'] = (now + timedelta(days=7)).isoformat()
            update['current_period_ends_at'] = None
        elif payload.access_status == 'active':
            update['trial_ends_at'] = None
            update['current_period_ends_at'] = (now + timedelta(days=30)).isoformat()
        else:
            update['trial_ends_at'] = None
            update['current_period_ends_at'] = None
        try:
            records = await self.supabase.update('child_access', {'id': f'eq.{subscription_id}'}, update)
        except SupabaseClientError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        if not records:
            raise HTTPException(status_code=404, detail='Subscription record not found.')
        await self.log_action(admin, 'subscription_updated', 'child_access', subscription_id, {
            'access_status': payload.access_status,
            'plan_name': payload.plan_name,
            'reason': payload.reason,
        })
        return records[0]

    async def reports(self, admin: dict) -> dict:
        learning_activity, assessments, llm_events, audit_logs = await asyncio.gather(
            self.learning_activity(),
            self._safe_select('assessment_results', 'order=created_at.desc&limit=100'),
            self._safe_select('llm_events', 'order=created_at.desc&limit=100'),
            self.audit_logs(admin, limit=50),
        )
        return {
            'learning_activity': learning_activity,
            'assessments': assessments,
            'llm_events': llm_events,
            'audit_logs': audit_logs,
        }

    async def learning_activity(self) -> list[dict]:
        children, assessments, sessions, threads = await asyncio.gather(
            self._safe_select('child_profiles', 'order=created_at.desc&limit=500'),
            self._safe_select('assessment_results', 'order=created_at.desc&limit=500'),
            self._safe_select('learning_sessions', 'order=created_at.desc&limit=500'),
            self._safe_select('chat_threads', 'order=updated_at.desc&limit=500'),
        )

        latest_assessment_by_child: dict[str, dict] = {}
        latest_session_by_child: dict[str, dict] = {}
        latest_thread_by_child: dict[str, dict] = {}
        assessments_by_name: dict[str, dict] = {}
        assessment_count_by_child: dict[str, int] = {}
        assessment_count_by_name: dict[str, int] = {}
        child_ids: set[str] = {str(child.get('id')) for child in children if child.get('id')}
        child_names: set[str] = {(child.get('name') or '').strip().lower() for child in children if child.get('name')}

        for assessment in assessments:
            child_id = assessment.get('child_id')
            if child_id and child_id not in latest_assessment_by_child:
                latest_assessment_by_child[child_id] = assessment
            if child_id:
                assessment_count_by_child[child_id] = assessment_count_by_child.get(child_id, 0) + 1
            student_name = (assessment.get('student_name') or '').strip().lower()
            if student_name and student_name not in assessments_by_name:
                assessments_by_name[student_name] = assessment
            if student_name:
                assessment_count_by_name[student_name] = assessment_count_by_name.get(student_name, 0) + 1

        for session in sessions:
            child_id = session.get('child_id')
            if child_id and child_id not in latest_session_by_child:
                latest_session_by_child[child_id] = session

        for thread in threads:
            child_id = thread.get('child_id')
            if child_id and child_id not in latest_thread_by_child:
                latest_thread_by_child[child_id] = thread

        rows = []
        for child in children:
            child_id = child.get('id')
            latest_assessment = latest_assessment_by_child.get(child_id) or assessments_by_name.get((child.get('name') or '').strip().lower())
            latest_session = latest_session_by_child.get(child_id)
            latest_thread = latest_thread_by_child.get(child_id)
            latest_activity_at = self._latest_date([
                latest_assessment.get('created_at') if latest_assessment else None,
                latest_session.get('created_at') if latest_session else None,
                latest_thread.get('updated_at') if latest_thread else None,
                child.get('updated_at'),
                child.get('created_at'),
            ])
            subject = (
                (latest_assessment or {}).get('subject')
                or (latest_session or {}).get('subject')
                or (latest_thread or {}).get('subject')
                or self._first_subject(child.get('subjects'))
                or 'Not started'
            )
            rows.append({
                'child_id': child_id,
                'student_name': child.get('name') or 'Student',
                'grade_level': child.get('grade_level') or 'Not set',
                'status': child.get('status') or 'active',
                'subject': subject,
                'latest_activity_at': latest_activity_at,
                'latest_activity_type': self._activity_type(latest_assessment, latest_session, latest_thread),
                'latest_level': (latest_assessment or {}).get('estimated_level'),
                'assessment_count': assessment_count_by_child.get(child_id, 0) or assessment_count_by_name.get((child.get('name') or '').strip().lower(), 0),
            })
        for name, assessment in assessments_by_name.items():
            child_id = assessment.get('child_id')
            if (child_id and str(child_id) in child_ids) or name in child_names:
                continue
            enrolled_grade = assessment.get('enrolled_grade')
            rows.append({
                'child_id': child_id or f'assessment:{assessment.get("id") or name}',
                'student_name': assessment.get('student_name') or 'Student',
                'grade_level': f'Grade {enrolled_grade}' if enrolled_grade else 'Not set',
                'status': 'assessment_only',
                'subject': assessment.get('subject') or 'Assessment',
                'latest_activity_at': assessment.get('created_at'),
                'latest_activity_type': 'Assessment Saved',
                'latest_level': assessment.get('estimated_level'),
                'assessment_count': assessment_count_by_name.get(name, 1),
            })
        return rows

    async def settings(self, admin: dict) -> list[dict]:
        return await self._safe_select('app_settings', 'order=key.asc&limit=100')

    async def update_setting(self, admin: dict, key: str, payload: AdminSettingUpdateRequest) -> dict:
        setting = {
            'key': key,
            'value': payload.value,
            'updated_by': admin['id'],
            'updated_at': datetime.now(UTC).isoformat(),
        }
        try:
            records = await self.supabase.upsert('app_settings', setting, 'key')
        except SupabaseClientError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        await self.log_action(admin, 'setting_updated', 'app_settings', key, {
            'value': payload.value,
            'reason': payload.reason,
        })
        return records[0] if records else setting

    async def audit_logs(self, admin: dict, limit: int = 100) -> list[dict]:
        return await self._safe_select('admin_audit_logs', f'order=created_at.desc&limit={limit}')

    async def invite_admin(self, admin: dict, payload: AdminInviteRequest) -> dict:
        if payload.role == 'super_admin' and admin.get('role') != 'super_admin':
            raise HTTPException(status_code=403, detail='Only a super admin can create another super admin.')
        permissions = self._clean_permissions(payload.permissions)
        try:
            auth_user = await self.supabase.create_auth_user(
                email=str(payload.email).lower(),
                password=payload.temporary_password,
                metadata={
                    'full_name': payload.full_name.strip(),
                    'role': payload.role,
                    'admin_permissions': permissions,
                },
            )
            user_id = auth_user['id']
            records = await self.supabase.upsert('profiles', {
                'id': user_id,
                'full_name': payload.full_name.strip(),
                'email': str(payload.email).lower(),
                'role': payload.role,
                'status': 'active',
                'admin_permissions': permissions,
                'admin_2fa_enabled': False,
                'updated_at': datetime.now(UTC).isoformat(),
            }, 'id')
        except SupabaseClientError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        profile = self._normalize_profile(records[0] if records else {'id': user_id, **payload.model_dump()})
        await self.log_action(admin, 'admin_created', 'profile', profile['id'], {
            'email': profile.get('email'),
            'role': profile.get('role'),
            'permissions': permissions,
        })
        return profile

    async def update_admin_permissions(self, admin: dict, user_id: str, payload: AdminPermissionsUpdateRequest) -> dict:
        target = await self._profile(user_id)
        if target.get('role') == 'super_admin' and admin.get('role') != 'super_admin':
            raise HTTPException(status_code=403, detail='Only a super admin can update a super admin.')
        permissions = self._clean_permissions(payload.permissions)
        updated = await self._update_profile(user_id, {
            'role': payload.role,
            'admin_permissions': permissions,
            'updated_at': datetime.now(UTC).isoformat(),
        })
        await self.log_action(admin, 'admin_permissions_updated', 'profile', user_id, {
            'role': payload.role,
            'permissions': permissions,
            'reason': payload.reason,
        })
        return self._normalize_profile(updated)

    async def log_action(self, admin: dict, action: str, target_type: str, target_id: str | None, metadata: dict | None = None) -> None:
        try:
            await self.supabase.insert('admin_audit_logs', {
                'admin_user_id': admin['id'],
                'action': action,
                'target_type': target_type,
                'target_id': target_id,
                'metadata': metadata or {},
            })
        except SupabaseClientError:
            return

    async def _profile(self, user_id: str) -> dict:
        records = await self._safe_select('profiles', f'id=eq.{quote(user_id)}&limit=1')
        if not records:
            raise HTTPException(status_code=404, detail='User profile not found.')
        return self._normalize_profile(records[0])

    async def _update_profile(self, user_id: str, payload: dict) -> dict:
        try:
            records = await self.supabase.update('profiles', {'id': f'eq.{user_id}'}, payload)
        except SupabaseClientError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        if not records:
            raise HTTPException(status_code=404, detail='User profile not found.')
        return records[0]

    async def _safe_select(self, table: str, query: str) -> list[dict]:
        try:
            return await self.supabase.select(table, query)
        except SupabaseClientError:
            return []

    def _bearer_token(self, authorization: str) -> str:
        if not authorization.lower().startswith('bearer '):
            raise HTTPException(status_code=401, detail='Authorization token is required.')
        token = authorization.split(' ', 1)[1].strip()
        if not token:
            raise HTTPException(status_code=401, detail='Authorization token is required.')
        return token

    def _normalize_profile(self, profile: dict) -> dict:
        normalized = dict(profile)
        normalized['status'] = normalized.get('status') or 'active'
        normalized['admin_permissions'] = self._clean_permissions(normalized.get('admin_permissions') or [])
        normalized['admin_2fa_enabled'] = bool(normalized.get('admin_2fa_enabled'))
        return normalized

    def _permissions(self, profile: dict) -> set[str]:
        role_permissions = DEFAULT_ROLE_PERMISSIONS.get(profile.get('role'), set())
        explicit = set(self._clean_permissions(profile.get('admin_permissions') or []))
        return role_permissions | explicit

    def _clean_permissions(self, permissions: object) -> list[str]:
        if not isinstance(permissions, list):
            return []
        return sorted({permission for permission in permissions if permission in ALL_ADMIN_PERMISSIONS})

    def _subscription_admin_view(self, row: dict) -> dict:
        hidden = {
            'stripe_customer_id',
            'stripe_subscription_id',
            'stripe_price_id',
            'latest_invoice_id',
            'latest_payment_intent_id',
            'stripe_coupon_id',
            'non_refundable_policy_accepted_at',
            'non_refundable_policy_version',
        }
        return {key: value for key, value in row.items() if key not in hidden}

    def _latest_date(self, values: list[str | None]) -> str | None:
        dates = []
        for value in values:
            if not value:
                continue
            try:
                dates.append(datetime.fromisoformat(value.replace('Z', '+00:00')))
            except ValueError:
                continue
        if not dates:
            return None
        return max(dates).isoformat()

    def _first_subject(self, subjects: object) -> str | None:
        if isinstance(subjects, list) and subjects:
            return str(subjects[0])
        return None

    def _activity_type(self, assessment: dict | None, session: dict | None, thread: dict | None) -> str:
        if assessment:
            return 'Assessment Saved'
        if session:
            return 'Learning Session'
        if thread:
            return 'Chat Activity'
        return 'No Activity Yet'
