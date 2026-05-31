from fastapi import APIRouter, Header

from ..schemas.problem_reports import ProblemReportRequest, ProblemReportResponse
from ..services.access_control import ensure_child_for_parent, require_child_access, require_parent_access
from ..services.problem_report_service import ProblemReportService

router = APIRouter(prefix='/api/problem-reports', tags=['problem reports'])


@router.post('', response_model=ProblemReportResponse)
async def create_problem_report(
    payload: ProblemReportRequest,
    authorization: str = Header(default=''),
    x_access_mode: str = Header(default=''),
) -> ProblemReportResponse:
    if payload.reporter_type == 'parent':
        user = await require_parent_access(authorization, x_access_mode)
        await ensure_child_for_parent(user['id'], payload.child_id)
        parent_id = user['id']
        reporter_user_id = user['id']
    else:
        access = await require_child_access(authorization, payload.child_id, x_access_mode)
        parent_id = access['id']
        reporter_user_id = None if access.get('role') == 'child' else access['id']

    result = await ProblemReportService().create_report(parent_id, reporter_user_id, payload)
    return ProblemReportResponse(**result)
