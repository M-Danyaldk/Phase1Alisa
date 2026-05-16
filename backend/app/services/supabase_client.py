from typing import Any
from urllib.parse import urlencode
import httpx
from ..config import get_settings


class SupabaseClientError(RuntimeError):
    def __init__(self, message: str, status_code: int = 500) -> None:
        super().__init__(message)
        self.status_code = status_code


class SupabaseClient:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.base_url = self.settings.supabase_url.rstrip('/')
        self.anon_key = self.settings.supabase_anon_key
        self.service_key = self.settings.supabase_service_role_key

    def configured(self) -> bool:
        return bool(self.base_url and self.anon_key and self.service_key)

    def _require_config(self) -> None:
        if not self.configured():
            raise SupabaseClientError('Supabase is not configured yet.', 503)

    def _service_headers(self, prefer: str | None = None) -> dict[str, str]:
        headers = {
            'apikey': self.service_key,
            'Authorization': f'Bearer {self.service_key}',
            'Content-Type': 'application/json',
        }
        if prefer:
            headers['Prefer'] = prefer
        return headers

    def _anon_headers(self) -> dict[str, str]:
        return {
            'apikey': self.anon_key,
            'Authorization': f'Bearer {self.anon_key}',
            'Content-Type': 'application/json',
        }

    async def insert(self, table: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
        self._require_config()
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f'{self.base_url}/rest/v1/{table}',
                json=payload,
                headers=self._service_headers('return=representation'),
            )
        return self._json_or_raise(response)

    async def upsert(self, table: str, payload: dict[str, Any], on_conflict: str) -> list[dict[str, Any]]:
        self._require_config()
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f'{self.base_url}/rest/v1/{table}?on_conflict={on_conflict}',
                json=payload,
                headers=self._service_headers('resolution=merge-duplicates,return=representation'),
            )
        return self._json_or_raise(response)

    async def update(self, table: str, filters: dict[str, str], payload: dict[str, Any]) -> list[dict[str, Any]]:
        self._require_config()
        query = urlencode(filters)
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.patch(
                f'{self.base_url}/rest/v1/{table}?{query}',
                json=payload,
                headers=self._service_headers('return=representation'),
            )
        return self._json_or_raise(response)

    async def select(self, table: str, query: str) -> list[dict[str, Any]]:
        self._require_config()
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                f'{self.base_url}/rest/v1/{table}?{query}',
                headers=self._service_headers(),
            )
        return self._json_or_raise(response)

    async def create_auth_user(self, email: str, password: str, metadata: dict[str, Any]) -> dict[str, Any]:
        self._require_config()
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f'{self.base_url}/auth/v1/admin/users',
                json={
                    'email': email,
                    'password': password,
                    'email_confirm': True,
                    'user_metadata': metadata,
                },
                headers=self._service_headers(),
            )
        return self._json_or_raise(response)

    async def login_with_password(self, email: str, password: str) -> dict[str, Any]:
        self._require_config()
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f'{self.base_url}/auth/v1/token?grant_type=password',
                json={'email': email, 'password': password},
                headers=self._anon_headers(),
            )
        return self._json_or_raise(response, clean_message='Invalid email or password.', clean_status=401)

    async def get_user(self, access_token: str) -> dict[str, Any]:
        self._require_config()
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                f'{self.base_url}/auth/v1/user',
                headers={
                    'apikey': self.anon_key,
                    'Authorization': f'Bearer {access_token}',
                    'Content-Type': 'application/json',
                },
            )
        return self._json_or_raise(response, clean_message='Invalid or expired session.', clean_status=401)

    async def upload_storage_file(self, bucket: str, path: str, content: bytes, content_type: str) -> dict[str, Any]:
        self._require_config()
        headers = {
            'apikey': self.service_key,
            'Authorization': f'Bearer {self.service_key}',
            'Content-Type': content_type,
            'x-upsert': 'true',
        }
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.post(
                f'{self.base_url}/storage/v1/object/{bucket}/{path}',
                content=content,
                headers=headers,
            )
        return self._json_or_raise(response)

    async def ensure_storage_bucket(self, bucket: str, public: bool = False) -> None:
        self._require_config()
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                f'{self.base_url}/storage/v1/bucket/{bucket}',
                headers=self._service_headers(),
            )
            if response.is_success:
                return
            if response.status_code != 404:
                self._json_or_raise(response)

            create_response = await client.post(
                f'{self.base_url}/storage/v1/bucket',
                json={'id': bucket, 'name': bucket, 'public': public},
                headers=self._service_headers(),
            )
        self._json_or_raise(create_response)

    async def ensure_public_storage_bucket(self, bucket: str) -> None:
        await self.ensure_storage_bucket(bucket, public=True)

    def public_storage_url(self, bucket: str, path: str) -> str:
        self._require_config()
        return f'{self.base_url}/storage/v1/object/public/{bucket}/{path}'

    def _json_or_raise(
        self,
        response: httpx.Response,
        clean_message: str | None = None,
        clean_status: int | None = None,
    ) -> Any:
        if response.is_success:
            if response.content:
                return response.json()
            return {}
        if clean_message:
            raise SupabaseClientError(clean_message, clean_status or response.status_code)
        try:
            data = response.json()
            detail = data.get('message') or data.get('error_description') or data.get('details') or data.get('hint') or data.get('code')
        except Exception:
            detail = response.text
        raise SupabaseClientError(detail or 'Supabase request failed.', response.status_code)
