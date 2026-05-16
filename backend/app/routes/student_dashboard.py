from fastapi import APIRouter, Header

from ..schemas.student_dashboard import StudentDashboardResponse
from ..services.auth_user import authenticated_user, bearer_token
from ..services.student_dashboard_service import StudentDashboardService

router = APIRouter(prefix='/children', tags=['student dashboard'])


@router.get('/{child_id}/dashboard', response_model=StudentDashboardResponse)
async def student_dashboard(child_id: str, authorization: str = Header(default='')) -> StudentDashboardResponse:
    user = await authenticated_user(bearer_token(authorization))
    return await StudentDashboardService().dashboard_for_child(user['id'], child_id)
