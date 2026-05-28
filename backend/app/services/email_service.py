import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from html import escape
from typing import Any
from urllib.parse import quote

import httpx

from ..config import get_settings
from .supabase_client import SupabaseClient, SupabaseClientError

logger = logging.getLogger(__name__)

EMAIL_TRIGGER_TYPES = {
    'signup_welcome',
    'trial_day_5',
    'trial_day_7',
    'trial_expired_day_8',
    'payment_success',
    'payment_failed',
    'annual_renewal_reminder',
    'weekly_progress',
}


@dataclass(frozen=True)
class EmailContent:
    subject: str
    text: str
    html: str


class EmailService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.supabase = SupabaseClient()

    async def generate_due_events(self) -> dict:
        summary = {
            'trial_events_created': 0,
            'annual_renewal_events_created': 0,
            'weekly_progress_events_created': 0,
        }
        if not self.supabase.configured():
            return summary

        summary['trial_events_created'] = await self.generate_due_trial_events()
        summary['annual_renewal_events_created'] = await self.generate_due_annual_renewal_events()
        summary['weekly_progress_events_created'] = await self.generate_due_weekly_progress_events()
        return summary

    async def create_event(
        self,
        *,
        trigger_type: str,
        recipient_email: str,
        parent_id: str | None = None,
        child_id: str | None = None,
        scheduled_send_at: str | None = None,
        metadata: dict[str, Any] | None = None,
        template_key: str | None = None,
    ) -> dict:
        self._validate_trigger(trigger_type)
        normalized_email = recipient_email.strip().lower()
        event_key = self._event_key(trigger_type, parent_id, child_id, normalized_email, scheduled_send_at, metadata or {})
        event_metadata = {**(metadata or {}), 'event_key': event_key}

        if not self.supabase.configured():
            logger.info('Supabase is not configured; email event %s for %s was skipped.', trigger_type, normalized_email)
            return {
                'status': 'skipped',
                'trigger_type': trigger_type,
                'recipient_email': normalized_email,
                'metadata': event_metadata,
            }

        existing = await self._find_existing_event(
            trigger_type=trigger_type,
            recipient_email=normalized_email,
            parent_id=parent_id,
            child_id=child_id,
            event_key=event_key,
        )
        if existing:
            return existing

        payload = {
            'parent_id': parent_id,
            'child_id': child_id,
            'trigger_type': trigger_type,
            'recipient_email': normalized_email,
            'template_key': template_key or trigger_type,
            'status': 'pending',
            'provider': 'resend',
            'scheduled_send_at': scheduled_send_at,
            'metadata': event_metadata,
        }
        records = await self.supabase.insert('email_events', payload)
        return records[0] if records else payload

    async def queue_signup_welcome(self, *, parent_id: str, recipient_email: str, scheduled_send_at: str | None = None) -> dict:
        return await self.create_event(
            trigger_type='signup_welcome',
            parent_id=parent_id,
            recipient_email=recipient_email,
            scheduled_send_at=scheduled_send_at,
        )

    async def queue_trial_day_5(self, *, parent_id: str, recipient_email: str, scheduled_send_at: str, metadata: dict[str, Any] | None = None) -> dict:
        return await self.create_event(
            trigger_type='trial_day_5',
            parent_id=parent_id,
            recipient_email=recipient_email,
            scheduled_send_at=scheduled_send_at,
            metadata=metadata,
        )

    async def queue_trial_day_7(self, *, parent_id: str, recipient_email: str, scheduled_send_at: str, metadata: dict[str, Any] | None = None) -> dict:
        return await self.create_event(
            trigger_type='trial_day_7',
            parent_id=parent_id,
            recipient_email=recipient_email,
            scheduled_send_at=scheduled_send_at,
            metadata=metadata,
        )

    async def queue_trial_expired_day_8(self, *, parent_id: str, recipient_email: str, scheduled_send_at: str, metadata: dict[str, Any] | None = None) -> dict:
        return await self.create_event(
            trigger_type='trial_expired_day_8',
            parent_id=parent_id,
            recipient_email=recipient_email,
            scheduled_send_at=scheduled_send_at,
            metadata=metadata,
        )

    async def queue_payment_success(self, *, parent_id: str, recipient_email: str, child_id: str | None = None, metadata: dict[str, Any] | None = None) -> dict:
        return await self.create_event(
            trigger_type='payment_success',
            parent_id=parent_id,
            child_id=child_id,
            recipient_email=recipient_email,
            metadata=metadata,
        )

    async def queue_payment_failed(self, *, parent_id: str, recipient_email: str, child_id: str | None = None, metadata: dict[str, Any] | None = None) -> dict:
        return await self.create_event(
            trigger_type='payment_failed',
            parent_id=parent_id,
            child_id=child_id,
            recipient_email=recipient_email,
            metadata=metadata,
        )

    async def queue_annual_renewal_reminder(
        self,
        *,
        parent_id: str,
        recipient_email: str,
        child_id: str | None = None,
        scheduled_send_at: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict:
        return await self.create_event(
            trigger_type='annual_renewal_reminder',
            parent_id=parent_id,
            child_id=child_id,
            recipient_email=recipient_email,
            scheduled_send_at=scheduled_send_at,
            metadata=metadata,
        )

    async def queue_weekly_progress(
        self,
        *,
        parent_id: str,
        child_id: str,
        recipient_email: str,
        scheduled_send_at: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict:
        return await self.create_event(
            trigger_type='weekly_progress',
            parent_id=parent_id,
            child_id=child_id,
            recipient_email=recipient_email,
            scheduled_send_at=scheduled_send_at,
            metadata=metadata,
        )

    async def send_signup_verification_code(self, *, recipient_email: str, code: str, expires_in_minutes: int) -> str | None:
        if not self.settings.resend_api_key.strip():
            raise RuntimeError('RESEND_API_KEY is not configured.')
        content = self._signup_verification_code(code, expires_in_minutes)
        return await self._send_resend_email(recipient_email.strip().lower(), content)

    async def send_password_reset_code(self, *, recipient_email: str, code: str, expires_in_minutes: int) -> str | None:
        if not self.settings.resend_api_key.strip():
            raise RuntimeError('RESEND_API_KEY is not configured.')
        content = self._password_reset_code(code, expires_in_minutes)
        return await self._send_resend_email(recipient_email.strip().lower(), content)

    async def process_due_events(self, limit: int = 25) -> dict:
        if not self.supabase.configured():
            return {'processed': 0, 'sent': 0, 'failed': 0, 'skipped': 0, 'message': 'Supabase is not configured.'}

        generated = await self.generate_due_events()
        now = datetime.now(UTC).isoformat()
        safe_limit = max(1, min(limit, 100))
        query = (
            'status=eq.pending'
            f'&or=(scheduled_send_at.is.null,scheduled_send_at.lte.{quote(now)})'
            '&order=scheduled_send_at.asc.nullsfirst'
            f'&limit={safe_limit}'
        )
        events = await self.supabase.select('email_events', query)
        summary = {'processed': 0, 'sent': 0, 'failed': 0, 'skipped': 0, **generated}

        for event in events:
            summary['processed'] += 1
            result = await self.send_event(event)
            status = result.get('status')
            if status in ('sent', 'failed', 'skipped'):
                summary[status] += 1

        return summary

    async def generate_due_trial_events(self) -> int:
        now = datetime.now(UTC)
        try:
            rows = await self.supabase.select('parent_trial_history', 'order=trial_started_at.desc&limit=500')
        except SupabaseClientError as exc:
            logger.warning('Could not load trial history for email events: %s', exc)
            return 0

        created_count = 0
        for row in rows:
            trial_start = self._parse_datetime(row.get('trial_started_at'))
            if not trial_start:
                continue
            parent_id = row.get('parent_id')
            recipient_email = row.get('email')
            if not parent_id or not recipient_email:
                continue
            child_id = row.get('child_id')
            metadata = {
                'trial_started_at': trial_start.isoformat(),
                'trial_ends_at': row.get('trial_ends_at'),
                'child_id': child_id,
            }
            for day_offset, queue_method, trigger_type in [
                (5, self.queue_trial_day_5, 'trial_day_5'),
                (7, self.queue_trial_day_7, 'trial_day_7'),
                (8, self.queue_trial_expired_day_8, 'trial_expired_day_8'),
            ]:
                scheduled_at = trial_start + timedelta(days=day_offset)
                if now < scheduled_at or now > scheduled_at + timedelta(days=2):
                    continue
                event = await queue_method(
                    parent_id=parent_id,
                    recipient_email=recipient_email,
                    scheduled_send_at=scheduled_at.isoformat(),
                    metadata={**metadata, 'dedupe_key': f'{trigger_type}|{parent_id}|{recipient_email}|{scheduled_at.date().isoformat()}'},
                )
                if self._was_created_recently(event):
                    created_count += 1
        return created_count

    async def generate_due_annual_renewal_events(self) -> int:
        now = datetime.now(UTC)
        try:
            rows = await self.supabase.select(
                'billing_subscriptions',
                'billing_interval=eq.annual&subscription_status=in.(active,trialing)&current_period_ends_at=not.is.null&order=current_period_ends_at.asc&limit=500',
            )
        except SupabaseClientError as exc:
            logger.warning('Could not load annual subscriptions for email events: %s', exc)
            return 0

        created_count = 0
        for row in rows:
            period_end = self._parse_datetime(row.get('current_period_ends_at'))
            parent_id = row.get('parent_id')
            if not period_end or not parent_id:
                continue
            if period_end <= now:
                continue
            scheduled_at = period_end - timedelta(days=7)
            if now < scheduled_at:
                continue
            recipient_email = await self._parent_email(parent_id)
            if not recipient_email:
                continue
            amount = self._annual_amount_label(row)
            event = await self.queue_annual_renewal_reminder(
                parent_id=parent_id,
                child_id=row.get('child_id'),
                recipient_email=recipient_email,
                scheduled_send_at=scheduled_at.isoformat(),
                metadata={
                    'renewal_date': period_end.date().isoformat(),
                    'amount': amount,
                    'stripe_subscription_id': row.get('stripe_subscription_id'),
                    'dedupe_key': f"annual_renewal_reminder|{row.get('stripe_subscription_id')}|{scheduled_at.date().isoformat()}",
                },
            )
            if self._was_created_recently(event):
                created_count += 1
        return created_count

    async def generate_due_weekly_progress_events(self) -> int:
        now = datetime.now(UTC)
        monday = self._week_start(now)
        try:
            children = await self.supabase.select('child_profiles', 'status=neq.inactive&order=created_at.asc&limit=500')
        except SupabaseClientError as exc:
            logger.warning('Could not load children for weekly progress emails: %s', exc)
            return 0

        created_count = 0
        for child in children:
            parent_id = child.get('parent_id')
            child_id = child.get('id')
            if not parent_id or not child_id:
                continue
            recipient_email = await self._parent_email(parent_id)
            if not recipient_email:
                continue
            metadata = await self._weekly_progress_metadata(parent_id, child_id, child, monday)
            event = await self.queue_weekly_progress(
                parent_id=parent_id,
                child_id=child_id,
                recipient_email=recipient_email,
                scheduled_send_at=monday.isoformat(),
                metadata=metadata,
            )
            if self._was_created_recently(event):
                created_count += 1
        return created_count

    async def send_event(self, event: dict) -> dict:
        event_id = event.get('id')
        retry_count = int(event.get('retry_count') or 0)
        trigger_type = event.get('trigger_type') or ''
        recipient_email = event.get('recipient_email') or ''
        metadata = event.get('metadata') or {}

        try:
            content = self.render_template(trigger_type, metadata)
        except Exception as exc:
            logger.warning('Email template render failed for event %s: %s', event_id, exc)
            return await self._record_delivery(
                event=event,
                status='failed',
                retry_count=retry_count + 1,
                error_message='Email template could not be rendered.',
            )

        if not self.settings.resend_api_key.strip():
            return await self._record_delivery(
                event=event,
                status='skipped',
                retry_count=retry_count,
                error_message='RESEND_API_KEY is not configured.',
                payload_preview={'subject': content.subject},
            )

        try:
            provider_message_id = await self._send_resend_email(recipient_email, content)
            return await self._record_delivery(
                event=event,
                status='sent',
                retry_count=retry_count,
                provider_message_id=provider_message_id,
                payload_preview={'subject': content.subject},
            )
        except Exception as exc:
            logger.warning('Resend email failed for event %s: %s', event_id, exc)
            return await self._record_delivery(
                event=event,
                status='failed',
                retry_count=retry_count + 1,
                error_message='Resend email delivery failed.',
                payload_preview={'subject': content.subject},
            )

    def render_template(self, trigger_type: str, metadata: dict[str, Any] | None = None) -> EmailContent:
        self._validate_trigger(trigger_type)
        data = metadata or {}
        child_name = str(data.get('child_name') or 'your child')
        manage_url = str(data.get('manage_billing_url') or self._manage_billing_url())
        app_url = str(data.get('app_url') or self._app_url())

        templates = {
            'signup_welcome': self._signup_welcome(app_url),
            'trial_day_5': self._trial_day_5(manage_url),
            'trial_day_7': self._trial_day_7(manage_url),
            'trial_expired_day_8': self._trial_expired_day_8(manage_url),
            'payment_success': self._payment_success(app_url),
            'payment_failed': self._payment_failed(manage_url),
            'annual_renewal_reminder': self._annual_renewal_reminder(data, manage_url),
            'weekly_progress': self._weekly_progress(data, child_name, app_url),
        }
        return templates[trigger_type]

    async def _send_resend_email(self, recipient_email: str, content: EmailContent) -> str | None:
        payload = {
            'from': self.settings.resend_from_email,
            'to': [recipient_email],
            'subject': content.subject,
            'text': content.text,
            'html': content.html,
        }
        headers = {
            'Authorization': f'Bearer {self.settings.resend_api_key}',
            'Content-Type': 'application/json',
        }
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post('https://api.resend.com/emails', json=payload, headers=headers)
        response.raise_for_status()
        data = response.json() if response.content else {}
        message_id = data.get('id')
        return str(message_id) if message_id else None

    async def _record_delivery(
        self,
        *,
        event: dict,
        status: str,
        retry_count: int,
        provider_message_id: str | None = None,
        error_message: str | None = None,
        payload_preview: dict[str, Any] | None = None,
    ) -> dict:
        now = datetime.now(UTC).isoformat()
        event_id = event.get('id')
        sent_at = now if status == 'sent' else None
        update_payload = {
            'status': status,
            'retry_count': retry_count,
            'sent_at': sent_at,
        }
        if event_id:
            await self.supabase.update('email_events', {'id': f'eq.{event_id}'}, update_payload)

        log_payload = {
            'email_event_id': event_id,
            'parent_id': event.get('parent_id'),
            'child_id': event.get('child_id'),
            'trigger_type': event.get('trigger_type'),
            'recipient_email': event.get('recipient_email'),
            'provider': event.get('provider') or 'resend',
            'provider_message_id': provider_message_id,
            'status': status,
            'error_message': error_message,
            'scheduled_send_at': event.get('scheduled_send_at'),
            'sent_at': sent_at,
            'retry_count': retry_count,
            'payload_preview': payload_preview or {},
        }
        try:
            logs = await self.supabase.insert('email_delivery_logs', log_payload)
        except SupabaseClientError as exc:
            logger.warning('Email delivery log insert failed for event %s: %s', event_id, exc)
            logs = []
        return logs[0] if logs else {'status': status, 'email_event_id': event_id}

    async def _find_existing_event(
        self,
        *,
        trigger_type: str,
        recipient_email: str,
        parent_id: str | None,
        child_id: str | None,
        event_key: str,
    ) -> dict | None:
        filters = [
            f'trigger_type=eq.{quote(trigger_type)}',
            f'normalized_recipient_email=eq.{quote(recipient_email)}',
            'status=in.(pending,sent,skipped)',
            'order=created_at.desc',
            'limit=50',
        ]
        if parent_id:
            filters.append(f'parent_id=eq.{quote(parent_id)}')
        else:
            filters.append('parent_id=is.null')
        if child_id:
            filters.append(f'child_id=eq.{quote(child_id)}')
        else:
            filters.append('child_id=is.null')

        records = await self.supabase.select('email_events', '&'.join(filters))
        for record in records:
            metadata = record.get('metadata') or {}
            if metadata.get('event_key') == event_key:
                return record
        return None

    def _event_key(
        self,
        trigger_type: str,
        parent_id: str | None,
        child_id: str | None,
        recipient_email: str,
        scheduled_send_at: str | None,
        metadata: dict[str, Any],
    ) -> str:
        explicit_key = metadata.get('event_key') or metadata.get('dedupe_key')
        if explicit_key:
            return str(explicit_key)
        scheduled_day = self._date_part(scheduled_send_at) or str(metadata.get('send_date') or '')
        return '|'.join([trigger_type, parent_id or '', child_id or '', recipient_email, scheduled_day])

    def _date_part(self, value: str | None) -> str | None:
        if not value:
            return None
        return value[:10]

    def _parse_datetime(self, value: object) -> datetime | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except Exception:
            return None

    def _week_start(self, value: datetime) -> datetime:
        start = value - timedelta(days=value.weekday())
        return start.replace(hour=9, minute=0, second=0, microsecond=0)

    def _was_created_recently(self, event: dict) -> bool:
        created_at = self._parse_datetime(event.get('created_at'))
        if not created_at:
            return event.get('status') == 'pending'
        return datetime.now(UTC) - created_at < timedelta(seconds=30)

    async def _parent_email(self, parent_id: str) -> str | None:
        try:
            records = await self.supabase.select('profiles', f'id=eq.{quote(parent_id)}&select=email&limit=1')
        except SupabaseClientError as exc:
            logger.warning('Could not load parent email for %s: %s', parent_id, exc)
            return None
        if not records:
            return None
        email = records[0].get('email')
        return str(email).strip().lower() if email else None

    async def _weekly_progress_metadata(self, parent_id: str, child_id: str, child: dict, monday: datetime) -> dict[str, Any]:
        from .child_report_service import ChildReportService

        try:
            preview = await ChildReportService().weekly_email_preview(parent_id, child_id)
            subject_highlights = [
                f'{item.subject}: {item.recent_improvement or item.strong_area or "practice is ready"}'
                for item in preview.subject_progress[:3]
            ]
            return {
                'child_name': preview.child_name,
                'session_count': sum(item.chat_count for item in preview.subject_progress),
                'subject_highlights': subject_highlights,
                'recommended_next_step': preview.recommended_next_steps[0] if preview.recommended_next_steps else None,
                'send_date': monday.date().isoformat(),
                'dedupe_key': f'weekly_progress|{parent_id}|{child_id}|{monday.date().isoformat()}',
            }
        except Exception as exc:
            logger.warning('Weekly progress preview failed for child %s: %s', child_id, exc)
            return {
                'child_name': child.get('name') or 'your child',
                'session_count': 0,
                'subject_highlights': [],
                'recommended_next_step': 'Try one short, focused practice session this week.',
                'send_date': monday.date().isoformat(),
                'dedupe_key': f'weekly_progress|{parent_id}|{child_id}|{monday.date().isoformat()}',
            }

    def _annual_amount_label(self, subscription: dict) -> str:
        plan_type = subscription.get('plan_type')
        if plan_type == 'voice':
            return '$1,749/year'
        if plan_type == 'text':
            return '$1,419/year'
        return ''

    def _validate_trigger(self, trigger_type: str) -> None:
        if trigger_type not in EMAIL_TRIGGER_TYPES:
            raise ValueError(f'Unsupported email trigger type: {trigger_type}')

    def _app_url(self) -> str:
        return self.settings.app_public_url.strip() or self.settings.stripe_customer_portal_return_url.strip() or 'https://www.msalisia.com'

    def _manage_billing_url(self) -> str:
        return self.settings.stripe_customer_portal_return_url.strip() or f'{self._app_url().rstrip("/")}/billing'

    def _content(self, subject: str, lines: list[str]) -> EmailContent:
        text = '\n\n'.join(lines)
        html = '<div>' + ''.join(f'<p>{escape(line)}</p>' for line in lines) + '</div>'
        return EmailContent(subject=subject, text=text, html=html)

    def _signup_welcome(self, app_url: str) -> EmailContent:
        return self._content(
            'Welcome to MsAlisia - Your Free Trial Starts Now',
            [
                'Welcome to MsAlisia. Your free trial starts now.',
                'To get started, create or review your child profile, choose the subjects your child will practice, and begin with a short assessment.',
                'Ms. Alisia will use that assessment to make tutoring feel helpful, warm, and personalized.',
                f'Open MsAlisia: {app_url}',
                'The MsAlisia Team',
            ],
        )

    def _signup_verification_code(self, code: str, expires_in_minutes: int) -> EmailContent:
        return self._content(
            'Your MsAlisia verification code',
            [
                f'Your verification code is: {code}.',
                f'This code expires in {expires_in_minutes} minutes.',
                'If you did not request this, you can ignore this email.',
                'The MsAlisia Team',
            ],
        )

    def _password_reset_code(self, code: str, expires_in_minutes: int) -> EmailContent:
        return self._content(
            'Reset your MsAlisia password',
            [
                f'Your MsAlisia password reset code is: {code}',
                f'This code expires in {expires_in_minutes} minutes. If you did not request this, you can ignore this email.',
                'The MsAlisia Team',
            ],
        )

    def _trial_day_5(self, manage_url: str) -> EmailContent:
        return self._content(
            'Your free trial ends in 2 days',
            [
                'Your MsAlisia free trial ends in 2 days.',
                'This is a good time to review your child profile, recent learning activity, and the plan that fits your family.',
                f'Subscribe or manage billing: {manage_url}',
                'The MsAlisia Team',
            ],
        )

    def _trial_day_7(self, manage_url: str) -> EmailContent:
        return self._content(
            'Your MsAlisia trial ends tomorrow',
            [
                'Your MsAlisia trial ends tomorrow.',
                'Subscribe today to keep your child learning without interruption.',
                f'Subscribe or manage billing: {manage_url}',
                'The MsAlisia Team',
            ],
        )

    def _trial_expired_day_8(self, manage_url: str) -> EmailContent:
        return self._content(
            'Your MsAlisia trial has ended',
            [
                'Your MsAlisia trial has ended.',
                'Add a subscription to continue tutoring, reports, and learning support for your child.',
                f'Subscribe or manage billing: {manage_url}',
                'The MsAlisia Team',
            ],
        )

    def _payment_success(self, app_url: str) -> EmailContent:
        return self._content(
            "You're subscribed to MsAlisia",
            [
                'Your MsAlisia subscription is active.',
                'Thank you. Your child can continue learning with Ms. Alisia.',
                f'Open MsAlisia: {app_url}',
                'The MsAlisia Team',
            ],
        )

    def _payment_failed(self, manage_url: str) -> EmailContent:
        return self._content(
            'Action needed - your MsAlisia payment',
            [
                'We could not complete your MsAlisia payment.',
                'Please update your payment method to keep your child learning with Ms. Alisia.',
                f'Update payment method: {manage_url}',
                'The MsAlisia Team',
            ],
        )

    def _annual_renewal_reminder(self, data: dict[str, Any], manage_url: str) -> EmailContent:
        renewal_date = str(data.get('renewal_date') or 'your renewal date')
        amount = str(data.get('amount') or '').strip()
        amount_line = f'Renewal amount: {amount}.' if amount else 'You can review your plan and payment details before renewal.'
        return self._content(
            'Your MsAlisia annual plan renews in 7 days',
            [
                f'Your MsAlisia annual plan renews on {renewal_date}.',
                amount_line,
                f'Manage subscription: {manage_url}',
                'The MsAlisia Team',
            ],
        )

    def _weekly_progress(self, data: dict[str, Any], child_name: str, app_url: str) -> EmailContent:
        session_count = str(data.get('session_count') or '0')
        subject_highlights = data.get('subject_highlights') or []
        if isinstance(subject_highlights, list) and subject_highlights:
            highlights = '; '.join(str(item) for item in subject_highlights[:4])
        else:
            highlights = 'Ms. Alisia will keep building highlights as learning sessions are completed.'
        recommended_next_step = str(data.get('recommended_next_step') or 'Try one short, focused practice session this week.')
        return self._content(
            f"{child_name}'s weekly learning summary",
            [
                f'Here is {child_name}\'s weekly learning summary.',
                f'Session count: {session_count}.',
                f'Subject highlights: {highlights}',
                f'Recommended next step: {recommended_next_step}',
                'Every bit of steady practice helps build confidence.',
                f'Open MsAlisia: {app_url}',
                'The MsAlisia Team',
            ],
        )
