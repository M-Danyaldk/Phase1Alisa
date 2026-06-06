import logging
from datetime import UTC, datetime
from urllib.parse import quote

from fastapi import HTTPException

from .auth_user import authenticated_user, bearer_token
from .student_auth_service import StudentAuthService
from .supabase_client import SupabaseClient, SupabaseClientError

logger = logging.getLogger(__name__)

CHILD_ACCESS_MODE = 'child'
CHILD_BILLING_BLOCKED_MESSAGE = 'Hi {name}! There is something your parent needs to take care of. Go find them and let them know — they will have you back learning in no time!'


async def require_parent_access(authorization: str, access_mode: str = '') -> dict:
    if access_mode.strip().lower() == CHILD_ACCESS_MODE:
        raise HTTPException(status_code=403, detail='This area is for parents only.')
    user = await authenticated_user(bearer_token(authorization))
    profile = await _profile_for_user(user['id'])
    role = profile.get('role') or 'parent'
    if role not in {'parent', 'admin', 'super_admin'}:
        raise HTTPException(status_code=403, detail='This area is for parents only.')
    user['role'] = role
    user['profile'] = profile
    return user


async def require_child_access(authorization: str, child_id: str | None, access_mode: str = '') -> dict:
    if not child_id:
        raise HTTPException(status_code=400, detail='Child profile is required for student learning access.')
    if access_mode.strip().lower() == CHILD_ACCESS_MODE:
        user = await authenticated_user(bearer_token(authorization))
        child = await ensure_child_for_parent(user['id'], child_id)
        await ensure_child_billing_access(child_id, child_name=child.get('name'))
        return user

    session = await StudentAuthService().session_from_token(bearer_token(authorization))
    if session['child_id'] != child_id:
        raise HTTPException(status_code=403, detail='This student session cannot access another child profile.')
    child = await ensure_child_for_parent(session['parent_id'], child_id)
    await ensure_child_billing_access(child_id, child_name=child.get('name'))
    return {'id': session['parent_id'], 'child_id': session['child_id'], 'role': 'child'}


async def require_student_child_access(authorization: str, child_id: str | None) -> dict:
    if not child_id:
        raise HTTPException(status_code=400, detail='Child profile is required for student learning access.')
    session = await StudentAuthService().session_from_token(bearer_token(authorization))
    if session['child_id'] != child_id:
        raise HTTPException(status_code=403, detail='This student session cannot access another child profile.')
    child = await ensure_child_for_parent(session['parent_id'], child_id)
    await ensure_child_billing_access(child_id, child_name=child.get('name'))
    return {'id': session['parent_id'], 'child_id': session['child_id'], 'role': 'child', 'child': child, 'session': session}


async def ensure_child_for_parent(parent_id: str, child_id: str) -> dict:
    try:
        records = await SupabaseClient().select(
            'child_profiles',
            f'id=eq.{quote(child_id)}&parent_id=eq.{quote(parent_id)}&status=neq.inactive&limit=1',
        )
    except SupabaseClientError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    if not records:
        raise HTTPException(status_code=403, detail='Your learning access is currently paused. Please ask your parent to check the account.')
    return records[0]


async def ensure_child_billing_access(child_id: str, child_name: str | None = None) -> None:
    state = await child_billing_access_state(child_id, child_name=child_name)
    if not state['access_allowed']:
        raise HTTPException(status_code=403, detail=state['child_blocked_message'])


async def child_billing_access_state(child_id: str, child_name: str | None = None) -> dict:
    try:
        records = await SupabaseClient().select('child_access', f'child_id=eq.{quote(child_id)}&limit=1')
    except SupabaseClientError as exc:
        logger.warning('Could not verify child billing access for child %s: %s', child_id, exc)
        return _billing_state(access_allowed=False, child_name=child_name, blocked_reason='billing_access_unverified')
    if not records:
        return _billing_state(access_allowed=False, child_name=child_name, blocked_reason='no_billing_access')
    access = records[0]
    status = access.get('access_status')
    plan_type = access.get('plan_type')
    voice_allowed = status == 'active' and plan_type == 'voice'
    blocked_reason = None
    if status in {'inactive', 'past_due'}:
        blocked_reason = status
    elif status == 'trial' and _is_past(access.get('trial_ends_at')):
        blocked_reason = 'trial_expired'
    elif status == 'active' and access.get('current_period_ends_at') and _is_past(access.get('current_period_ends_at')):
        blocked_reason = 'subscription_expired'
    elif access.get('grace_period_ends_at') and _is_past(access.get('grace_period_ends_at')):
        blocked_reason = 'grace_expired'
    elif status not in {'trial', 'active'}:
        blocked_reason = 'no_billing_access'
    return _billing_state(
        access_allowed=blocked_reason is None,
        child_name=child_name,
        blocked_reason=blocked_reason,
        status=status,
        plan_type=plan_type,
        voice_allowed=voice_allowed if blocked_reason is None else False,
    )


async def _profile_for_user(user_id: str) -> dict:
    try:
        records = await SupabaseClient().select('profiles', f'id=eq.{quote(user_id)}&limit=1')
    except SupabaseClientError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    if not records:
        raise HTTPException(status_code=403, detail='Profile access is required.')
    return records[0]


def _billing_state(
    access_allowed: bool,
    child_name: str | None = None,
    blocked_reason: str | None = None,
    status: str | None = None,
    plan_type: str | None = None,
    voice_allowed: bool = False,
) -> dict:
    name = child_name or 'there'
    return {
        'access_allowed': access_allowed,
        'billing_status': status,
        'blocked_reason': blocked_reason,
        'voice_allowed': bool(access_allowed and voice_allowed),
        'plan_type': plan_type,
        'child_blocked_message': CHILD_BILLING_BLOCKED_MESSAGE.format(name=name),
    }


def _is_past(value: str | None) -> bool:
    if not value:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return False
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC) <= datetime.now(UTC)
