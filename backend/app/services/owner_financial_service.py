from __future__ import annotations

import csv
import io
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from .supabase_client import SupabaseClient, SupabaseClientError


PLAN_MONTHLY_CENTS = {
    ('text', 'monthly'): 12900,
    ('text', 'annual'): 141900,
    ('voice', 'monthly'): 15900,
    ('voice', 'annual'): 174900,
}

PAID_EVENT_TYPES = {'invoice.paid', 'payment_intent.succeeded'}
FAILED_EVENT_TYPES = {'invoice.payment_failed', 'payment_intent.payment_failed'}


class OwnerFinancialService:
    def __init__(self) -> None:
        self.supabase = SupabaseClient()

    async def summary(self) -> dict:
        subscriptions, access_rows, financial_events, discounts, coupons, referrals, rewards, trials = await self._owner_dataset()
        paid_events = [event for event in financial_events if event.get('event_type') in PAID_EVENT_TYPES]
        failed_events = [event for event in financial_events if event.get('event_type') in FAILED_EVENT_TYPES]
        current_month = datetime.now(UTC).strftime('%Y-%m')
        total_revenue_cents = sum(self._int(event.get('amount_cents')) for event in paid_events)
        current_month_revenue_cents = sum(
            self._int(event.get('amount_cents'))
            for event in paid_events
            if self._date_prefix(event.get('occurred_at') or event.get('created_at')) == current_month
        )
        subscription_basis = self._subscription_basis(subscriptions, access_rows)
        active_rows = [row for row in subscription_basis if self._status(row) in {'active', 'trialing'}]
        mrr_cents = sum(self._mrr_cents(row) for row in active_rows)
        now = datetime.now(UTC)

        return {
            'currency': 'usd',
            'total_revenue_cents_estimate': total_revenue_cents,
            'current_month_revenue_cents_estimate': current_month_revenue_cents,
            'mrr_cents_estimate': mrr_cents,
            'arr_cents_estimate': mrr_cents * 12,
            'active_subscriptions_count': len([row for row in active_rows if self._status(row) == 'active']),
            'paused_unpaid_subscriptions_count': len([row for row in subscription_basis if self._status(row) in {'past_due', 'paused', 'unpaid'}]),
            'canceled_subscriptions_count': len([row for row in subscriptions if self._status(row) in {'canceled', 'incomplete_expired'}]),
            'active_trials_count': len([row for row in access_rows if row.get('access_status') == 'trial' and not self._is_past(row.get('trial_ends_at'))]),
            'expired_trials_count': len([row for row in trials if self._is_past(row.get('trial_ends_at'))]),
            'failed_payments_count': len(failed_events),
            'text_plan_count': len([row for row in active_rows if row.get('plan_type') == 'text']),
            'voice_plan_count': len([row for row in active_rows if row.get('plan_type') == 'voice']),
            'monthly_plan_count': len([row for row in active_rows if row.get('billing_interval') == 'monthly']),
            'annual_plan_count': len([row for row in active_rows if row.get('billing_interval') == 'annual']),
            'family_discount_usage_count': len([row for row in discounts if row.get('discount_type') == 'family']),
            'coupon_redemption_count': len(coupons),
            'referral_reward_count': len(rewards),
            'generated_at': now.isoformat(),
            'notes': [
                'Revenue values are estimates from stored financial event records.',
                'MRR and ARR are estimates from active subscription/access plan records.',
            ],
        }

    async def subscriptions(self, limit: int = 250) -> list[dict]:
        subscriptions, access_rows, customers, profiles, children, discounts, coupons = await self._subscription_dataset(limit)
        profile_by_id = {profile.get('id'): profile for profile in profiles}
        child_by_id = {child.get('id'): child for child in children}
        customer_by_parent = {customer.get('parent_id'): customer for customer in customers if customer.get('parent_id')}
        discounts_by_subscription = self._group_by(discounts, 'billing_subscription_id')
        discounts_by_parent = self._group_by(discounts, 'parent_id')
        coupons_by_subscription = self._group_by(coupons, 'billing_subscription_id')

        rows = []
        seen_children = set()
        current_subscriptions = self._current_subscription_rows(subscriptions)
        for sub in current_subscriptions:
            parent = profile_by_id.get(sub.get('parent_id')) or {}
            child = child_by_id.get(sub.get('child_id')) or {}
            customer = customer_by_parent.get(sub.get('parent_id')) or {}
            seen_children.add(sub.get('child_id'))
            rows.append(self._subscription_row(
                source='billing_subscriptions',
                record=sub,
                parent=parent,
                child=child,
                customer=customer,
                discounts=discounts_by_subscription.get(sub.get('id')) or discounts_by_parent.get(sub.get('parent_id')) or [],
                coupons=coupons_by_subscription.get(sub.get('id')) or [],
            ))

        for access in access_rows:
            if access.get('child_id') in seen_children:
                continue
            if self._is_placeholder_access_row(access):
                continue
            parent = profile_by_id.get(access.get('parent_id')) or {}
            child = child_by_id.get(access.get('child_id')) or {}
            customer = customer_by_parent.get(access.get('parent_id')) or {}
            rows.append(self._subscription_row(
                source='child_access',
                record=access,
                parent=parent,
                child=child,
                customer=customer,
                discounts=discounts_by_parent.get(access.get('parent_id')) or [],
                coupons=[],
            ))
        return rows[:limit]

    async def failed_payments(self, limit: int = 100) -> list[dict]:
        events, profiles, children, subscriptions, access_rows = await self._failed_payment_dataset(limit)
        profile_by_id = {profile.get('id'): profile for profile in profiles}
        child_by_id = {child.get('id'): child for child in children}
        sub_by_id = {sub.get('id'): sub for sub in subscriptions}
        sub_by_stripe = {sub.get('stripe_subscription_id'): sub for sub in subscriptions if sub.get('stripe_subscription_id')}
        access_by_child = {row.get('child_id'): row for row in access_rows}
        rows = []
        for event in events:
            sub = sub_by_id.get(event.get('billing_subscription_id')) or sub_by_stripe.get(event.get('stripe_subscription_id')) or {}
            child_id = event.get('child_id') or sub.get('child_id')
            parent_id = event.get('parent_id') or sub.get('parent_id')
            access = access_by_child.get(child_id) or {}
            parent = profile_by_id.get(parent_id) or {}
            child = child_by_id.get(child_id) or {}
            rows.append({
                'id': event.get('id'),
                'parent_id': parent_id,
                'parent_name': parent.get('full_name'),
                'parent_email': parent.get('email'),
                'child_id': child_id,
                'child_name': child.get('name'),
                'plan_type': sub.get('plan_type') or access.get('plan_type'),
                'billing_interval': sub.get('billing_interval') or access.get('billing_interval'),
                'amount_cents': self._int(event.get('amount_cents')),
                'currency': event.get('currency') or 'usd',
                'failure_date': event.get('occurred_at') or event.get('created_at'),
                'billing_status': event.get('billing_status') or sub.get('subscription_status'),
                'access_status': access.get('access_status'),
                'grace_period_ends_at': access.get('grace_period_ends_at') or sub.get('grace_period_ends_at'),
                'latest_event_type': event.get('event_type'),
                'stripe_invoice_id': event.get('stripe_invoice_id'),
            })
        return rows

    async def discounts(self, limit: int = 150) -> dict:
        discounts, coupons, profiles, children = await self._discount_dataset(limit)
        profile_by_id = {profile.get('id'): profile for profile in profiles}
        child_by_id = {child.get('id'): child for child in children}
        return {
            'discounts': [self._discount_row(row, profile_by_id, child_by_id) for row in discounts],
            'coupon_redemptions': [self._coupon_row(row, profile_by_id, child_by_id) for row in coupons],
        }

    async def referrals(self, limit: int = 150) -> dict:
        codes, referrals, rewards, profiles = await self._referral_dataset(limit)
        profile_by_id = {profile.get('id'): profile for profile in profiles}
        return {
            'referral_codes': [self._referral_code_row(row, profile_by_id) for row in codes],
            'referrals': [self._referral_row(row, profile_by_id) for row in referrals],
            'referral_rewards': [self._reward_row(row, profile_by_id) for row in rewards],
        }

    async def events(self, limit: int = 200) -> list[dict]:
        events, profiles, children = await self._events_dataset(limit)
        profile_by_id = {profile.get('id'): profile for profile in profiles}
        child_by_id = {child.get('id'): child for child in children}
        rows = []
        for event in events:
            parent = profile_by_id.get(event.get('parent_id')) or {}
            child = child_by_id.get(event.get('child_id')) or {}
            rows.append({
                'id': event.get('id'),
                'event_type': event.get('event_type'),
                'parent_id': event.get('parent_id'),
                'parent_name': parent.get('full_name'),
                'parent_email': parent.get('email'),
                'child_id': event.get('child_id'),
                'child_name': child.get('name'),
                'amount_cents': self._int(event.get('amount_cents')),
                'currency': event.get('currency') or 'usd',
                'billing_status': event.get('billing_status'),
                'source': 'stripe',
                'occurred_at': event.get('occurred_at') or event.get('created_at'),
                'stripe_invoice_id': event.get('stripe_invoice_id'),
                'stripe_subscription_id': event.get('stripe_subscription_id'),
            })
        return rows

    async def export_csv(self) -> str:
        summary = await self.summary()
        subscriptions = await self.subscriptions(limit=1000)
        failed_payments = await self.failed_payments(limit=500)
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['MsAlisia Owner Financial Export'])
        writer.writerow(['Generated At', summary.get('generated_at')])
        writer.writerow([])
        writer.writerow(['Summary Metric', 'Value'])
        for key, value in summary.items():
            if key == 'notes':
                continue
            writer.writerow([key, value])
        writer.writerow([])
        writer.writerow(['Subscriptions'])
        self._write_rows(writer, subscriptions)
        writer.writerow([])
        writer.writerow(['Failed Payments'])
        self._write_rows(writer, failed_payments)
        return output.getvalue()

    async def _owner_dataset(self) -> tuple[list[dict], ...]:
        return (
            await self._safe_select('billing_subscriptions', 'order=created_at.desc&limit=1000'),
            await self._safe_select('child_access', 'order=created_at.desc&limit=1000'),
            await self._safe_select('financial_events', 'order=occurred_at.desc&limit=1000'),
            await self._safe_select('billing_discounts', 'order=created_at.desc&limit=1000'),
            await self._safe_select('coupon_redemptions', 'order=created_at.desc&limit=1000'),
            await self._safe_select('referrals', 'order=created_at.desc&limit=1000'),
            await self._safe_select('referral_rewards', 'order=created_at.desc&limit=1000'),
            await self._safe_select('parent_trial_history', 'order=trial_started_at.desc&limit=1000'),
        )

    async def _subscription_dataset(self, limit: int) -> tuple[list[dict], ...]:
        query_limit = max(limit, 250)
        return (
            await self._safe_select('billing_subscriptions', f'order=created_at.desc&limit={query_limit}'),
            await self._safe_select('child_access', f'order=created_at.desc&limit={query_limit}'),
            await self._safe_select('billing_customers', f'order=created_at.desc&limit={query_limit}'),
            await self._safe_select('profiles', 'order=created_at.desc&limit=1000'),
            await self._safe_select('child_profiles', 'order=created_at.desc&limit=1000'),
            await self._safe_select('billing_discounts', 'order=created_at.desc&limit=1000'),
            await self._safe_select('coupon_redemptions', 'order=created_at.desc&limit=1000'),
        )

    async def _failed_payment_dataset(self, limit: int) -> tuple[list[dict], ...]:
        events = await self._safe_select('financial_events', f'order=occurred_at.desc&limit={max(limit * 3, 100)}')
        failed = [event for event in events if event.get('event_type') in FAILED_EVENT_TYPES][:limit]
        return (
            failed,
            await self._safe_select('profiles', 'order=created_at.desc&limit=1000'),
            await self._safe_select('child_profiles', 'order=created_at.desc&limit=1000'),
            await self._safe_select('billing_subscriptions', 'order=created_at.desc&limit=1000'),
            await self._safe_select('child_access', 'order=created_at.desc&limit=1000'),
        )

    async def _discount_dataset(self, limit: int) -> tuple[list[dict], ...]:
        return (
            await self._safe_select('billing_discounts', f'order=created_at.desc&limit={limit}'),
            await self._safe_select('coupon_redemptions', f'order=created_at.desc&limit={limit}'),
            await self._safe_select('profiles', 'order=created_at.desc&limit=1000'),
            await self._safe_select('child_profiles', 'order=created_at.desc&limit=1000'),
        )

    async def _referral_dataset(self, limit: int) -> tuple[list[dict], ...]:
        return (
            await self._safe_select('referral_codes', f'order=created_at.desc&limit={limit}'),
            await self._safe_select('referrals', f'order=created_at.desc&limit={limit}'),
            await self._safe_select('referral_rewards', f'order=created_at.desc&limit={limit}'),
            await self._safe_select('profiles', 'order=created_at.desc&limit=1000'),
        )

    async def _events_dataset(self, limit: int) -> tuple[list[dict], ...]:
        return (
            await self._safe_select('financial_events', f'order=occurred_at.desc&limit={limit}'),
            await self._safe_select('profiles', 'order=created_at.desc&limit=1000'),
            await self._safe_select('child_profiles', 'order=created_at.desc&limit=1000'),
        )

    async def _safe_select(self, table: str, query: str) -> list[dict]:
        try:
            return await self.supabase.select(table, query)
        except SupabaseClientError:
            return []

    def _subscription_basis(self, subscriptions: list[dict], access_rows: list[dict]) -> list[dict]:
        return self._current_subscription_rows(subscriptions) if subscriptions else self._current_subscription_rows(access_rows)

    def _current_subscription_rows(self, rows: list[dict]) -> list[dict]:
        current_by_child: dict[str, dict] = {}
        unlinked_rows: list[dict] = []
        for row in rows:
            child_id = row.get('child_id')
            if not child_id:
                unlinked_rows.append(row)
                continue
            existing = current_by_child.get(child_id)
            if not existing or self._current_row_sort_key(row) > self._current_row_sort_key(existing):
                current_by_child[child_id] = row
        return sorted([*current_by_child.values(), *unlinked_rows], key=self._current_row_sort_key, reverse=True)

    def _current_row_sort_key(self, row: dict) -> tuple[int, float]:
        status_priority = {
            'active': 5,
            'trialing': 4,
            'trial': 4,
            'past_due': 3,
            'paused': 3,
            'unpaid': 3,
            'incomplete': 2,
            'inactive': 1,
            'canceled': 0,
            'incomplete_expired': 0,
        }.get(self._status(row) or '', 1)
        date_value = (
            row.get('current_period_ends_at')
            or row.get('updated_at')
            or row.get('created_at')
            or row.get('trial_ends_at')
        )
        parsed = self._parse_date(date_value)
        timestamp = parsed.timestamp() if parsed else 0.0
        return status_priority, timestamp

    def _is_placeholder_access_row(self, row: dict) -> bool:
        return (
            self._status(row) == 'inactive'
            and not row.get('plan_type')
            and not row.get('billing_interval')
            and not row.get('stripe_subscription_id')
            and not row.get('trial_started_at')
            and not row.get('trial_ends_at')
            and not row.get('current_period_ends_at')
            and self._plan_amount_cents(row) == 0
        )

    def _subscription_row(self, source: str, record: dict, parent: dict, child: dict, customer: dict, discounts: list[dict], coupons: list[dict]) -> dict:
        status = self._status(record)
        return {
            'source': source,
            'id': record.get('id'),
            'parent_id': record.get('parent_id'),
            'parent_name': parent.get('full_name') or customer.get('billing_name'),
            'parent_email': parent.get('email') or customer.get('email'),
            'child_id': record.get('child_id'),
            'child_name': child.get('name'),
            'grade_level': child.get('grade_level'),
            'plan_type': record.get('plan_type'),
            'billing_interval': record.get('billing_interval'),
            'status': status,
            'access_status': record.get('access_status'),
            'subscription_status': record.get('subscription_status'),
            'current_period_started_at': record.get('current_period_started_at'),
            'current_period_ends_at': record.get('current_period_ends_at'),
            'next_renewal_date': record.get('current_period_ends_at'),
            'trial_ends_at': record.get('trial_ends_at'),
            'amount_cents_estimate': self._plan_amount_cents(record),
            'amount_display': self._amount_display(record),
            'discount_status': self._discount_status(discounts, coupons),
            'family_discount_status': self._family_discount_status(record, discounts),
            'payment_failure_status': record.get('access_paused_reason') or ('payment_required' if status in {'past_due', 'unpaid'} else None),
            'grace_period_ends_at': record.get('grace_period_ends_at'),
            'stripe_customer_id': record.get('stripe_customer_id'),
            'stripe_subscription_id': record.get('stripe_subscription_id'),
        }

    def _discount_row(self, row: dict, profiles: dict, children: dict) -> dict:
        parent = profiles.get(row.get('parent_id')) or {}
        child = children.get(row.get('child_id')) or {}
        return {
            'id': row.get('id'),
            'parent_id': row.get('parent_id'),
            'parent_email': parent.get('email'),
            'parent_name': parent.get('full_name'),
            'child_id': row.get('child_id'),
            'child_name': child.get('name'),
            'discount_type': row.get('discount_type'),
            'discount_percent': self._decimal(row.get('discount_percent')),
            'eligibility_status': row.get('eligibility_status'),
            'stripe_coupon_id': row.get('stripe_coupon_id'),
            'applies_at': row.get('applies_at'),
            'removed_at': row.get('removed_at'),
            'created_at': row.get('created_at'),
        }

    def _coupon_row(self, row: dict, profiles: dict, children: dict) -> dict:
        parent = profiles.get(row.get('parent_id')) or {}
        child = children.get(row.get('child_id')) or {}
        return {
            'id': row.get('id'),
            'parent_id': row.get('parent_id'),
            'parent_email': parent.get('email'),
            'parent_name': parent.get('full_name'),
            'child_id': row.get('child_id'),
            'child_name': child.get('name'),
            'coupon_code': row.get('coupon_code'),
            'validation_status': row.get('validation_status'),
            'applied_at': row.get('applied_at'),
            'rejection_reason': row.get('rejection_reason'),
            'created_at': row.get('created_at'),
        }

    def _referral_code_row(self, row: dict, profiles: dict) -> dict:
        parent = profiles.get(row.get('parent_id')) or {}
        return {
            'id': row.get('id'),
            'parent_id': row.get('parent_id'),
            'parent_email': parent.get('email'),
            'parent_name': parent.get('full_name'),
            'referral_code': row.get('referral_code'),
            'referral_url': row.get('referral_url'),
            'is_active': row.get('is_active'),
            'use_count': self._int(row.get('use_count')),
            'fraud_review_status': row.get('fraud_review_status'),
            'created_at': row.get('created_at'),
        }

    def _referral_row(self, row: dict, profiles: dict) -> dict:
        referrer = profiles.get(row.get('referrer_parent_id')) or {}
        referred = profiles.get(row.get('referred_parent_id')) or {}
        return {
            'id': row.get('id'),
            'referrer_parent_id': row.get('referrer_parent_id'),
            'referrer_email': referrer.get('email'),
            'referrer_name': referrer.get('full_name'),
            'referred_parent_id': row.get('referred_parent_id'),
            'referred_email': referred.get('email') or row.get('referred_parent_email'),
            'referred_name': referred.get('full_name'),
            'status': row.get('status'),
            'consecutive_paid_months': self._int(row.get('consecutive_paid_months')),
            'reward_eligible_at': row.get('reward_eligible_at'),
            'reward_applied_at': row.get('reward_applied_at'),
            'self_referral_blocked': row.get('self_referral_blocked'),
            'created_at': row.get('created_at'),
        }

    def _reward_row(self, row: dict, profiles: dict) -> dict:
        referrer = profiles.get(row.get('referrer_parent_id')) or {}
        return {
            'id': row.get('id'),
            'referral_id': row.get('referral_id'),
            'referrer_parent_id': row.get('referrer_parent_id'),
            'referrer_email': referrer.get('email'),
            'referrer_name': referrer.get('full_name'),
            'reward_type': row.get('reward_type'),
            'reward_status': row.get('reward_status'),
            'reward_amount_cents': self._int(row.get('reward_amount_cents')),
            'eligibility_months_required': self._int(row.get('eligibility_months_required')),
            'eligible_at': row.get('eligible_at'),
            'applied_at': row.get('applied_at'),
            'voided_at': row.get('voided_at'),
            'created_at': row.get('created_at'),
        }

    def _write_rows(self, writer: csv.writer, rows: list[dict]) -> None:
        if not rows:
            writer.writerow(['No records'])
            return
        headers = sorted({key for row in rows for key in row.keys()})
        writer.writerow(headers)
        for row in rows:
            writer.writerow([row.get(header, '') for header in headers])

    def _group_by(self, rows: list[dict], key: str) -> dict[Any, list[dict]]:
        grouped: dict[Any, list[dict]] = {}
        for row in rows:
            value = row.get(key)
            if value:
                grouped.setdefault(value, []).append(row)
        return grouped

    def _status(self, row: dict) -> str | None:
        return row.get('subscription_status') or row.get('access_status')

    def _mrr_cents(self, row: dict) -> int:
        amount = self._plan_amount_cents(row)
        if row.get('billing_interval') == 'annual':
            return round(amount / 12)
        return amount

    def _plan_amount_cents(self, row: dict) -> int:
        return PLAN_MONTHLY_CENTS.get((row.get('plan_type'), row.get('billing_interval')), 0)

    def _amount_display(self, row: dict) -> str | None:
        amount = self._plan_amount_cents(row)
        status = self._status(row)
        if status in {'trial', 'trialing'}:
            return f'$0 trial now / {self._money(amount)} after trial'
        if not amount:
            return '$0.00'
        return self._money(amount)

    def _money(self, cents: int) -> str:
        return f'${Decimal(cents) / Decimal(100):,.2f}'

    def _discount_status(self, discounts: list[dict], coupons: list[dict]) -> str | None:
        if coupons:
            return coupons[0].get('validation_status') or 'coupon_recorded'
        non_family_discounts = [discount for discount in discounts if discount.get('discount_type') != 'family']
        if non_family_discounts:
            return non_family_discounts[0].get('eligibility_status') or 'discount_recorded'
        return None

    def _family_discount_status(self, record: dict, discounts: list[dict]) -> str | None:
        metadata = record.get('metadata') or {}
        if isinstance(metadata, str):
            metadata = {}
        if record.get('family_discount_remove_at_period_end'):
            return 'Removal at renewal'
        if record.get('family_discount_applied') or metadata.get('family_discount_applied') == 'true':
            return 'Applied'
        if record.get('family_discount_eligible'):
            return 'Family eligible'
        for discount in discounts:
            if discount.get('discount_type') == 'family':
                status = discount.get('eligibility_status') or 'recorded'
                if status == 'eligible':
                    return 'Family eligible (account)'
                if status == 'pending':
                    return 'Eligible next checkout'
                if status == 'applied':
                    return 'Applied'
                if status == 'remove_at_period_end':
                    return 'Removal at renewal'
                return status.replace('_', ' ').title()
        return None

    def _is_past(self, value: str | None) -> bool:
        if not value:
            return False
        parsed = self._parse_date(value)
        return bool(parsed and parsed <= datetime.now(UTC))

    def _date_prefix(self, value: str | None) -> str | None:
        parsed = self._parse_date(value)
        return parsed.strftime('%Y-%m') if parsed else None

    def _parse_date(self, value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except ValueError:
            return None

    def _int(self, value: object) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    def _decimal(self, value: object) -> float | None:
        if value is None:
            return None
        try:
            return float(Decimal(str(value)))
        except Exception:
            return None
