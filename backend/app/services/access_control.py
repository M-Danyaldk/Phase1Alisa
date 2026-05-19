from urllib.parse import quote

from fastapi import HTTPException

from .auth_user import authenticated_user, bearer_token
from .student_auth_service import StudentAuthService
from .supabase_client import SupabaseClient, SupabaseClientError

CHILD_ACCESS_MODE = 'child'


async def require_parent_access(authorization: str, access_mode: str = '') -> dict:
    if access_mode.strip().lower() == CHILD_ACCESS_MODE:
        raise HTTPException(status_code=403, detail='This area is for parents only.')
    return await authenticated_user(bearer_token(authorization))


async def require_child_access(authorization: str, child_id: str | None, access_mode: str = '') -> dict:
    if not child_id:
        raise HTTPException(status_code=400, detail='Child profile is required for student learning access.')
    if access_mode.strip().lower() == CHILD_ACCESS_MODE:
        user = await authenticated_user(bearer_token(authorization))
        await ensure_child_for_parent(user['id'], child_id)
        return user

    session = await StudentAuthService().session_from_token(bearer_token(authorization))
    if session['child_id'] != child_id:
        raise HTTPException(status_code=403, detail='This student session cannot access another child profile.')
    await ensure_child_for_parent(session['parent_id'], child_id)
    return {'id': session['parent_id'], 'child_id': session['child_id'], 'role': 'child'}


async def ensure_child_for_parent(parent_id: str, child_id: str) -> None:
    try:
        records = await SupabaseClient().select(
            'child_profiles',
            f'id=eq.{quote(child_id)}&parent_id=eq.{quote(parent_id)}&status=neq.inactive&limit=1',
        )
    except SupabaseClientError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    if not records:
        raise HTTPException(status_code=403, detail='Your learning access is currently paused. Please ask your parent to check the account.')
