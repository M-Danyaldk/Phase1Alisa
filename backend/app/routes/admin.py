from fastapi import APIRouter, Header, Query, Response

from ..schemas.admin import (
    AdminAuditLogsResponse,
    AdminInviteRequest,
    AdminInviteResponse,
    AdminOverviewResponse,
    OwnerFinancialDiscountsResponse,
    OwnerFinancialEventsResponse,
    OwnerFinancialFailedPaymentsResponse,
    OwnerFinancialReferralsResponse,
    OwnerFinancialSubscriptionsResponse,
    OwnerFinancialSummaryResponse,
    AdminPermissionsUpdateRequest,
    AdminReportsResponse,
    AdminSettingsResponse,
    AdminSettingUpdateRequest,
    AdminSubscriptionsResponse,
    AdminSubscriptionUpdateRequest,
    AdminUsersResponse,
    AdminUserStatusUpdateRequest,
)
from ..services.admin_service import AdminService
from ..services.owner_financial_service import OwnerFinancialService

router = APIRouter(prefix='/api/admin', tags=['admin'])


@router.get('/overview', response_model=AdminOverviewResponse)
async def admin_overview(authorization: str = Header(default='')) -> dict:
    service = AdminService()
    admin = await service.require_admin(authorization, 'view_analytics')
    return await service.overview(admin)


@router.get('/users', response_model=AdminUsersResponse)
async def admin_users(
    authorization: str = Header(default=''),
    search: str = Query(default=''),
) -> dict:
    service = AdminService()
    admin = await service.require_admin(authorization, 'manage_users')
    return {'users': await service.users(admin, search=search)}


@router.patch('/users/{user_id}/status')
async def admin_update_user_status(
    user_id: str,
    payload: AdminUserStatusUpdateRequest,
    authorization: str = Header(default=''),
) -> dict:
    service = AdminService()
    admin = await service.require_admin(authorization, 'manage_users')
    return await service.update_user_status(admin, user_id, payload)


@router.get('/subscriptions', response_model=AdminSubscriptionsResponse)
async def admin_subscriptions(authorization: str = Header(default='')) -> dict:
    service = AdminService()
    admin = await service.require_admin(authorization, 'manage_subscriptions')
    return {'subscriptions': await service.subscriptions(admin)}


@router.patch('/subscriptions/{subscription_id}')
async def admin_update_subscription(
    subscription_id: str,
    payload: AdminSubscriptionUpdateRequest,
    authorization: str = Header(default=''),
) -> dict:
    service = AdminService()
    admin = await service.require_admin(authorization, 'manage_subscriptions')
    return await service.update_subscription(admin, subscription_id, payload)


@router.get('/reports', response_model=AdminReportsResponse)
async def admin_reports(authorization: str = Header(default='')) -> dict:
    service = AdminService()
    admin = await service.require_admin(authorization, 'view_analytics')
    return await service.reports(admin)


@router.get('/settings', response_model=AdminSettingsResponse)
async def admin_settings(authorization: str = Header(default='')) -> dict:
    service = AdminService()
    admin = await service.require_admin(authorization, 'manage_settings')
    return {'settings': await service.settings(admin)}


@router.patch('/settings/{key}')
async def admin_update_setting(
    key: str,
    payload: AdminSettingUpdateRequest,
    authorization: str = Header(default=''),
) -> dict:
    service = AdminService()
    admin = await service.require_admin(authorization, 'manage_settings')
    return await service.update_setting(admin, key, payload)


@router.get('/audit-logs', response_model=AdminAuditLogsResponse)
async def admin_audit_logs(authorization: str = Header(default='')) -> dict:
    service = AdminService()
    admin = await service.require_admin(authorization, 'view_analytics')
    return {'audit_logs': await service.audit_logs(admin)}


@router.get('/owner-financials/summary', response_model=OwnerFinancialSummaryResponse)
async def owner_financial_summary(authorization: str = Header(default='')) -> dict:
    await AdminService().require_super_admin(authorization)
    return {'summary': await OwnerFinancialService().summary()}


@router.get('/owner-financials/subscriptions', response_model=OwnerFinancialSubscriptionsResponse)
async def owner_financial_subscriptions(
    authorization: str = Header(default=''),
    limit: int = Query(default=250, ge=1, le=1000),
) -> dict:
    await AdminService().require_super_admin(authorization)
    return {'subscriptions': await OwnerFinancialService().subscriptions(limit=limit)}


@router.get('/owner-financials/failed-payments', response_model=OwnerFinancialFailedPaymentsResponse)
async def owner_financial_failed_payments(
    authorization: str = Header(default=''),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict:
    await AdminService().require_super_admin(authorization)
    return {'failed_payments': await OwnerFinancialService().failed_payments(limit=limit)}


@router.get('/owner-financials/discounts', response_model=OwnerFinancialDiscountsResponse)
async def owner_financial_discounts(
    authorization: str = Header(default=''),
    limit: int = Query(default=150, ge=1, le=500),
) -> dict:
    await AdminService().require_super_admin(authorization)
    return await OwnerFinancialService().discounts(limit=limit)


@router.get('/owner-financials/referrals', response_model=OwnerFinancialReferralsResponse)
async def owner_financial_referrals(
    authorization: str = Header(default=''),
    limit: int = Query(default=150, ge=1, le=500),
) -> dict:
    await AdminService().require_super_admin(authorization)
    return await OwnerFinancialService().referrals(limit=limit)


@router.get('/owner-financials/events', response_model=OwnerFinancialEventsResponse)
async def owner_financial_events(
    authorization: str = Header(default=''),
    limit: int = Query(default=200, ge=1, le=1000),
) -> dict:
    await AdminService().require_super_admin(authorization)
    return {'events': await OwnerFinancialService().events(limit=limit)}


@router.get('/owner-financials/export')
async def owner_financial_export(authorization: str = Header(default='')) -> Response:
    await AdminService().require_super_admin(authorization)
    csv_body = await OwnerFinancialService().export_csv()
    return Response(
        content=csv_body,
        media_type='text/csv',
        headers={'Content-Disposition': 'attachment; filename="msalisia-owner-financials.csv"'},
    )


@router.post('/admins/invite', response_model=AdminInviteResponse)
async def admin_invite(payload: AdminInviteRequest, authorization: str = Header(default='')) -> dict:
    service = AdminService()
    admin = await service.require_admin(authorization, 'manage_admins')
    created = await service.invite_admin(admin, payload)
    return {'admin': created, 'message': 'Admin account created.'}


@router.patch('/admins/{user_id}/permissions')
async def admin_update_permissions(
    user_id: str,
    payload: AdminPermissionsUpdateRequest,
    authorization: str = Header(default=''),
) -> dict:
    service = AdminService()
    admin = await service.require_admin(authorization, 'manage_admins')
    return await service.update_admin_permissions(admin, user_id, payload)
