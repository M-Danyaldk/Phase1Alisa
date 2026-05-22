from fastapi import APIRouter, Header, Query

from ..schemas.admin import (
    AdminAuditLogsResponse,
    AdminInviteRequest,
    AdminInviteResponse,
    AdminOverviewResponse,
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
