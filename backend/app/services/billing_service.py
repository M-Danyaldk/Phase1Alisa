from datetime import UTC, datetime, timedelta
import json
import logging
import anyio
from urllib.parse import quote

from fastapi import HTTPException

from ..config import get_settings
from ..schemas.billing import ChildAccessUpdateRequest, PlanKey
from .email_service import EmailService
from .supabase_client import SupabaseClient, SupabaseClientError

TRIAL_DAYS = 7
logger = logging.getLogger(__name__)

PLAN_CATALOG: dict[str, dict] = {
    'text_monthly': {
        'plan_type': 'text',
        'billing_interval': 'monthly',
        'display_name': 'Chat Monthly',
        'price_label': '$129/month',
        'stripe_price_env': 'STRIPE_TEXT_MONTHLY_PRICE_ID',
        'settings_attr': 'stripe_text_monthly_price_id',
        'voice_enabled': False,
    },
    'text_annual': {
        'plan_type': 'text',
        'billing_interval': 'annual',
        'display_name': 'Chat Annual',
        'price_label': '$1,419/year',
        'annual_discount_label': '1 month free',
        'stripe_price_env': 'STRIPE_TEXT_ANNUAL_PRICE_ID',
        'settings_attr': 'stripe_text_annual_price_id',
        'voice_enabled': False,
    },
    'voice_monthly': {
        'plan_type': 'voice',
        'billing_interval': 'monthly',
        'display_name': 'Chat + Audio Monthly',
        'price_label': '$159/month',
        'stripe_price_env': 'STRIPE_VOICE_MONTHLY_PRICE_ID',
        'settings_attr': 'stripe_voice_monthly_price_id',
        'voice_enabled': True,
    },
    'voice_annual': {
        'plan_type': 'voice',
        'billing_interval': 'annual',
        'display_name': 'Chat + Audio Annual',
        'price_label': '$1,749/year',
        'annual_discount_label': '1 month free',
        'stripe_price_env': 'STRIPE_VOICE_ANNUAL_PRICE_ID',
        'settings_attr': 'stripe_voice_annual_price_id',
        'voice_enabled': True,
    },
}


class BillingService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.supabase = SupabaseClient()

    def plans(self) -> list[dict]:
        records = []
        for plan_key, plan in PLAN_CATALOG.items():
            stripe_price_id = getattr(self.settings, plan['settings_attr'], '')
            records.append({
                'plan_key': plan_key,
                'plan_type': plan['plan_type'],
                'billing_interval': plan['billing_interval'],
                'display_name': plan['display_name'],
                'price_label': plan['price_label'],
                'annual_discount_label': plan.get('annual_discount_label'),
                'stripe_price_env': plan['stripe_price_env'],
                'stripe_price_configured': bool(stripe_price_id),
                'voice_enabled': plan['voice_enabled'],
            })
        return records

    async def billing_status(self, parent_id: str, email: str) -> dict:
        trial_record = await self._trial_history_for_email(email)
        children = await self.list_child_access(parent_id, email=email)
        family_discount = await self._family_discount_summary(parent_id)
        coupon_redemptions = await self._coupon_redemptions_for_parent(parent_id)
        return {
            'parent_id': parent_id,
            'email': self._normalize_email(email),
            'trial_available': trial_record is None,
            'paid_checkout_required': trial_record is not None,
            'trial_blocked_reason': 'trial_already_used' if trial_record else None,
            'children': children,
            'plans': self.plans(),
            'family_discount': family_discount,
            'coupon_redemptions': coupon_redemptions,
        }

    async def list_child_access(self, parent_id: str, email: str | None = None) -> list[dict]:
        children = await self._children(parent_id)
        await self._sync_stripe_subscriptions_for_parent(parent_id)
        access_rows = await self._access_rows(parent_id)
        access_by_child = {row['child_id']: row for row in access_rows}

        records: list[dict] = []
        for child in children:
            access = access_by_child.get(child['id'])
            if not access:
                access = await self._create_default_access(parent_id, child, email=email)
            records.append(self._merge(child, access))
        return records

    async def update_child_access(self, parent_id: str, child_id: str, payload: ChildAccessUpdateRequest, email: str | None = None) -> dict:
        if payload.access_status in {'active', 'past_due'}:
            raise HTTPException(status_code=403, detail='This billing action is handled by admin billing tools.')
        if payload.access_status == 'trial':
            if not email:
                raise HTTPException(status_code=400, detail='Parent email is required to start a trial.')
            return (await self.start_trial(parent_id, email, child_id, payload.plan_key))['child']
        child = await self._child(parent_id, child_id)
        access = await self._access_for_child(parent_id, child_id)
        if payload.access_status == 'inactive' and self._has_current_paid_access(access):
            return await self._schedule_paid_access_pause(parent_id, child_id, child, access)
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
            update['access_paused_reason'] = 'manual_pause'

        try:
            records = await self.supabase.update('child_access', {
                'parent_id': f'eq.{parent_id}',
                'child_id': f'eq.{child_id}',
            }, update)
        except SupabaseClientError as exc:
            if self._missing_access_table(exc):
                raise HTTPException(status_code=503, detail='Child access billing table is not set up yet. Please run the Supabase migration first.') from exc
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

        if not records:
            records = [await self._create_default_access(parent_id, child, update)]
        return self._merge(child, records[0])

    async def resume_child_access(self, parent_id: str, child_id: str) -> dict:
        child = await self._child(parent_id, child_id)
        access_rows = await self._access_rows(parent_id)
        access = next((row for row in access_rows if row.get('child_id') == child_id), None)
        if not access:
            raise HTTPException(status_code=409, detail='Please choose a plan to resume classroom access.')

        now = datetime.now(UTC)
        current_period_end = self._parse_iso_datetime(access.get('current_period_ends_at'))
        trial_end = self._parse_iso_datetime(access.get('trial_ends_at'))
        if current_period_end and current_period_end > now:
            next_status = 'active'
        elif trial_end and trial_end > now:
            next_status = 'trial'
        else:
            raise HTTPException(status_code=409, detail='Please choose a plan to resume classroom access.')

        update = {
            'access_status': next_status,
            'access_paused_reason': None,
            'cancel_at_period_end': False,
            'updated_at': now.isoformat(),
        }
        subscription_id = access.get('stripe_subscription_id')
        if subscription_id and access.get('cancel_at_period_end'):
            await self._resume_paid_subscription(parent_id, subscription_id)
        try:
            records = await self.supabase.update('child_access', {
                'parent_id': f'eq.{parent_id}',
                'child_id': f'eq.{child_id}',
            }, update)
        except SupabaseClientError as exc:
            if self._missing_access_table(exc):
                raise HTTPException(status_code=503, detail='Child access billing table is not set up yet. Please run the Supabase migration first.') from exc
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        if not records:
            raise HTTPException(status_code=500, detail='Could not resume classroom access.')
        return self._merge(child, records[0])

    async def _schedule_paid_access_pause(self, parent_id: str, child_id: str, child: dict, access: dict) -> dict:
        subscription_id = access.get('stripe_subscription_id')
        if not subscription_id:
            raise HTTPException(status_code=409, detail='Please use billing checkout or the payment portal to manage this access.')
        shared_count = await self._subscription_child_access_count(subscription_id)
        if shared_count > 1:
            raise HTTPException(
                status_code=409,
                detail='This subscription covers multiple children. Please use Manage Payment Method to adjust the shared subscription.',
            )
        stripe = self._stripe_module()
        try:
            await anyio.to_thread.run_sync(lambda: stripe.Subscription.modify(subscription_id, cancel_at_period_end=True))
        except Exception as exc:
            logger.warning('Could not schedule Stripe subscription pause for child %s: %s', child_id, exc)
            raise HTTPException(status_code=503, detail='Could not schedule this subscription change right now. Please try again.') from exc

        now = datetime.now(UTC).isoformat()
        update = {
            'access_status': 'active',
            'access_paused_reason': 'pause_at_period_end',
            'cancel_at_period_end': True,
            'updated_at': now,
        }
        try:
            records = await self.supabase.update('child_access', {
                'parent_id': f'eq.{parent_id}',
                'child_id': f'eq.{child_id}',
            }, update)
            await self.supabase.update('billing_subscriptions', {'stripe_subscription_id': f'eq.{subscription_id}'}, {
                'cancel_at_period_end': True,
                'updated_at': now,
            })
        except SupabaseClientError as exc:
            if self._missing_cancel_at_period_end_column(exc):
                raise HTTPException(status_code=503, detail='Subscription pause support is not set up yet. Please run the Supabase migration first.') from exc
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        if not records:
            raise HTTPException(status_code=500, detail='Could not schedule access pause.')
        return self._merge(child, records[0])

    async def _resume_paid_subscription(self, parent_id: str, subscription_id: str) -> None:
        stripe = self._stripe_module()
        try:
            await anyio.to_thread.run_sync(lambda: stripe.Subscription.modify(subscription_id, cancel_at_period_end=False))
        except Exception as exc:
            logger.warning('Could not resume Stripe subscription %s for parent %s: %s', subscription_id, parent_id, exc)
            raise HTTPException(status_code=503, detail='Could not resume this subscription right now. Please try again.') from exc
        try:
            await self.supabase.update('billing_subscriptions', {'stripe_subscription_id': f'eq.{subscription_id}'}, {
                'cancel_at_period_end': False,
                'updated_at': datetime.now(UTC).isoformat(),
            })
        except SupabaseClientError as exc:
            if not self._missing_milestone2_table(exc):
                raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    async def prepare_classroom_access(self, parent_id: str, child_id: str) -> dict | None:
        child = await self._child(parent_id, child_id)
        access = await self._access_for_child(parent_id, child_id)
        if self._has_current_access(access):
            return self._merge(child, access)

        parent_email = await self._parent_email(parent_id)
        if not parent_email:
            return None
        if await self._trial_history_for_email(parent_email):
            return self._merge(child, access) if access else None

        try:
            return (await self.start_trial(parent_id, parent_email, child_id))['child']
        except HTTPException as exc:
            if exc.status_code == 409:
                access = await self._access_for_child(parent_id, child_id)
                return self._merge(child, access) if access else None
            raise

    async def start_trial(self, parent_id: str, email: str, child_id: str, plan_key: PlanKey = 'text_monthly') -> dict:
        child = await self._child(parent_id, child_id)
        normalized_email = self._normalize_email(email)
        if not normalized_email:
            raise HTTPException(status_code=400, detail='Parent email is required to start a trial.')
        existing_trial = await self._trial_history_for_email(normalized_email)
        if existing_trial:
            raise HTTPException(status_code=409, detail='This email has already used its free trial.')

        plan = self._plan(plan_key)
        now = datetime.now(UTC)
        trial_ends_at = now + timedelta(days=TRIAL_DAYS)
        trial_payload = {
            'parent_id': parent_id,
            'email': normalized_email,
            'child_id': child_id,
            'trial_started_at': now.isoformat(),
            'trial_ends_at': trial_ends_at.isoformat(),
            'source': 'billing_trial_start',
            'metadata': {'plan_key': plan_key},
        }
        access_payload = {
            'parent_id': parent_id,
            'child_id': child_id,
            'access_status': 'trial',
            'plan_name': plan['display_name'],
            'plan_type': plan['plan_type'],
            'billing_interval': plan['billing_interval'],
            'trial_started_at': now.isoformat(),
            'trial_ends_at': trial_ends_at.isoformat(),
            'current_period_ends_at': None,
            'updated_at': now.isoformat(),
        }

        try:
            await self.supabase.insert('parent_trial_history', trial_payload)
            records = await self.supabase.upsert('child_access', {
                **access_payload,
                'created_at': now.isoformat(),
            }, 'child_id')
        except SupabaseClientError as exc:
            if self._duplicate_trial_error(exc):
                raise HTTPException(status_code=409, detail='This email has already used its free trial.') from exc
            if self._missing_milestone2_table(exc):
                raise HTTPException(status_code=503, detail='Milestone 2 billing tables are not set up yet. Please run the Supabase migration first.') from exc
            if self._missing_plan_columns(exc):
                fallback = {key: value for key, value in access_payload.items() if key not in {'plan_type', 'billing_interval', 'trial_started_at'}}
                records = await self.supabase.upsert('child_access', {**fallback, 'created_at': now.isoformat()}, 'child_id')
            else:
                raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

        if not records:
            raise HTTPException(status_code=500, detail='Could not start trial access.')
        child_access = self._merge(child, records[0])
        await self._send_trial_started_parent_email(
            parent_id=parent_id,
            parent_email=normalized_email,
            child_id=child_id,
            trial_started_at=now.isoformat(),
            trial_ends_at=trial_ends_at.isoformat(),
        )
        await self._send_trial_started_alert(
            parent_id=parent_id,
            parent_email=normalized_email,
            child=child,
            plan=plan,
            trial_started_at=now.isoformat(),
            trial_ends_at=trial_ends_at.isoformat(),
        )
        return {
            'child': child_access,
            'trial_started_at': now.isoformat(),
            'trial_ends_at': trial_ends_at.isoformat(),
            'trial_available': False,
            'message': 'Free trial started.',
        }

    async def create_checkout_session(self, parent_id: str, email: str, child_id: str, plan_key: PlanKey, coupon_code: str | None = None) -> dict:
        stripe = self._stripe_module()
        child = await self._child(parent_id, child_id)
        await self._ensure_child_can_checkout(parent_id, child_id)
        plan = self._plan(plan_key)
        stripe_price_id = self._stripe_price_id(plan)
        customer_id = await self._get_or_create_stripe_customer(parent_id, email)
        family_discount = await self._family_discount_state(parent_id)
        coupon = await self._validate_coupon_code(stripe, coupon_code)

        checkout_payload = {
            'mode': 'subscription',
            'customer': customer_id,
            'line_items': [{'price': stripe_price_id, 'quantity': 1}],
            'success_url': self.settings.stripe_success_url or 'http://localhost:5173/billing/success',
            'cancel_url': self.settings.stripe_cancel_url or 'http://localhost:5173/billing/cancel',
            'client_reference_id': child_id,
            'subscription_data': {
                'metadata': {
                    'parent_id': parent_id,
                    'child_id': child_id,
                    'plan_key': plan_key,
                    'plan_type': plan['plan_type'],
                    'billing_interval': plan['billing_interval'],
                },
            },
            'metadata': {
                'parent_id': parent_id,
                'child_id': child_id,
                'child_name': child.get('name', ''),
                'plan_key': plan_key,
                'plan_type': plan['plan_type'],
                'billing_interval': plan['billing_interval'],
                'family_discount_checkout_eligible': str(bool(family_discount['checkout_eligible'])).lower(),
            },
        }
        if coupon:
            checkout_payload['discounts'] = [{'promotion_code': coupon['promotion_code_id']}]
            checkout_payload['metadata']['coupon_code'] = coupon['coupon_code']
            checkout_payload['subscription_data']['metadata']['coupon_code'] = coupon['coupon_code']
        elif family_discount['checkout_eligible'] and self.settings.stripe_family_discount_coupon_id:
            checkout_payload['discounts'] = [{'coupon': self.settings.stripe_family_discount_coupon_id}]
            checkout_payload['metadata']['family_discount_applied'] = 'true'
            checkout_payload['subscription_data']['metadata']['family_discount_applied'] = 'true'
        elif family_discount['checkout_eligible']:
            logger.warning('Family discount eligible for parent %s but STRIPE_FAMILY_DISCOUNT_COUPON_ID is not configured.', parent_id)
            checkout_payload['allow_promotion_codes'] = True
        else:
            checkout_payload['allow_promotion_codes'] = True

        session = await self._create_stripe_checkout_session(stripe, checkout_payload)
        if coupon:
            await self._record_coupon_redemption(parent_id, child_id, coupon, 'valid', payment_reference=session.id, metadata={
                'plan_key': plan_key,
                'checkout_session_id': session.id,
            })
        return {
            'checkout_url': session.url,
            'session_id': session.id,
        }

    async def create_bulk_checkout_session(self, parent_id: str, email: str, selections: list[dict], coupon_code: str | None = None) -> dict:
        stripe = self._stripe_module()
        if not selections:
            raise HTTPException(status_code=422, detail='Choose at least one child to subscribe.')
        if len(selections) > 10:
            raise HTTPException(status_code=422, detail='Please choose 10 or fewer children for one checkout.')

        normalized: list[dict] = []
        seen_children: set[str] = set()
        for item in selections:
            child_id = str(item.get('child_id') or '').strip()
            plan_key = str(item.get('plan_key') or '').strip()
            if not child_id or child_id in seen_children:
                continue
            child = await self._child(parent_id, child_id)
            await self._ensure_child_can_checkout(parent_id, child_id)
            plan = self._plan(plan_key)
            normalized.append({'child': child, 'child_id': child_id, 'plan_key': plan_key, 'plan': plan})
            seen_children.add(child_id)

        if not normalized:
            raise HTTPException(status_code=422, detail='Choose at least one child to subscribe.')

        customer_id = await self._get_or_create_stripe_customer(parent_id, email)
        family_discount = await self._family_discount_state(parent_id, pending_checkout_count=len(normalized))
        coupon = await self._validate_coupon_code(stripe, coupon_code)
        child_plan_map = self._encode_child_plan_map(normalized)
        child_names = ', '.join(item['child'].get('name', 'Child') for item in normalized[:5])
        if len(normalized) > 5:
            child_names = f'{child_names}, and {len(normalized) - 5} more'

        checkout_payload = {
            'mode': 'subscription',
            'customer': customer_id,
            'line_items': self._checkout_line_items(normalized),
            'success_url': self.settings.stripe_success_url or 'http://localhost:5173/billing/success',
            'cancel_url': self.settings.stripe_cancel_url or 'http://localhost:5173/billing/cancel',
            'client_reference_id': f'bulk:{normalized[0]["child_id"]}',
            'subscription_data': {
                'metadata': {
                    'parent_id': parent_id,
                    'checkout_mode': 'multi_child',
                    'child_plan_map': child_plan_map,
                    'child_count': str(len(normalized)),
                },
            },
            'metadata': {
                'parent_id': parent_id,
                'checkout_mode': 'multi_child',
                'child_plan_map': child_plan_map,
                'child_count': str(len(normalized)),
                'child_names': child_names,
                'family_discount_checkout_eligible': str(bool(family_discount['checkout_eligible'])).lower(),
            },
        }
        if coupon:
            checkout_payload['discounts'] = [{'promotion_code': coupon['promotion_code_id']}]
            checkout_payload['metadata']['coupon_code'] = coupon['coupon_code']
            checkout_payload['subscription_data']['metadata']['coupon_code'] = coupon['coupon_code']
        elif family_discount['checkout_eligible'] and self.settings.stripe_family_discount_coupon_id:
            checkout_payload['discounts'] = [{'coupon': self.settings.stripe_family_discount_coupon_id}]
            checkout_payload['metadata']['family_discount_applied'] = 'true'
            checkout_payload['subscription_data']['metadata']['family_discount_applied'] = 'true'
        elif family_discount['checkout_eligible']:
            logger.warning('Family discount eligible for parent %s but STRIPE_FAMILY_DISCOUNT_COUPON_ID is not configured.', parent_id)
            checkout_payload['allow_promotion_codes'] = True
        else:
            checkout_payload['allow_promotion_codes'] = True

        session = await self._create_stripe_checkout_session(stripe, checkout_payload)
        if coupon:
            for item in normalized:
                await self._record_coupon_redemption(parent_id, item['child_id'], coupon, 'valid', payment_reference=session.id, metadata={
                    'plan_key': item['plan_key'],
                    'checkout_session_id': session.id,
                    'checkout_mode': 'multi_child',
                })
        return {
            'checkout_url': session.url,
            'session_id': session.id,
        }

    async def create_customer_portal_session(self, parent_id: str, email: str, child_id: str | None = None) -> dict:
        stripe = self._stripe_module()
        if child_id:
            await self._child(parent_id, child_id)
        customer_id = await self._stripe_customer_id_for_parent(parent_id)
        if customer_id and not await self._stripe_customer_exists(stripe, customer_id):
            customer_id = None
        if not customer_id:
            customer_id = await self._get_or_create_stripe_customer(parent_id, email)
        portal_session = await anyio.to_thread.run_sync(lambda: stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=self.settings.stripe_customer_portal_return_url or 'http://localhost:5173/billing',
        ))
        return {
            'portal_url': portal_session.url,
            'session_id': portal_session.id,
        }

    async def handle_stripe_webhook(self, payload: bytes, stripe_signature: str) -> dict:
        stripe = self._stripe_module(require_webhook_secret=True)
        try:
            event = stripe.Webhook.construct_event(payload, stripe_signature, self.settings.stripe_webhook_secret)
        except Exception as exc:
            raise HTTPException(status_code=400, detail='Invalid Stripe webhook signature.') from exc

        event_data = self._stripe_to_dict(event)
        event_id = event_data.get('id')
        event_type = event_data.get('type')
        if not event_id or not event_type:
            raise HTTPException(status_code=400, detail='Stripe webhook event is missing id or type.')

        existing_event = await self._stripe_event(event_id)
        if existing_event and existing_event.get('processing_status') == 'processed':
            return {'received': True, 'event_id': event_id, 'event_type': event_type, 'status': 'duplicate'}
        if not existing_event:
            await self._record_stripe_event(event_data, 'pending')

        try:
            await self._process_stripe_event(event_data)
        except Exception as exc:
            await self._mark_stripe_event(event_id, 'failed', str(exc))
            raise

        await self._mark_stripe_event(event_id, 'processed')
        return {'received': True, 'event_id': event_id, 'event_type': event_type, 'status': 'processed'}

    async def expire_unpaid_grace_periods(self) -> dict:
        now = datetime.now(UTC)
        checked_at = now.isoformat()
        try:
            rows = await self.supabase.select(
                'child_access',
                f'grace_period_ends_at=lt.{quote(checked_at)}&access_status=eq.active&order=grace_period_ends_at.asc&limit=500',
            )
        except SupabaseClientError as exc:
            if self._missing_access_table(exc) or self._missing_plan_columns(exc):
                return {'paused_count': 0, 'checked_at': checked_at}
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

        paused_count = 0
        for row in rows:
            child_id = row.get('child_id')
            if not child_id:
                continue
            await self.supabase.update('child_access', {'child_id': f'eq.{child_id}'}, {
                'access_status': 'inactive',
                'access_paused_reason': 'payment_failed_grace_expired',
                'updated_at': checked_at,
            })
            paused_count += 1
        return {'paused_count': paused_count, 'checked_at': checked_at}

    async def _process_stripe_event(self, event: dict) -> None:
        event_type = event.get('type')
        obj = ((event.get('data') or {}).get('object') or {})
        if event_type == 'checkout.session.completed':
            await self._handle_checkout_completed(obj)
        elif event_type in {'customer.subscription.created', 'customer.subscription.updated'}:
            await self._handle_subscription_upsert(obj)
        elif event_type == 'customer.subscription.deleted':
            await self._handle_subscription_deleted(obj)
        elif event_type == 'invoice.paid':
            await self._handle_invoice_paid(obj)
        elif event_type == 'invoice.payment_failed':
            await self._handle_invoice_payment_failed(obj)
        elif event_type == 'payment_intent.succeeded':
            await self._record_financial_event_from_payment_intent(obj, 'payment_intent.succeeded')
        elif event_type == 'payment_intent.payment_failed':
            await self._record_financial_event_from_payment_intent(obj, 'payment_intent.payment_failed')
        else:
            logger.info('Stored unhandled Stripe event type: %s', event_type)

    async def _handle_checkout_completed(self, session: dict) -> None:
        subscription_id = self._stripe_id(session.get('subscription'))
        if subscription_id:
            subscription = await self._retrieve_subscription(subscription_id)
            await self._handle_subscription_upsert(subscription, checkout_session=session)

    async def _handle_subscription_upsert(self, subscription: dict, checkout_session: dict | None = None) -> None:
        subscription_id = self._stripe_id(subscription.get('id'))
        customer_id = self._stripe_id(subscription.get('customer')) or self._stripe_id((checkout_session or {}).get('customer'))
        metadata = {**(subscription.get('metadata') or {}), **((checkout_session or {}).get('metadata') or {})}
        if metadata.get('checkout_mode') == 'multi_child' or metadata.get('child_plan_map'):
            await self._handle_multi_child_subscription_upsert(subscription, checkout_session=checkout_session, metadata=metadata)
            return
        parent_id = metadata.get('parent_id')
        child_id = metadata.get('child_id') or (checkout_session or {}).get('client_reference_id')
        plan_key = self._plan_key_from_price(subscription) or metadata.get('plan_key')
        if not subscription_id or not customer_id or not parent_id or not child_id or not plan_key:
            logger.warning('Stripe subscription sync skipped due to missing metadata: subscription=%s parent=%s child=%s plan=%s', subscription_id, parent_id, child_id, plan_key)
            return

        plan = self._plan(plan_key)
        status = subscription.get('status') or 'incomplete'
        now = datetime.now(UTC).isoformat()
        current_period_start = self._subscription_period_timestamp(subscription, 'current_period_start')
        current_period_end = self._subscription_period_timestamp(subscription, 'current_period_end')
        trial_start = self._stripe_timestamp(subscription.get('trial_start'))
        trial_end = self._stripe_timestamp(subscription.get('trial_end'))
        access_status = self._access_status_from_subscription(status)
        latest_invoice_id = self._stripe_id(subscription.get('latest_invoice'))

        existing_access = await self._child_access_for_child(child_id)
        original_due = existing_access.get('original_billing_due_at') if existing_access else None
        if not original_due:
            original_due = current_period_end

        billing_payload = {
            'parent_id': parent_id,
            'child_id': child_id,
            'stripe_customer_id': customer_id,
            'stripe_subscription_id': subscription_id,
            'stripe_price_id': self._subscription_price_id(subscription),
            'stripe_latest_invoice_id': latest_invoice_id,
            'plan_type': plan['plan_type'],
            'billing_interval': plan['billing_interval'],
            'subscription_status': status if status in self._subscription_statuses() else 'incomplete',
            'trial_started_at': trial_start,
            'trial_ends_at': trial_end,
            'original_billing_due_at': original_due,
            'current_period_started_at': current_period_start,
            'current_period_ends_at': current_period_end,
            'cancel_at_period_end': bool(subscription.get('cancel_at_period_end')),
            'canceled_at': self._stripe_timestamp(subscription.get('canceled_at')),
            'metadata': metadata,
            'updated_at': now,
        }
        await self._upsert_billing_subscription(billing_payload)

        access_payload = {
            'parent_id': parent_id,
            'child_id': child_id,
            'access_status': access_status,
            'plan_name': plan['display_name'],
            'plan_type': plan['plan_type'],
            'billing_interval': plan['billing_interval'],
            'stripe_customer_id': customer_id,
            'stripe_subscription_id': subscription_id,
            'stripe_price_id': billing_payload['stripe_price_id'],
            'trial_started_at': trial_start,
            'trial_ends_at': trial_end,
            'current_period_started_at': current_period_start,
            'current_period_ends_at': current_period_end,
            'original_billing_due_at': original_due,
            'cancel_at_period_end': bool(subscription.get('cancel_at_period_end')),
            'grace_period_started_at': None if access_status == 'active' else (existing_access or {}).get('grace_period_started_at'),
            'grace_period_ends_at': None if access_status == 'active' else (existing_access or {}).get('grace_period_ends_at'),
            'access_paused_reason': 'pause_at_period_end' if subscription.get('cancel_at_period_end') and access_status == 'active' else (None if access_status == 'active' else self._pause_reason_for_status(status)),
            'latest_invoice_id': latest_invoice_id,
            'updated_at': now,
        }
        await self.supabase.upsert('child_access', {**access_payload, 'created_at': now}, 'child_id')
        await self._queue_annual_renewal_email(parent_id, child_id, customer_id, billing_payload)

    async def _handle_multi_child_subscription_upsert(self, subscription: dict, checkout_session: dict | None, metadata: dict) -> None:
        subscription_id = self._stripe_id(subscription.get('id'))
        customer_id = self._stripe_id(subscription.get('customer')) or self._stripe_id((checkout_session or {}).get('customer'))
        parent_id = metadata.get('parent_id')
        selections = self._decode_child_plan_map(metadata.get('child_plan_map') or '')
        if not subscription_id or not customer_id or not parent_id or not selections:
            logger.warning('Stripe multi-child subscription sync skipped due to missing metadata: subscription=%s parent=%s children=%s', subscription_id, parent_id, len(selections))
            return

        status = subscription.get('status') or 'incomplete'
        now = datetime.now(UTC).isoformat()
        current_period_start = self._subscription_period_timestamp(subscription, 'current_period_start')
        current_period_end = self._subscription_period_timestamp(subscription, 'current_period_end')
        trial_start = self._stripe_timestamp(subscription.get('trial_start'))
        trial_end = self._stripe_timestamp(subscription.get('trial_end'))
        access_status = self._access_status_from_subscription(status)
        latest_invoice_id = self._stripe_id(subscription.get('latest_invoice'))
        first_selection = selections[0]
        first_plan = self._plan(first_selection['plan_key'])
        billing_payload = {
            'parent_id': parent_id,
            'child_id': first_selection['child_id'],
            'stripe_customer_id': customer_id,
            'stripe_subscription_id': subscription_id,
            'stripe_price_id': self._subscription_price_id(subscription),
            'stripe_latest_invoice_id': latest_invoice_id,
            'plan_type': first_plan['plan_type'],
            'billing_interval': first_plan['billing_interval'],
            'subscription_status': status if status in self._subscription_statuses() else 'incomplete',
            'trial_started_at': trial_start,
            'trial_ends_at': trial_end,
            'original_billing_due_at': current_period_end,
            'current_period_started_at': current_period_start,
            'current_period_ends_at': current_period_end,
            'cancel_at_period_end': bool(subscription.get('cancel_at_period_end')),
            'canceled_at': self._stripe_timestamp(subscription.get('canceled_at')),
            'metadata': {**metadata, 'multi_child_subscription': True},
            'updated_at': now,
        }
        await self._upsert_billing_subscription(billing_payload)

        for selection in selections:
            child_id = selection['child_id']
            plan = self._plan(selection['plan_key'])
            child = await self._child(parent_id, child_id)
            existing_access = await self._child_access_for_child(child_id)
            original_due = (existing_access or {}).get('original_billing_due_at') or current_period_end
            access_payload = {
                'parent_id': parent_id,
                'child_id': child_id,
                'access_status': access_status,
                'plan_name': plan['display_name'],
                'plan_type': plan['plan_type'],
                'billing_interval': plan['billing_interval'],
                'stripe_customer_id': customer_id,
                'stripe_subscription_id': subscription_id,
                'stripe_price_id': self._stripe_price_id(plan),
                'trial_started_at': trial_start,
                'trial_ends_at': trial_end,
                'current_period_started_at': current_period_start,
                'current_period_ends_at': current_period_end,
                'original_billing_due_at': original_due,
                'cancel_at_period_end': bool(subscription.get('cancel_at_period_end')),
                'grace_period_started_at': None if access_status == 'active' else (existing_access or {}).get('grace_period_started_at'),
                'grace_period_ends_at': None if access_status == 'active' else (existing_access or {}).get('grace_period_ends_at'),
                'access_paused_reason': 'pause_at_period_end' if subscription.get('cancel_at_period_end') and access_status == 'active' else (None if access_status == 'active' else self._pause_reason_for_status(status)),
                'latest_invoice_id': latest_invoice_id,
                'updated_at': now,
            }
            await self.supabase.upsert('child_access', {**access_payload, 'created_at': now}, 'child_id')
            await self._queue_annual_renewal_email(parent_id, child_id, customer_id, {
                **billing_payload,
                'child_id': child_id,
                'plan_type': plan['plan_type'],
                'billing_interval': plan['billing_interval'],
            })
            logger.info('Synced multi-child subscription %s for child %s (%s).', subscription_id, child_id, child.get('name'))

    async def _handle_subscription_deleted(self, subscription: dict) -> None:
        subscription_id = self._stripe_id(subscription.get('id'))
        if not subscription_id:
            return
        metadata = subscription.get('metadata') or {}
        billing_row = await self._billing_subscription_for_subscription(subscription_id)
        parent_id = metadata.get('parent_id') or (billing_row or {}).get('parent_id')
        child_id = metadata.get('child_id') or (billing_row or {}).get('child_id')
        now = datetime.now(UTC).isoformat()
        await self.supabase.update('billing_subscriptions', {'stripe_subscription_id': f'eq.{subscription_id}'}, {
            'subscription_status': 'canceled',
            'canceled_at': self._stripe_timestamp(subscription.get('canceled_at')) or now,
            'updated_at': now,
        })
        await self.supabase.update('child_access', {'stripe_subscription_id': f'eq.{subscription_id}'}, {
            'access_status': 'inactive',
            'access_paused_reason': 'subscription_canceled',
            'cancel_at_period_end': False,
            'updated_at': now,
        })
        if parent_id:
            await self._send_subscription_canceled_alert(
                parent_id=parent_id,
                child_id=child_id,
                subscription_id=subscription_id,
                status='canceled',
                canceled_at=self._stripe_timestamp(subscription.get('canceled_at')) or now,
            )

    async def _handle_invoice_paid(self, invoice: dict) -> None:
        subscription_id = self._stripe_id(invoice.get('subscription'))
        subscription = None
        if subscription_id:
            subscription = await self._retrieve_subscription(subscription_id)
            await self._handle_subscription_upsert(subscription)
        await self._queue_payment_success_email(invoice, subscription)
        await self._record_financial_event_from_invoice(invoice, 'invoice.paid')

    async def _handle_invoice_payment_failed(self, invoice: dict) -> None:
        now = datetime.now(UTC)
        grace_ends = now + timedelta(days=1)
        subscription_id = self._stripe_id(invoice.get('subscription'))
        if subscription_id:
            await self.supabase.update('billing_subscriptions', {'stripe_subscription_id': f'eq.{subscription_id}'}, {
                'subscription_status': 'past_due',
                'stripe_latest_invoice_id': self._stripe_id(invoice.get('id')),
                'stripe_latest_payment_intent_id': self._stripe_id(invoice.get('payment_intent')),
                'grace_period_started_at': now.isoformat(),
                'grace_period_ends_at': grace_ends.isoformat(),
                'updated_at': now.isoformat(),
            })
            await self.supabase.update('child_access', {'stripe_subscription_id': f'eq.{subscription_id}'}, {
                'access_status': 'active',
                'latest_invoice_id': self._stripe_id(invoice.get('id')),
                'latest_payment_intent_id': self._stripe_id(invoice.get('payment_intent')),
                'grace_period_started_at': now.isoformat(),
                'grace_period_ends_at': grace_ends.isoformat(),
                'cancel_at_period_end': False,
                'access_paused_reason': None,
                'updated_at': now.isoformat(),
            })
        await self._queue_payment_failed_email(invoice)
        await self._record_financial_event_from_invoice(invoice, 'invoice.payment_failed')

    async def sync_all_stripe_subscriptions(self, limit: int = 100) -> dict:
        stripe = self._stripe_module()
        limit = max(1, min(limit, 100))
        synced_count = 0
        skipped_count = 0
        failed_count = 0
        has_more = False
        starting_after = None

        while True:
            def list_page():
                params = {'status': 'all', 'limit': limit}
                if starting_after:
                    params['starting_after'] = starting_after
                return stripe.Subscription.list(**params)

            page = await anyio.to_thread.run_sync(list_page)
            page_data = self._stripe_to_dict(page)
            subscriptions = page_data.get('data') or []
            has_more = bool(page_data.get('has_more'))
            if not subscriptions:
                break

            for subscription in subscriptions:
                subscription_dict = self._stripe_to_dict(subscription)
                if subscription_dict.get('status') not in self._subscription_statuses():
                    skipped_count += 1
                    continue
                metadata = subscription_dict.get('metadata') or {}
                if not metadata.get('parent_id') or not (metadata.get('child_id') or metadata.get('child_plan_map')):
                    skipped_count += 1
                    continue
                try:
                    await self._handle_subscription_upsert(subscription_dict)
                    synced_count += 1
                except Exception as exc:
                    failed_count += 1
                    logger.warning('Could not sync Stripe subscription %s during full sync: %s', subscription_dict.get('id'), exc)

            if not has_more:
                break
            starting_after = self._stripe_id(subscriptions[-1].get('id'))
            if not starting_after:
                break

        return {
            'synced_count': synced_count,
            'skipped_count': skipped_count,
            'failed_count': failed_count,
            'has_more': has_more,
            'message': 'Stripe subscriptions sync completed.',
        }

    async def _sync_stripe_subscriptions_for_parent(self, parent_id: str) -> None:
        if not self.settings.stripe_secret_key:
            return
        stripe = self._stripe_module()
        customer_id = await self._stripe_customer_id_for_parent(parent_id)
        if not customer_id:
            return
        if not await self._stripe_customer_exists(stripe, customer_id):
            return
        try:
            subscriptions = await anyio.to_thread.run_sync(lambda: stripe.Subscription.list(
                customer=customer_id,
                status='all',
                limit=20,
            ))
        except Exception as exc:
            logger.warning('Could not sync Stripe subscriptions for parent %s: %s', parent_id, exc)
            return
        data = self._stripe_to_dict(subscriptions).get('data') or []
        for subscription in data:
            subscription_dict = self._stripe_to_dict(subscription)
            if subscription_dict.get('status') not in self._subscription_statuses():
                continue
            metadata = subscription_dict.get('metadata') or {}
            if metadata.get('parent_id') != parent_id or not (metadata.get('child_id') or metadata.get('child_plan_map')):
                continue
            try:
                await self._handle_subscription_upsert(subscription_dict)
            except Exception as exc:
                logger.warning('Could not sync Stripe subscription %s for parent %s: %s', subscription_dict.get('id'), parent_id, exc)

    async def _children(self, parent_id: str) -> list[dict]:
        try:
            return await self.supabase.select(
                'child_profiles',
                f'parent_id=eq.{quote(parent_id)}&status=neq.inactive&order=created_at.asc',
            )
        except SupabaseClientError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    async def _child(self, parent_id: str, child_id: str) -> dict:
        try:
            records = await self.supabase.select(
                'child_profiles',
                f'id=eq.{quote(child_id)}&parent_id=eq.{quote(parent_id)}&status=neq.inactive&limit=1',
            )
        except SupabaseClientError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        if not records:
            raise HTTPException(status_code=404, detail='Child profile not found.')
        return records[0]

    async def _access_rows(self, parent_id: str) -> list[dict]:
        try:
            return await self.supabase.select(
                'child_access',
                f'parent_id=eq.{quote(parent_id)}&order=created_at.asc',
            )
        except SupabaseClientError as exc:
            if self._missing_access_table(exc):
                raise HTTPException(status_code=503, detail='Child access billing table is not set up yet. Please run the Supabase migration first.') from exc
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    async def _access_for_child(self, parent_id: str, child_id: str) -> dict | None:
        try:
            records = await self.supabase.select(
                'child_access',
                f'parent_id=eq.{quote(parent_id)}&child_id=eq.{quote(child_id)}&limit=1',
            )
        except SupabaseClientError as exc:
            if self._missing_access_table(exc):
                raise HTTPException(status_code=503, detail='Child access billing table is not set up yet. Please run the Supabase migration first.') from exc
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        return records[0] if records else None

    async def _create_default_access(self, parent_id: str, child: dict, override: dict | None = None, email: str | None = None) -> dict:
        now = datetime.now(UTC)
        access_status = 'inactive'
        payload = {
            'parent_id': parent_id,
            'child_id': child['id'],
            'access_status': access_status,
            'plan_name': 'No paid plan selected',
            'trial_ends_at': None,
            'current_period_ends_at': None,
            'created_at': now.isoformat(),
            'updated_at': now.isoformat(),
        }
        if override:
            payload.update(override)
        try:
            records = await self.supabase.upsert('child_access', payload, 'child_id')
        except SupabaseClientError as exc:
            if self._missing_access_table(exc):
                raise HTTPException(status_code=503, detail='Child access billing table is not set up yet. Please run the Supabase migration first.') from exc
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        if not records:
            raise HTTPException(status_code=500, detail='Could not create child access record.')
        return records[0]

    def _merge(self, child: dict, access: dict) -> dict:
        plan_type = access.get('plan_type')
        voice_enabled = access.get('access_status') == 'active' and plan_type == 'voice'
        return {
            **access,
            'child_name': child['name'],
            'grade_level': child['grade_level'],
            'access_status': access.get('access_status') or 'inactive',
            'plan_name': access.get('plan_name') or 'Phase 1 MVP',
            'plan_type': plan_type,
            'billing_interval': access.get('billing_interval'),
            'cancel_at_period_end': bool(access.get('cancel_at_period_end')),
            'voice_enabled': voice_enabled,
            'voice_allowed': voice_enabled,
            'feature_mode': 'chat_and_voice' if voice_enabled else 'chat_only',
        }

    def _has_current_access(self, access: dict | None) -> bool:
        if not access:
            return False
        now = datetime.now(UTC)
        status = access.get('access_status')
        if status == 'active':
            period_end = self._parse_iso_datetime(access.get('current_period_ends_at'))
            return period_end is None or period_end > now
        if status == 'trial':
            trial_end = self._parse_iso_datetime(access.get('trial_ends_at'))
            return trial_end is not None and trial_end > now
        return False

    async def _ensure_child_can_checkout(self, parent_id: str, child_id: str) -> None:
        access = await self._access_for_child(parent_id, child_id)
        if not self._has_current_paid_access(access):
            return
        raise HTTPException(
            status_code=409,
            detail='This child already has an active paid subscription for the current billing period.',
        )

    def _has_current_paid_access(self, access: dict | None) -> bool:
        if not access or access.get('access_status') != 'active':
            return False
        if not access.get('stripe_subscription_id'):
            return False
        period_end = self._parse_iso_datetime(access.get('current_period_ends_at'))
        return period_end is None or period_end > datetime.now(UTC)

    def _checkout_line_items(self, selections: list[dict]) -> list[dict]:
        line_items_by_price: dict[str, dict] = {}
        for item in selections:
            price_id = self._stripe_price_id(item['plan'])
            line_item = line_items_by_price.setdefault(price_id, {'price': price_id, 'quantity': 0})
            line_item['quantity'] += 1
        return list(line_items_by_price.values())

    async def _create_stripe_checkout_session(self, stripe, checkout_payload: dict):
        try:
            return await anyio.to_thread.run_sync(lambda: stripe.checkout.Session.create(**checkout_payload))
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception('Stripe checkout session creation failed: %s', exc)
            raise HTTPException(
                status_code=503,
                detail='Could not start Stripe checkout. Please try again or contact support.',
            ) from exc

    def _encode_child_plan_map(self, selections: list[dict]) -> str:
        return '|'.join(f'{item["child_id"]}:{item["plan_key"]}' for item in selections)

    def _decode_child_plan_map(self, value: str) -> list[dict]:
        selections: list[dict] = []
        for raw_item in str(value or '').split('|'):
            if ':' not in raw_item:
                continue
            child_id, plan_key = raw_item.split(':', 1)
            child_id = child_id.strip()
            plan_key = plan_key.strip()
            if child_id and plan_key in PLAN_CATALOG:
                selections.append({'child_id': child_id, 'plan_key': plan_key})
        return selections

    def _missing_access_table(self, exc: SupabaseClientError) -> bool:
        message = str(exc).lower()
        return 'child_access' in message and ('schema cache' in message or 'could not find' in message or 'does not exist' in message)

    async def _trial_history_for_email(self, email: str | None) -> dict | None:
        if not email:
            return None
        try:
            records = await self.supabase.select(
                'parent_trial_history',
                f'normalized_email=eq.{quote(self._normalize_email(email))}&limit=1',
            )
        except SupabaseClientError as exc:
            if self._missing_milestone2_table(exc):
                return None
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        return records[0] if records else None

    def _plan(self, plan_key: str) -> dict:
        plan = PLAN_CATALOG.get(plan_key)
        if not plan:
            raise HTTPException(status_code=422, detail='Unsupported billing plan.')
        return plan

    def _normalize_email(self, email: str) -> str:
        return email.strip().lower()

    def _duplicate_trial_error(self, exc: SupabaseClientError) -> bool:
        message = str(exc).lower()
        return 'parent_trial_history_normalized_email_uidx' in message or 'duplicate key' in message

    def _missing_milestone2_table(self, exc: SupabaseClientError) -> bool:
        message = str(exc).lower()
        return (
            ('parent_trial_history' in message or 'billing_customers' in message or 'billing_discounts' in message)
            and ('schema cache' in message or 'could not find' in message or 'does not exist' in message)
        )

    def _missing_plan_columns(self, exc: SupabaseClientError) -> bool:
        message = str(exc).lower()
        return 'schema cache' in message and any(column in message for column in ['plan_type', 'billing_interval', 'trial_started_at'])

    def _stripe_module(self, require_webhook_secret: bool = False):
        if not self.settings.stripe_secret_key:
            raise HTTPException(status_code=503, detail='Stripe is not configured yet.')
        if require_webhook_secret and not self.settings.stripe_webhook_secret:
            raise HTTPException(status_code=503, detail='Stripe webhook secret is not configured yet.')
        try:
            import stripe
        except ImportError as exc:
            raise HTTPException(status_code=503, detail='Stripe Python package is not installed yet. Run backend dependency installation first.') from exc
        stripe.api_key = self.settings.stripe_secret_key
        return stripe

    def _stripe_price_id(self, plan: dict) -> str:
        stripe_price_id = getattr(self.settings, plan['settings_attr'], '')
        if not stripe_price_id:
            raise HTTPException(status_code=503, detail=f'{plan["stripe_price_env"]} is not configured yet.')
        return stripe_price_id

    async def _get_or_create_stripe_customer(self, parent_id: str, email: str) -> str:
        stripe = self._stripe_module()
        normalized_email = self._normalize_email(email)
        existing_customer_id = await self._stripe_customer_id_for_parent(parent_id)
        if existing_customer_id:
            if await self._stripe_customer_exists(stripe, existing_customer_id):
                return existing_customer_id
            logger.warning(
                'Stored Stripe customer %s is not available with the configured Stripe key; creating a new customer for parent %s.',
                existing_customer_id,
                parent_id,
            )
        if not normalized_email:
            raise HTTPException(status_code=400, detail='Parent email is required for Stripe checkout.')

        customer = await anyio.to_thread.run_sync(lambda: stripe.Customer.create(
            email=normalized_email,
            metadata={'parent_id': parent_id},
        ))
        now = datetime.now(UTC).isoformat()
        try:
            await self.supabase.update('profiles', {'id': f'eq.{parent_id}'}, {
                'stripe_customer_id': customer.id,
                'updated_at': now,
            })
        except SupabaseClientError as exc:
            if not self._missing_profile_stripe_column(exc):
                raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

        try:
            await self.supabase.upsert('billing_customers', {
                'parent_id': parent_id,
                'email': normalized_email,
                'stripe_customer_id': customer.id,
                'updated_at': now,
            }, 'stripe_customer_id')
        except SupabaseClientError as exc:
            if self._missing_milestone2_table(exc):
                logger.warning('billing_customers table is unavailable while creating Stripe customer for parent %s.', parent_id)
            else:
                raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        return customer.id

    async def _stripe_customer_exists(self, stripe, customer_id: str) -> bool:
        try:
            customer = await anyio.to_thread.run_sync(lambda: stripe.Customer.retrieve(customer_id))
        except Exception as exc:
            message = str(exc).lower()
            if 'no such customer' in message or 'similar object exists in live mode' in message or 'similar object exists in test mode' in message:
                return False
            raise
        customer_dict = self._stripe_to_dict(customer)
        return not bool(customer_dict.get('deleted'))

    async def _stripe_customer_id_for_parent(self, parent_id: str) -> str | None:
        try:
            profiles = await self.supabase.select('profiles', f'id=eq.{quote(parent_id)}&select=stripe_customer_id&limit=1')
            if profiles and profiles[0].get('stripe_customer_id'):
                return profiles[0]['stripe_customer_id']
        except SupabaseClientError as exc:
            if not self._missing_profile_stripe_column(exc):
                raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

        try:
            customers = await self.supabase.select('billing_customers', f'parent_id=eq.{quote(parent_id)}&order=created_at.desc&limit=1')
        except SupabaseClientError as exc:
            if self._missing_milestone2_table(exc):
                return None
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        if customers:
            return customers[0].get('stripe_customer_id')
        return None

    async def _family_discount_state(self, parent_id: str, pending_checkout_count: int = 1) -> dict:
        access_rows = await self._access_rows(parent_id)
        active_count = len([row for row in access_rows if row.get('access_status') == 'active'])
        current_eligible = active_count >= 2
        checkout_eligible = active_count + max(1, pending_checkout_count) >= 2
        await self._record_family_discount_state(parent_id, active_count, current_eligible, checkout_eligible)
        return {
            'eligible': current_eligible,
            'checkout_eligible': checkout_eligible,
            'active_child_subscriptions': active_count,
            'discount_percent': 5,
            'stripe_coupon_configured': bool(self.settings.stripe_family_discount_coupon_id),
        }

    async def _family_discount_summary(self, parent_id: str) -> dict:
        access_rows = await self._access_rows(parent_id)
        active_count = len([row for row in access_rows if row.get('access_status') == 'active'])
        current_eligible = active_count >= 2
        checkout_eligible = active_count >= 1
        await self._record_family_discount_state(parent_id, active_count, current_eligible, checkout_eligible)
        return {
            'active_child_subscriptions': active_count,
            'eligible': current_eligible,
            'checkout_eligible': checkout_eligible,
            'discount_percent': 5,
            'stripe_coupon_configured': bool(self.settings.stripe_family_discount_coupon_id),
            'status': 'eligible' if current_eligible else ('eligible_next_checkout' if checkout_eligible else 'ineligible'),
            'message': self._family_discount_message(active_count, current_eligible, checkout_eligible),
            'not_retroactive': True,
            'annual_non_refundable': True,
            'removal_timing': 'next_renewal',
        }

    async def _record_family_discount_state(self, parent_id: str, active_count: int, current_eligible: bool, checkout_eligible: bool) -> None:
        status = 'eligible' if current_eligible else ('pending' if checkout_eligible else 'ineligible')
        latest = None
        try:
            rows = await self.supabase.select(
                'billing_discounts',
                f'parent_id=eq.{quote(parent_id)}&discount_type=eq.family&order=created_at.desc&limit=1',
            )
            latest = rows[0] if rows else None
        except SupabaseClientError as exc:
            if self._missing_milestone2_table(exc):
                return
            logger.warning('Could not load family discount state for parent %s: %s', parent_id, exc)
            return

        metadata = {
            'active_child_subscriptions': active_count,
            'checkout_eligible_for_next_child': checkout_eligible,
            'rule': '5 percent discount when parent has 2 or more active child subscriptions; second child checkout is eligible.',
            'not_retroactive': True,
            'removal_timing': 'next_renewal',
        }
        should_insert = not latest or latest.get('eligibility_status') != status
        remove_at_period_end = bool(
            active_count < 2
            and latest
            and latest.get('eligibility_status') in {'eligible', 'applied'}
        )
        if should_insert:
            try:
                await self.supabase.insert('billing_discounts', {
                    'parent_id': parent_id,
                    'discount_type': 'family',
                    'discount_percent': 5,
                    'stripe_coupon_id': self.settings.stripe_family_discount_coupon_id or None,
                    'eligibility_status': status,
                    'removes_at_period_end': remove_at_period_end,
                    'metadata': metadata,
                })
            except SupabaseClientError as exc:
                if not self._missing_milestone2_table(exc):
                    logger.warning('Could not save family discount state for parent %s: %s', parent_id, exc)

        await self._mark_family_discount_subscription_flags(parent_id, current_eligible, remove_at_period_end)

    async def _mark_family_discount_subscription_flags(self, parent_id: str, eligible: bool, remove_at_period_end: bool) -> None:
        try:
            await self.supabase.update('billing_subscriptions', {'parent_id': f'eq.{parent_id}'}, {
                'family_discount_eligible': eligible,
                'family_discount_remove_at_period_end': remove_at_period_end,
                'stripe_coupon_id': self.settings.stripe_family_discount_coupon_id or None,
                'updated_at': datetime.now(UTC).isoformat(),
            })
        except SupabaseClientError as exc:
            if self._missing_milestone2_table(exc) or self._missing_family_discount_columns(exc):
                return
            logger.warning('Could not update family discount subscription flags for parent %s: %s', parent_id, exc)

    def _family_discount_message(self, active_count: int, current_eligible: bool, checkout_eligible: bool) -> str:
        if current_eligible:
            return 'Family discount is available for this account because 2 or more child subscriptions are active.'
        if checkout_eligible:
            return 'Your next child subscription checkout is eligible for the family discount because it will bring the account to 2 active child subscriptions.'
        return 'Family discount starts when 2 or more child subscriptions are active.'

    async def _validate_coupon_code(self, stripe, coupon_code: str | None) -> dict | None:
        code = (coupon_code or '').strip()
        if not code:
            return None
        try:
            result = await anyio.to_thread.run_sync(lambda: stripe.PromotionCode.list(code=code, active=True, limit=1))
        except Exception as exc:
            logger.warning('Stripe coupon validation failed for submitted code: %s', exc)
            raise HTTPException(status_code=503, detail='Could not verify this coupon code right now. Please try again.') from exc

        promotions = self._stripe_to_dict(result).get('data') or []
        if not promotions:
            raise HTTPException(status_code=422, detail='This coupon code is not valid or is no longer active.')
        promotion = promotions[0]
        coupon = promotion.get('coupon') or {}
        if coupon.get('valid') is False:
            raise HTTPException(status_code=422, detail='This coupon code is not valid or is no longer active.')
        promotion_code_id = self._stripe_id(promotion.get('id'))
        if not promotion_code_id:
            raise HTTPException(status_code=422, detail='This coupon code is not valid or is no longer active.')
        return {
            'coupon_code': code,
            'promotion_code_id': promotion_code_id,
            'coupon_id': self._stripe_id(coupon.get('id')),
            'coupon_percent_off': coupon.get('percent_off'),
            'coupon_amount_off': coupon.get('amount_off'),
            'coupon_currency': coupon.get('currency'),
        }

    async def _record_coupon_redemption(self, parent_id: str, child_id: str, coupon: dict, status: str, payment_reference: str | None = None, metadata: dict | None = None) -> None:
        try:
            await self.supabase.insert('coupon_redemptions', {
                'parent_id': parent_id,
                'child_id': child_id,
                'coupon_code': coupon['coupon_code'],
                'stripe_coupon_id': coupon.get('coupon_id'),
                'stripe_promotion_code_id': coupon.get('promotion_code_id'),
                'validation_status': status,
                'payment_reference': payment_reference,
                'metadata': self._json_safe(metadata or {}),
            })
        except SupabaseClientError as exc:
            if not self._missing_coupon_redemptions_table(exc):
                logger.warning('Could not record coupon redemption for parent %s: %s', parent_id, exc)

    async def _coupon_redemptions_for_parent(self, parent_id: str) -> list[dict]:
        try:
            return await self.supabase.select(
                'coupon_redemptions',
                f'parent_id=eq.{quote(parent_id)}&order=created_at.desc&limit=10',
            )
        except SupabaseClientError as exc:
            if self._missing_coupon_redemptions_table(exc):
                return []
            logger.warning('Could not load coupon redemptions for parent %s: %s', parent_id, exc)
            return []

    def _missing_profile_stripe_column(self, exc: SupabaseClientError) -> bool:
        message = str(exc).lower()
        return 'stripe_customer_id' in message and ('schema cache' in message or 'could not find' in message or 'column' in message)

    def _stripe_to_dict(self, value) -> dict:
        if hasattr(value, 'to_dict_recursive'):
            return value.to_dict_recursive()
        if isinstance(value, dict):
            return value
        return dict(value)

    async def _stripe_event(self, event_id: str) -> dict | None:
        try:
            rows = await self.supabase.select('stripe_events', f'stripe_event_id=eq.{quote(event_id)}&limit=1')
        except SupabaseClientError as exc:
            if self._missing_stripe_events_table(exc):
                raise HTTPException(status_code=503, detail='Stripe events table is not set up yet. Please run the Supabase migration first.') from exc
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        return rows[0] if rows else None

    async def _record_stripe_event(self, event: dict, status: str) -> None:
        try:
            await self.supabase.insert('stripe_events', {
                'stripe_event_id': event['id'],
                'event_type': event['type'],
                'api_version': event.get('api_version'),
                'livemode': bool(event.get('livemode')),
                'processing_status': status,
                'payload': self._json_safe(event),
            })
        except SupabaseClientError as exc:
            if self._duplicate_stripe_event_error(exc):
                return
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    async def _mark_stripe_event(self, event_id: str, status: str, error_message: str | None = None) -> None:
        payload = {
            'processing_status': status,
            'processed_at': datetime.now(UTC).isoformat() if status == 'processed' else None,
            'error_message': error_message,
            'updated_at': datetime.now(UTC).isoformat(),
        }
        await self.supabase.update('stripe_events', {'stripe_event_id': f'eq.{event_id}'}, payload)

    async def _retrieve_subscription(self, subscription_id: str) -> dict:
        stripe = self._stripe_module()
        subscription = await anyio.to_thread.run_sync(lambda: stripe.Subscription.retrieve(subscription_id))
        return self._stripe_to_dict(subscription)

    async def _child_access_for_child(self, child_id: str) -> dict | None:
        rows = await self.supabase.select('child_access', f'child_id=eq.{quote(child_id)}&limit=1')
        return rows[0] if rows else None

    async def _child_access_for_subscription(self, subscription_id: str) -> dict | None:
        rows = await self.supabase.select('child_access', f'stripe_subscription_id=eq.{quote(subscription_id)}&limit=1')
        return rows[0] if rows else None

    async def _subscription_child_access_count(self, subscription_id: str) -> int:
        try:
            rows = await self.supabase.select('child_access', f'stripe_subscription_id=eq.{quote(subscription_id)}&select=child_id&limit=100')
        except SupabaseClientError as exc:
            if self._missing_access_table(exc):
                return 0
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        return len(rows)

    async def _billing_subscription_for_subscription(self, subscription_id: str) -> dict | None:
        rows = await self.supabase.select('billing_subscriptions', f'stripe_subscription_id=eq.{quote(subscription_id)}&limit=1')
        return rows[0] if rows else None

    async def _parent_email(self, parent_id: str) -> str | None:
        try:
            records = await self.supabase.select('profiles', f'id=eq.{quote(parent_id)}&select=email&limit=1')
        except SupabaseClientError as exc:
            logger.warning('Could not load parent email for billing email event: %s', exc)
            return None
        if not records:
            return None
        email = records[0].get('email')
        return str(email).strip().lower() if email else None

    async def _parent_contact(self, parent_id: str, fallback_email: str | None = None) -> dict:
        try:
            records = await self.supabase.select('profiles', f'id=eq.{quote(parent_id)}&select=full_name,email&limit=1')
        except SupabaseClientError as exc:
            logger.warning('Could not load parent contact for admin alert: %s', exc)
            return {'full_name': None, 'email': fallback_email}
        if not records:
            return {'full_name': None, 'email': fallback_email}
        row = records[0]
        return {
            'full_name': row.get('full_name'),
            'email': row.get('email') or fallback_email,
        }

    async def _child_name_for_alert(self, child_id: str | None) -> str | None:
        if not child_id:
            return None
        try:
            records = await self.supabase.select('child_profiles', f'id=eq.{quote(child_id)}&select=name&limit=1')
        except SupabaseClientError as exc:
            logger.warning('Could not load child name for admin alert: %s', exc)
            return None
        if not records:
            return None
        child_name = records[0].get('name')
        return str(child_name) if child_name else None

    def _billing_plan_label(self, row: dict | None) -> str | None:
        if not row:
            return None
        plan_type = row.get('plan_type')
        billing_interval = row.get('billing_interval')
        for plan in PLAN_CATALOG.values():
            if plan.get('plan_type') == plan_type and plan.get('billing_interval') == billing_interval:
                return str(plan.get('display_name') or '')
        return None

    async def _send_trial_started_alert(
        self,
        *,
        parent_id: str,
        parent_email: str,
        child: dict,
        plan: dict,
        trial_started_at: str,
        trial_ends_at: str,
    ) -> None:
        try:
            parent = await self._parent_contact(parent_id, fallback_email=parent_email)
            await EmailService().send_internal_admin_alert(
                subject='MsAlisia Admin Alert: Trial started',
                lines=[
                    'Event type: Trial started',
                    f'Parent name: {parent.get("full_name") or "Not provided"}',
                    f'Parent email: {parent.get("email") or parent_email}',
                    f'Child name: {child.get("name") or "Not provided"}',
                    f'Plan: {plan.get("display_name") or "Not provided"}',
                    f'Trial started at: {trial_started_at}',
                    f'Trial ends at: {trial_ends_at}',
                ],
            )
        except Exception as exc:
            logger.warning('Internal trial started alert failed for parent %s: %s', parent_id, exc)

    async def _send_trial_started_parent_email(
        self,
        *,
        parent_id: str,
        parent_email: str,
        child_id: str,
        trial_started_at: str,
        trial_ends_at: str,
    ) -> None:
        try:
            await EmailService().queue_and_send_trial_started_welcome(
                parent_id=parent_id,
                child_id=child_id,
                recipient_email=parent_email,
                trial_started_at=trial_started_at,
                trial_ends_at=trial_ends_at,
            )
        except Exception as exc:
            logger.warning('Trial started parent email failed for parent %s: %s', parent_id, exc)

    async def _send_paid_subscription_activated_alert(
        self,
        *,
        parent_id: str,
        parent_email: str,
        child_id: str | None,
        subscription_id: str | None,
        invoice_id: str | None,
        subscription: dict | None,
    ) -> None:
        try:
            parent = await self._parent_contact(parent_id, fallback_email=parent_email)
            child_name = await self._child_name_for_alert(child_id)
            plan_key = self._plan_key_from_price(subscription or {}) if subscription else None
            billing_row = await self._billing_subscription_for_subscription(subscription_id) if subscription_id else None
            plan_label = self._plan(plan_key)['display_name'] if plan_key else self._billing_plan_label(billing_row)
            status = (subscription or {}).get('status') or (billing_row or {}).get('subscription_status') or 'active'
            await EmailService().send_internal_admin_alert(
                subject='MsAlisia Admin Alert: Paid subscription activated',
                lines=[
                    'Event type: Paid subscription activated',
                    f'Parent name: {parent.get("full_name") or "Not provided"}',
                    f'Parent email: {parent.get("email") or parent_email}',
                    f'Child name: {child_name or child_id or "Not provided"}',
                    f'Plan/status: {plan_label or "Not provided"} / {status}',
                    f'Time: {datetime.now(UTC).isoformat()}',
                ],
            )
        except Exception as exc:
            logger.warning('Internal paid subscription alert failed for parent %s invoice %s: %s', parent_id, invoice_id, exc)

    async def _send_subscription_canceled_alert(
        self,
        *,
        parent_id: str,
        child_id: str | None,
        subscription_id: str,
        status: str,
        canceled_at: str,
    ) -> None:
        try:
            parent = await self._parent_contact(parent_id)
            child_name = await self._child_name_for_alert(child_id)
            billing_row = await self._billing_subscription_for_subscription(subscription_id)
            plan_label = self._billing_plan_label(billing_row)
            await EmailService().send_internal_admin_alert(
                subject='MsAlisia Admin Alert: Subscription canceled',
                lines=[
                    'Event type: Subscription canceled',
                    f'Parent name: {parent.get("full_name") or "Not provided"}',
                    f'Parent email: {parent.get("email") or "Not provided"}',
                    f'Child name: {child_name or child_id or "Not provided"}',
                    f'Plan/status: {plan_label or "Not provided"} / {status}',
                    f'Canceled at: {canceled_at}',
                ],
            )
        except Exception as exc:
            logger.warning('Internal subscription canceled alert failed for parent %s: %s', parent_id, exc)

    async def _queue_and_send_email_event(self, event: dict) -> None:
        if event.get('status') != 'pending' or not event.get('id'):
            return
        try:
            await EmailService().send_event(event)
        except Exception as exc:
            logger.warning('Immediate billing email send failed for event %s: %s', event.get('id'), exc)

    async def _queue_payment_success_email(self, invoice: dict, subscription: dict | None) -> None:
        metadata = subscription.get('metadata') if subscription else {}
        subscription_id = self._stripe_id(invoice.get('subscription')) or self._stripe_id((subscription or {}).get('id'))
        parent_id = (metadata or {}).get('parent_id')
        child_id = (metadata or {}).get('child_id')
        if (not parent_id or not child_id) and subscription_id:
            billing_row = await self._billing_subscription_for_subscription(subscription_id)
            parent_id = parent_id or (billing_row or {}).get('parent_id')
            child_id = child_id or (billing_row or {}).get('child_id')
        if not parent_id:
            return
        recipient_email = await self._parent_email(parent_id)
        if not recipient_email:
            return
        invoice_id = self._stripe_id(invoice.get('id')) or datetime.now(UTC).isoformat()
        event = await EmailService().queue_payment_success(
            parent_id=parent_id,
            child_id=child_id,
            recipient_email=recipient_email,
            metadata={
                'stripe_invoice_id': self._stripe_id(invoice.get('id')),
                'stripe_subscription_id': subscription_id,
                'dedupe_key': f'payment_success|{invoice_id}',
            },
        )
        await self._queue_and_send_email_event(event)
        await self._send_paid_subscription_activated_alert(
            parent_id=parent_id,
            parent_email=recipient_email,
            child_id=child_id,
            subscription_id=subscription_id,
            invoice_id=invoice_id,
            subscription=subscription,
        )

    async def _queue_payment_failed_email(self, invoice: dict) -> None:
        subscription_id = self._stripe_id(invoice.get('subscription'))
        if not subscription_id:
            return
        access_row = await self._child_access_for_subscription(subscription_id)
        parent_id = (access_row or {}).get('parent_id')
        child_id = (access_row or {}).get('child_id')
        if not parent_id:
            billing_row = await self._billing_subscription_for_subscription(subscription_id)
            parent_id = (billing_row or {}).get('parent_id')
            child_id = child_id or (billing_row or {}).get('child_id')
        if not parent_id:
            return
        recipient_email = await self._parent_email(parent_id)
        if not recipient_email:
            return
        invoice_id = self._stripe_id(invoice.get('id')) or datetime.now(UTC).isoformat()
        event = await EmailService().queue_payment_failed(
            parent_id=parent_id,
            child_id=child_id,
            recipient_email=recipient_email,
            metadata={
                'stripe_invoice_id': self._stripe_id(invoice.get('id')),
                'stripe_subscription_id': subscription_id,
                'dedupe_key': f'payment_failed|{invoice_id}',
            },
        )
        await self._queue_and_send_email_event(event)

    async def _queue_annual_renewal_email(self, parent_id: str, child_id: str, customer_id: str, billing_payload: dict) -> None:
        if billing_payload.get('billing_interval') != 'annual' or billing_payload.get('subscription_status') not in {'active', 'trialing'}:
            return
        period_end = self._parse_iso_datetime(billing_payload.get('current_period_ends_at'))
        if not period_end:
            return
        scheduled_at = period_end - timedelta(days=7)
        recipient_email = await self._parent_email(parent_id)
        if not recipient_email:
            return
        event = await EmailService().queue_annual_renewal_reminder(
            parent_id=parent_id,
            child_id=child_id,
            recipient_email=recipient_email,
            scheduled_send_at=scheduled_at.isoformat(),
            metadata={
                'renewal_date': period_end.date().isoformat(),
                'amount': '$1,749/year' if billing_payload.get('plan_type') == 'voice' else '$1,419/year',
                'stripe_customer_id': customer_id,
                'stripe_subscription_id': billing_payload.get('stripe_subscription_id'),
                'dedupe_key': f"annual_renewal_reminder|{billing_payload.get('stripe_subscription_id')}|{scheduled_at.date().isoformat()}",
            },
        )
        if scheduled_at <= datetime.now(UTC):
            await self._queue_and_send_email_event(event)

    async def _upsert_billing_subscription(self, payload: dict) -> None:
        try:
            await self.supabase.upsert('billing_subscriptions', {**payload, 'created_at': datetime.now(UTC).isoformat()}, 'stripe_subscription_id')
        except SupabaseClientError as exc:
            if self._missing_milestone2_table(exc):
                raise HTTPException(status_code=503, detail='Billing subscription table is not set up yet. Please run the Supabase migration first.') from exc
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    async def _record_financial_event_from_invoice(self, invoice: dict, event_type: str) -> None:
        try:
            await self.supabase.insert('financial_events', {
                'stripe_customer_id': self._stripe_id(invoice.get('customer')),
                'stripe_subscription_id': self._stripe_id(invoice.get('subscription')),
                'stripe_invoice_id': self._stripe_id(invoice.get('id')),
                'stripe_payment_intent_id': self._stripe_id(invoice.get('payment_intent')),
                'event_type': event_type,
                'billing_status': invoice.get('status'),
                'amount_cents': int(invoice.get('amount_paid') or invoice.get('amount_due') or 0),
                'currency': invoice.get('currency') or 'usd',
                'metadata': self._json_safe(invoice.get('metadata') or {}),
            })
        except SupabaseClientError as exc:
            if not self._missing_financial_events_table(exc):
                logger.warning('Could not record financial event %s: %s', event_type, exc)

    async def _record_financial_event_from_payment_intent(self, payment_intent: dict, event_type: str) -> None:
        try:
            await self.supabase.insert('financial_events', {
                'stripe_customer_id': self._stripe_id(payment_intent.get('customer')),
                'stripe_payment_intent_id': self._stripe_id(payment_intent.get('id')),
                'event_type': event_type,
                'billing_status': payment_intent.get('status'),
                'amount_cents': int(payment_intent.get('amount') or 0),
                'currency': payment_intent.get('currency') or 'usd',
                'metadata': self._json_safe(payment_intent.get('metadata') or {}),
            })
        except SupabaseClientError as exc:
            if not self._missing_financial_events_table(exc):
                logger.warning('Could not record financial event %s: %s', event_type, exc)

    def _stripe_id(self, value) -> str | None:
        if not value:
            return None
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            return value.get('id')
        return str(value)

    def _stripe_timestamp(self, value) -> str | None:
        if not value:
            return None
        try:
            return datetime.fromtimestamp(int(value), UTC).isoformat()
        except Exception:
            return None

    def _parse_iso_datetime(self, value: object) -> datetime | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except Exception:
            return None

    def _subscription_price_id(self, subscription: dict) -> str | None:
        items = ((subscription.get('items') or {}).get('data') or [])
        if not items:
            return None
        price = items[0].get('price') or {}
        return self._stripe_id(price.get('id'))

    def _subscription_period_timestamp(self, subscription: dict, key: str) -> str | None:
        value = subscription.get(key)
        if value:
            return self._stripe_timestamp(value)
        items = ((subscription.get('items') or {}).get('data') or [])
        for item in items:
            item_value = item.get(key)
            if item_value:
                return self._stripe_timestamp(item_value)
        return None

    def _plan_key_from_price(self, subscription: dict) -> str | None:
        price_id = self._subscription_price_id(subscription)
        if not price_id:
            return None
        for plan_key, plan in PLAN_CATALOG.items():
            if getattr(self.settings, plan['settings_attr'], '') == price_id:
                return plan_key
        return None

    def _access_status_from_subscription(self, status: str) -> str:
        if status in {'active', 'trialing'}:
            return 'active'
        if status in {'past_due', 'unpaid'}:
            return 'past_due'
        return 'inactive'

    def _pause_reason_for_status(self, status: str) -> str | None:
        if status in {'canceled', 'incomplete_expired'}:
            return 'subscription_canceled'
        if status in {'past_due', 'unpaid'}:
            return 'payment_required'
        if status == 'paused':
            return 'subscription_paused'
        return None

    def _subscription_statuses(self) -> set[str]:
        return {'incomplete', 'trialing', 'active', 'past_due', 'paused', 'canceled', 'unpaid', 'incomplete_expired'}

    def _json_safe(self, value):
        return json.loads(json.dumps(value, default=str))

    def _duplicate_stripe_event_error(self, exc: SupabaseClientError) -> bool:
        message = str(exc).lower()
        return 'stripe_events_stripe_event_id_key' in message or 'duplicate key' in message

    def _missing_stripe_events_table(self, exc: SupabaseClientError) -> bool:
        message = str(exc).lower()
        return 'stripe_events' in message and ('schema cache' in message or 'could not find' in message or 'does not exist' in message)

    def _missing_financial_events_table(self, exc: SupabaseClientError) -> bool:
        message = str(exc).lower()
        return 'financial_events' in message and ('schema cache' in message or 'could not find' in message or 'does not exist' in message)

    def _missing_coupon_redemptions_table(self, exc: SupabaseClientError) -> bool:
        message = str(exc).lower()
        return 'coupon_redemptions' in message and ('schema cache' in message or 'could not find' in message or 'does not exist' in message)

    def _missing_family_discount_columns(self, exc: SupabaseClientError) -> bool:
        message = str(exc).lower()
        return 'schema cache' in message and any(column in message for column in [
            'family_discount_eligible',
            'family_discount_remove_at_period_end',
            'stripe_coupon_id',
        ])

    def _missing_cancel_at_period_end_column(self, exc: SupabaseClientError) -> bool:
        message = str(exc).lower()
        return 'schema cache' in message and 'cancel_at_period_end' in message
