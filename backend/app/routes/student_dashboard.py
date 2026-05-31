from fastapi import APIRouter, Header

from ..schemas.student_dashboard import StudentDashboardResponse, WeeklyRhythmListResponse
from ..services.access_control import require_child_access, require_parent_access
from ..services.student_dashboard_service import StudentDashboardService

router = APIRouter(prefix='/children', tags=['student dashboard'])


@router.get('/weekly-rhythm', response_model=WeeklyRhythmListResponse)
async def parent_weekly_rhythm(authorization: str = Header(default=''), x_access_mode: str = Header(default='')) -> WeeklyRhythmListResponse:
    user = await require_parent_access(authorization, x_access_mode)
    rhythms = await StudentDashboardService().weekly_rhythm_for_parent(user['id'])
    return WeeklyRhythmListResponse(rhythms=rhythms)


@router.get('/{child_id}/dashboard', response_model=StudentDashboardResponse)
async def student_dashboard(child_id: str, authorization: str = Header(default=''), x_access_mode: str = Header(default='')) -> StudentDashboardResponse:
    user = await require_child_access(authorization, child_id, x_access_mode)
    return await StudentDashboardService().dashboard_for_child(user['id'], child_id)
