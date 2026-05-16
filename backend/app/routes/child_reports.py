from fastapi import APIRouter, Header, Query

from ..schemas.child_report import ChildReportResponse, WeeklyReportEmailPreview
from ..services.auth_user import authenticated_user, bearer_token
from ..services.child_report_service import ChildReportService

router = APIRouter(prefix='/children', tags=['child reports'])


@router.get('/{child_id}/report', response_model=ChildReportResponse)
async def child_report(
    child_id: str,
    period: str = Query(default='all', pattern='^(week|month|all)$'),
    subject: str = Query(default='All'),
    authorization: str = Header(default=''),
) -> ChildReportResponse:
    user = await authenticated_user(bearer_token(authorization))
    return await ChildReportService().report_for_child(user['id'], child_id, period=period, subject=subject)


@router.get('/{child_id}/weekly-email-preview', response_model=WeeklyReportEmailPreview)
async def weekly_email_preview(child_id: str, authorization: str = Header(default='')) -> WeeklyReportEmailPreview:
    user = await authenticated_user(bearer_token(authorization))
    return await ChildReportService().weekly_email_preview(user['id'], child_id)
