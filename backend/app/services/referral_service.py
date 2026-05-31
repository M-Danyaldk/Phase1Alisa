from __future__ import annotations

import secrets
import string
import json
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

from fastapi import HTTPException

from ..config import get_settings
from .email_service import EmailService
from .supabase_client import SupabaseClient, SupabaseClientError

QUALIFYING_DAYS = 90
REWARD_DAYS = 7
QUALIFYING_REFERRAL_STATUSES = {'signed_up', 'trialing', 'qualified', 'reward_pending'}
BLOCKED_SUBSCRIPTION_STATUSES = {'past_due', 'paused', 'canceled', 'unpaid', 'incomplete_expired'}
PAID_EVENT_TYPES = {'invoice.paid'}
INTERRUPTION_EVENT_TYPES = {'invoice.payment_failed', 'payment_intent.payment_failed'}


class ReferralService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.supabase = SupabaseClient()

    async def parent_summary(self, parent_id: str) -> dict:
        code = await self.ensure_referral_code(parent_id)
        referrals = await self._safe_select('referrals', f'referrer_parent_id=eq.{quote(parent_id)}&order=created_at.desc&limit=100')
        rewards = await self._safe_select('referral_rewards', f'referrer_parent_id=eq.{quote(parent_id)}&order=created_at.desc&limit=100')
        successful = [row for row in referrals if row.get('status') in {'qualified', 'reward_pending', 'rewarded'}]
        earned = [row for row in rewards if row.get('reward_status') == 'applied']
        return {
            'referral_code': code['referral_code'],
            'referral_url': code.get('referral_url') or self._referral_url(code['referral_code']),
            'referrals_sent': len(referrals),
            'successful_referrals': len(successful),
            'rewards_earned': len(earned),
            'referrals': [self._public_referral(row) for row in referrals],
            'rewards': [self._public_reward(row) for row in rewards],
        }

    async def ensure_referral_code(self, parent_id: str) -> dict:
        existing = await self._safe_select('referral_codes', f'parent_id=eq.{quote(parent_id)}&is_active=eq.true&order=created_at.asc&limit=1')
        if existing:
            record = existing[0]
            if not record.get('referral_url'):
                await self.supabase.update('referral_codes', {'id': f'eq.{record["id"]}'}, {'referral_url': self._referral_url(record['referral_code'])})
                record['referral_url'] = self._referral_url(record['referral_code'])
            return record

        for _ in range(8):
            code = self._generate_code()
            try:
                records = await self.supabase.insert('referral_codes', {
                    'parent_id': parent_id,
                    'referral_code': code,
                    'referral_url': self._referral_url(code),
                    'is_active': True,
                    'metadata': {'source': 'lazy_parent_dashboard'},
                })
                if records:
                    return records[0]
            except SupabaseClientError as exc:
                if 'duplicate' not in str(exc).lower() and 'unique' not in str(exc).lower():
                    raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        raise HTTPException(status_code=500, detail='Could not create referral code.')

    async def record_referred_signup(self, referred_parent_id: str, referred_email: str, referral_code: str) -> dict | None:
        code = referral_code.strip()
        if not code:
            return None
        code_rows = await self._safe_select('referral_codes', f'referral_code=eq.{quote(code)}&is_active=eq.true&limit=1')
        if not code_rows:
            return None
        code_row = code_rows[0]
        referrer_parent_id = code_row.get('parent_id')
        normalized_email = referred_email.strip().lower()
        referrer = await self._profile(referrer_parent_id)
        if not referrer or referrer.get('status') != 'active':
            return None
        if str(referrer_parent_id) == str(referred_parent_id) or (referrer.get('email') or '').strip().lower() == normalized_email:
            await self._record_blocked_referral(code_row, referred_parent_id, normalized_email)
            return None
        duplicate = await self._safe_select('referrals', f'referred_normalized_email=eq.{quote(normalized_email)}&limit=1')
        if duplicate:
            return duplicate[0]

        records = await self.supabase.insert('referrals', {
            'referral_code_id': code_row.get('id'),
            'referrer_parent_id': referrer_parent_id,
            'referred_parent_id': referred_parent_id,
            'referred_parent_email': normalized_email,
            'status': 'signed_up',
            'metadata': {'source': 'signup_referral_code'},
        })
        await self.supabase.update('referral_codes', {'id': f'eq.{code_row["id"]}'}, {
            'use_count': int(code_row.get('use_count') or 0) + 1,
            'updated_at': datetime.now(UTC).isoformat(),
        })
        return records[0] if records else None

    async def process_rewards(self) -> dict:
        referrals = await self._safe_select('referrals', 'order=created_at.asc&limit=1000')
        checked_count = 0
        eligible_count = 0
        applied_count = 0
        pending_count = 0
        skipped_count = 0

        for referral in referrals:
            if referral.get('status') not in QUALIFYING_REFERRAL_STATUSES:
                skipped_count += 1
                continue
            checked_count += 1
            existing_rewards = await self._safe_select('referral_rewards', f'referral_id=eq.{quote(referral["id"])}&limit=1')
            if existing_rewards and existing_rewards[0].get('reward_status') == 'applied':
                skipped_count += 1
                continue
            decision = await self._reward_decision(referral)
            if decision['reset_reason']:
                await self._reset_referral_clock(referral, decision['reset_reason'], decision)
                skipped_count += 1
                continue
            if decision['status'] == 'not_eligible':
                skipped_count += 1
                continue

            if decision['status'] == 'pending_verification':
                pending_count += 1
                reward = existing_rewards[0] if existing_rewards else await self._create_reward(referral, 'eligible', decision)
                await self._mark_reward_pending_verification(referral, reward, decision)
                continue

            eligible_count += 1
            reward = existing_rewards[0] if existing_rewards else await self._create_reward(referral, 'eligible', decision)
            applied = await self._apply_reward(referral, reward)
            if applied:
                applied_count += 1
                await self._mark_reward_applied(referral, reward, decision)
            else:
                pending_count += 1
                await self._mark_reward_pending_verification(referral, reward, {**decision, 'reason': 'no_active_referrer_access_to_extend'})

        return {
            'checked_count': checked_count,
            'eligible_count': eligible_count,
            'applied_count': applied_count,
            'pending_count': pending_count,
            'skipped_count': skipped_count,
            'message': 'Referral reward processing completed.',
        }

    async def _reward_decision(self, referral: dict) -> dict:
        referrer_parent_id = referral.get('referrer_parent_id')
        referred_parent_id = referral.get('referred_parent_id')
        base = {
            'status': 'not_eligible',
            'reset_reason': None,
            'reason': None,
            'paid_invoice_count': 0,
            'proof_source': 'financial_events',
        }
        if not referrer_parent_id or not referred_parent_id:
            return {**base, 'reason': 'missing_parent_link'}
        if not await self._parent_has_active_subscription(referrer_parent_id):
            return {**base, 'reason': 'referrer_not_active'}

        all_referred_subs = await self._safe_select('billing_subscriptions', f'parent_id=eq.{quote(referred_parent_id)}&order=created_at.asc&limit=50')
        if not all_referred_subs:
            if not await self._parent_has_active_subscription(referred_parent_id):
                return {**base, 'reason': 'referred_parent_not_active'}
            return {**base, 'status': 'pending_verification', 'reason': 'missing_billing_subscription_records', 'proof_source': 'child_access_only'}

        if any(sub.get('subscription_status') in BLOCKED_SUBSCRIPTION_STATUSES for sub in all_referred_subs):
            return {**base, 'reset_reason': 'referred_parent_subscription_inactive', 'reason': 'referred_parent_subscription_inactive'}

        active_referred_subs = [sub for sub in all_referred_subs if sub.get('subscription_status') == 'active']
        if not active_referred_subs:
            return {**base, 'reason': 'referred_parent_not_active'}

        window_start = self._parse_date(referral.get('reset_at')) or self._parse_date(referral.get('created_at')) or datetime.now(UTC)
        interruption = await self._latest_interruption_after(active_referred_subs, window_start)
        if interruption:
            return {**base, 'reset_reason': 'referred_parent_payment_interrupted', 'reason': interruption.get('event_type') or 'payment_interruption'}

        paid_events = await self._paid_invoice_events(active_referred_subs, window_start)
        paid_invoice_ids = []
        seen_invoice_ids = set()
        for event in paid_events:
            invoice_id = event.get('stripe_invoice_id') or self._metadata(event).get('stripe_invoice_id') or event.get('id')
            if invoice_id in seen_invoice_ids:
                continue
            seen_invoice_ids.add(invoice_id)
            paid_invoice_ids.append(invoice_id)
        if len(paid_invoice_ids) >= 3:
            third_event_date = self._parse_date(paid_events[2].get('occurred_at') or paid_events[2].get('created_at'))
            return {
                **base,
                'status': 'eligible',
                'reason': 'three_paid_invoices_verified',
                'paid_invoice_count': len(paid_invoice_ids),
                'paid_invoice_ids': paid_invoice_ids[:3],
                'qualified_at': third_event_date.isoformat() if third_event_date else datetime.now(UTC).isoformat(),
            }

        start_dates = [self._parse_date(sub.get('current_period_started_at') or sub.get('created_at')) for sub in active_referred_subs]
        start_dates = [date for date in start_dates if date]
        if not start_dates:
            return {**base, 'reason': 'missing_subscription_start_date', 'paid_invoice_count': len(paid_invoice_ids)}
        paid_since = min(start_dates)
        if paid_since + timedelta(days=QUALIFYING_DAYS) > datetime.now(UTC):
            return {**base, 'reason': 'three_month_window_not_complete', 'paid_invoice_count': len(paid_invoice_ids)}
        return {
            **base,
            'status': 'pending_verification',
            'reason': 'subscription_age_met_but_three_paid_invoices_not_verified',
            'paid_invoice_count': len(paid_invoice_ids),
            'proof_source': 'subscription_dates_without_invoice_count',
        }

    async def _paid_invoice_events(self, subscriptions: list[dict], since: datetime) -> list[dict]:
        events: list[dict] = []
        for subscription in subscriptions:
            subscription_id = subscription.get('stripe_subscription_id')
            if not subscription_id:
                continue
            rows = await self._safe_select(
                'financial_events',
                f'stripe_subscription_id=eq.{quote(subscription_id)}&event_type=in.(invoice.paid)&amount_cents=gt.0&order=occurred_at.asc&limit=20',
            )
            events.extend([row for row in rows if self._parse_date(row.get('occurred_at') or row.get('created_at')) and self._parse_date(row.get('occurred_at') or row.get('created_at')) >= since])
        return sorted(events, key=lambda row: row.get('occurred_at') or row.get('created_at') or '')

    async def _latest_interruption_after(self, subscriptions: list[dict], since: datetime) -> dict | None:
        interruptions: list[dict] = []
        for subscription in subscriptions:
            subscription_id = subscription.get('stripe_subscription_id')
            if not subscription_id:
                continue
            rows = await self._safe_select(
                'financial_events',
                f'stripe_subscription_id=eq.{quote(subscription_id)}&event_type=in.(invoice.payment_failed,payment_intent.payment_failed)&order=occurred_at.desc&limit=10',
            )
            for row in rows:
                occurred = self._parse_date(row.get('occurred_at') or row.get('created_at'))
                if occurred and occurred >= since:
                    interruptions.append(row)
        return sorted(interruptions, key=lambda row: row.get('occurred_at') or row.get('created_at') or '', reverse=True)[0] if interruptions else None

    async def _apply_reward(self, referral: dict, reward: dict) -> bool:
        active_access = await self._safe_select('child_access', f'parent_id=eq.{quote(referral["referrer_parent_id"])}&access_status=eq.active&order=current_period_ends_at.asc&limit=20')
        if not active_access:
            return False
        now = datetime.now(UTC)
        updated = 0
        for row in active_access:
            period_end = self._parse_date(row.get('current_period_ends_at')) or now
            new_end = max(period_end, now) + timedelta(days=REWARD_DAYS)
            await self.supabase.update('child_access', {'id': f'eq.{row["id"]}'}, {
                'current_period_ends_at': new_end.isoformat(),
                'updated_at': now.isoformat(),
            })
            updated += 1
        return updated > 0

    async def _create_reward(self, referral: dict, status: str, evidence: dict | None = None) -> dict:
        records = await self.supabase.insert('referral_rewards', {
            'referral_id': referral['id'],
            'referrer_parent_id': referral['referrer_parent_id'],
            'reward_type': 'free_week_access_extension',
            'reward_status': status,
            'reward_amount_cents': 0,
            'eligibility_months_required': 3,
            'eligible_at': datetime.now(UTC).isoformat(),
            'metadata': {'reward_days': REWARD_DAYS, 'eligibility_evidence': evidence or {}},
        })
        return records[0] if records else {}

    async def _mark_reward_applied(self, referral: dict, reward: dict, evidence: dict | None = None) -> None:
        now = datetime.now(UTC).isoformat()
        await self.supabase.update('referral_rewards', {'id': f'eq.{reward["id"]}'}, {
            'reward_status': 'applied',
            'applied_at': now,
            'metadata': {**self._metadata(reward), 'reward_days': REWARD_DAYS, 'eligibility_evidence': evidence or {}, 'verification_status': 'paid_invoices_verified'},
            'updated_at': now,
        })
        await self.supabase.update('referrals', {'id': f'eq.{referral["id"]}'}, {
            'status': 'rewarded',
            'reward_applied_at': now,
            'consecutive_paid_months': 3,
            'reward_eligible_at': (evidence or {}).get('qualified_at') or now,
            'metadata': {**self._metadata(referral), 'latest_reward_evidence': evidence or {}, 'reward_status_label': 'reward_earned'},
            'updated_at': now,
        })
        await self._queue_referral_success_email(referral, reward)

    async def _mark_reward_pending_verification(self, referral: dict, reward: dict, evidence: dict | None = None) -> None:
        now = datetime.now(UTC).isoformat()
        await self.supabase.update('referral_rewards', {'id': f'eq.{reward["id"]}'}, {
            'reward_status': 'eligible',
            'metadata': {**self._metadata(reward), 'reward_days': REWARD_DAYS, 'eligibility_evidence': evidence or {}, 'verification_status': 'pending_stripe_verification'},
            'updated_at': now,
        })
        await self.supabase.update('referrals', {'id': f'eq.{referral["id"]}'}, {
            'status': 'reward_pending',
            'consecutive_paid_months': min(3, int((evidence or {}).get('paid_invoice_count') or 0)),
            'metadata': {**self._metadata(referral), 'latest_reward_evidence': evidence or {}, 'reward_status_label': 'pending_verification'},
            'updated_at': now,
        })

    async def _reset_referral_clock(self, referral: dict, reason: str, evidence: dict | None = None) -> None:
        await self.supabase.update('referrals', {'id': f'eq.{referral["id"]}'}, {
            'status': 'trialing',
            'consecutive_paid_months': 0,
            'reset_at': datetime.now(UTC).isoformat(),
            'metadata': {**self._metadata(referral), 'latest_reset_reason': reason, 'latest_reward_evidence': evidence or {}},
            'updated_at': datetime.now(UTC).isoformat(),
        })

    async def _parent_has_active_subscription(self, parent_id: str) -> bool:
        if await self._active_parent_subscriptions(parent_id):
            return True
        access = await self._safe_select('child_access', f'parent_id=eq.{quote(parent_id)}&access_status=eq.active&limit=1')
        return bool(access)

    async def _active_parent_subscriptions(self, parent_id: str) -> list[dict]:
        subscriptions = await self._safe_select('billing_subscriptions', f'parent_id=eq.{quote(parent_id)}&subscription_status=eq.active&order=created_at.asc&limit=20')
        if subscriptions:
            return subscriptions
        access = await self._safe_select('child_access', f'parent_id=eq.{quote(parent_id)}&access_status=eq.active&order=created_at.asc&limit=20')
        return access

    async def _queue_referral_success_email(self, referral: dict, reward: dict) -> None:
        referrer_parent_id = referral.get('referrer_parent_id')
        reward_id = reward.get('id')
        if not referrer_parent_id or not reward_id:
            return
        referrer = await self._profile(referrer_parent_id)
        recipient_email = (referrer or {}).get('email')
        if not recipient_email:
            return
        try:
            event = await EmailService().queue_referral_success(
                parent_id=referrer_parent_id,
                recipient_email=str(recipient_email),
                metadata={
                    'referral_id': referral.get('id'),
                    'referral_reward_id': reward_id,
                    'reward_days': REWARD_DAYS,
                    'dedupe_key': f'referral_success|{reward_id}',
                },
            )
            if event.get('status') == 'pending' and event.get('id'):
                await EmailService().send_event(event)
        except Exception:
            return

    async def _record_blocked_referral(self, code_row: dict, referred_parent_id: str, email: str) -> None:
        existing = await self._safe_select('referrals', f'referred_normalized_email=eq.{quote(email)}&limit=1')
        if existing:
            return
        await self.supabase.insert('referrals', {
            'referral_code_id': code_row.get('id'),
            'referrer_parent_id': code_row.get('parent_id'),
            'referred_parent_id': referred_parent_id,
            'referred_parent_email': email,
            'status': 'blocked',
            'self_referral_blocked': True,
            'metadata': {'reason': 'self_referral'},
        })

    async def _profile(self, parent_id: str | None) -> dict | None:
        if not parent_id:
            return None
        rows = await self._safe_select('profiles', f'id=eq.{quote(parent_id)}&limit=1')
        return rows[0] if rows else None

    async def _safe_select(self, table: str, query: str) -> list[dict]:
        try:
            return await self.supabase.select(table, query)
        except SupabaseClientError:
            return []

    def _generate_code(self) -> str:
        alphabet = string.ascii_uppercase + string.digits
        return ''.join(secrets.choice(alphabet) for _ in range(10))

    def _referral_url(self, code: str) -> str:
        base = (self.settings.app_public_url or 'https://www.msalisia.com').rstrip('/')
        return f'{base}/ref/{code}'

    def _public_referral(self, row: dict) -> dict:
        metadata = self._metadata(row)
        return {
            'id': row.get('id'),
            'status': row.get('status'),
            'status_label': metadata.get('reward_status_label') or self._status_label(row.get('status')),
            'referred_parent_email': row.get('referred_parent_email'),
            'consecutive_paid_months': row.get('consecutive_paid_months') or 0,
            'reward_eligible_at': row.get('reward_eligible_at'),
            'reward_applied_at': row.get('reward_applied_at'),
            'latest_reason': (metadata.get('latest_reward_evidence') or {}).get('reason') or metadata.get('latest_reset_reason'),
            'created_at': row.get('created_at'),
        }

    def _public_reward(self, row: dict) -> dict:
        metadata = self._metadata(row)
        return {
            'id': row.get('id'),
            'reward_type': row.get('reward_type'),
            'reward_status': row.get('reward_status'),
            'status_label': 'pending verification' if metadata.get('verification_status') == 'pending_stripe_verification' else row.get('reward_status'),
            'verification_status': metadata.get('verification_status'),
            'eligible_at': row.get('eligible_at'),
            'applied_at': row.get('applied_at'),
            'created_at': row.get('created_at'),
        }

    def _status_label(self, status: str | None) -> str:
        labels = {
            'signed_up': 'Pending',
            'trialing': 'Pending',
            'qualified': 'Qualified',
            'reward_pending': 'Pending verification',
            'rewarded': 'Reward earned',
            'canceled': 'Not eligible',
            'paused': 'Not eligible',
            'blocked': 'Not eligible',
            'expired': 'Not eligible',
        }
        return labels.get(status or '', status or 'Pending')

    def _metadata(self, row: dict) -> dict:
        value = row.get('metadata') or {}
        if isinstance(value, dict):
            return value
        try:
            parsed = json.loads(str(value))
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}

    def _parse_date(self, value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except ValueError:
            return None
