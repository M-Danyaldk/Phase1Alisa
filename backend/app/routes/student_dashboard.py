from fastapi import APIRouter, Header

from ..schemas.student_dashboard import StudentDashboardResponse
from ..services.access_control import require_child_access
from ..services.student_dashboard_service import StudentDashboardService

router = APIRouter(prefix='/children', tags=['student dashboard'])


@router.get('/{child_id}/dashboard', response_model=StudentDashboardResponse)
async def student_dashboard(child_id: str, authorization: str = Header(default=''), x_access_mode: str = Header(default='')) -> StudentDashboardResponse:
    user = await require_child_access(authorization, child_id, x_access_mode)
    return await StudentDashboardService().dashboard_for_child(user['id'], child_id)
