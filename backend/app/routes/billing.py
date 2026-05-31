from fastapi import APIRouter, Header, HTTPException, Request

from ..config import get_settings
from ..schemas.billing import (
    BillingPlansResponse,
    BillingPlanResponse,
    BillingStatusResponse,
    CheckoutSessionRequest,
    CheckoutSessionResponse,
    ChildAccessListResponse,
    ChildAccessResponse,
    ChildAccessUpdateRequest,
    CustomerPortalRequest,
    CustomerPortalResponse,
    StartTrialRequest,
    StartTrialResponse,
    StripeSubscriptionSyncResponse,
    StripeWebhookResponse,
)
from ..services.access_control import require_parent_access
from ..services.billing_service import BillingService

router = APIRouter(prefix='/billing', tags=['billing'])


@router.get('/children', response_model=ChildAccessListResponse)
async def child_access_list(authorization: str = Header(default=''), x_access_mode: str = Header(default='')) -> ChildAccessListResponse:
    user = await require_parent_access(authorization, x_access_mode)
    records = await BillingService().list_child_access(user['id'], email=user.get('email') or '')
    return ChildAccessListResponse(children=[ChildAccessResponse(**record) for record in records])


@router.get('/plans', response_model=BillingPlansResponse)
async def billing_plans() -> BillingPlansResponse:
    plans = BillingService().plans()
    return BillingPlansResponse(plans=[BillingPlanResponse(**plan) for plan in plans])


@router.get('/status', response_model=BillingStatusResponse)
async def billing_status(authorization: str = Header(default=''), x_access_mode: str = Header(default='')) -> BillingStatusResponse:
    user = await require_parent_access(authorization, x_access_mode)
    status = await BillingService().billing_status(user['id'], user.get('email') or '')
    return BillingStatusResponse(
        **{
            **status,
            'children': [ChildAccessResponse(**record) for record in status['children']],
            'plans': [BillingPlanResponse(**record) for record in status['plans']],
        }
    )


@router.post('/trial/start', response_model=StartTrialResponse)
async def start_trial(payload: StartTrialRequest, authorization: str = Header(default=''), x_access_mode: str = Header(default='')) -> StartTrialResponse:
    user = await require_parent_access(authorization, x_access_mode)
    result = await BillingService().start_trial(user['id'], user.get('email') or '', payload.child_id, payload.plan_key)
    return StartTrialResponse(**{**result, 'child': ChildAccessResponse(**result['child'])})


@router.post('/checkout/session', response_model=CheckoutSessionResponse)
async def create_checkout_session(payload: CheckoutSessionRequest, authorization: str = Header(default=''), x_access_mode: str = Header(default='')) -> CheckoutSessionResponse:
    user = await require_parent_access(authorization, x_access_mode)
    result = await BillingService().create_checkout_session(user['id'], user.get('email') or '', payload.child_id, payload.plan_key, payload.coupon_code)
    return CheckoutSessionResponse(**result)


@router.post('/portal/session', response_model=CustomerPortalResponse)
async def create_customer_portal_session(payload: CustomerPortalRequest, authorization: str = Header(default=''), x_access_mode: str = Header(default='')) -> CustomerPortalResponse:
    user = await require_parent_access(authorization, x_access_mode)
    result = await BillingService().create_customer_portal_session(user['id'], user.get('email') or '', payload.child_id)
    return CustomerPortalResponse(**result)


@router.post('/stripe/webhook', response_model=StripeWebhookResponse)
async def stripe_webhook(request: Request, stripe_signature: str = Header(default='', alias='Stripe-Signature')) -> StripeWebhookResponse:
    payload = await request.body()
    result = await BillingService().handle_stripe_webhook(payload, stripe_signature)
    return StripeWebhookResponse(**result)


@router.post('/stripe/sync-all', response_model=StripeSubscriptionSyncResponse)
async def sync_all_stripe_subscriptions(
    authorization: str = Header(default=''),
    x_internal_cron_secret: str = Header(default=''),
) -> StripeSubscriptionSyncResponse:
    settings = get_settings()
    expected_secret = settings.internal_cron_secret.strip()
    provided_secret = x_internal_cron_secret.strip()
    if authorization.lower().startswith('bearer '):
        provided_secret = authorization[7:].strip()
    if not expected_secret or provided_secret != expected_secret:
        raise HTTPException(status_code=403, detail='Internal endpoint access denied.')
    result = await BillingService().sync_all_stripe_subscriptions()
    return StripeSubscriptionSyncResponse(**result)


@router.patch('/children/{child_id}', response_model=ChildAccessResponse)
async def update_child_access(child_id: str, payload: ChildAccessUpdateRequest, authorization: str = Header(default=''), x_access_mode: str = Header(default='')) -> ChildAccessResponse:
    user = await require_parent_access(authorization, x_access_mode)
    record = await BillingService().update_child_access(user['id'], child_id, payload, email=user.get('email') or '')
    return ChildAccessResponse(**record)
