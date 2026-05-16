from fastapi import HTTPException

from .supabase_client import SupabaseClient, SupabaseClientError


def bearer_token(authorization: str) -> str:
    if not authorization.lower().startswith('bearer '):
        raise HTTPException(status_code=401, detail='Authorization token is required.')
    token = authorization.split(' ', 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail='Authorization token is required.')
    return token


async def authenticated_user(access_token: str) -> dict:
    try:
        user = await SupabaseClient().get_user(access_token)
    except SupabaseClientError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    if not user.get('id'):
        raise HTTPException(status_code=401, detail='Invalid or expired session.')
    return user
