import httpx
from .base import LLMResult
from ...config import get_settings

class ClaudeProvider:
    provider_name = 'claude'

    def __init__(self) -> None:
        self.settings = get_settings()
        self.model = self.settings.anthropic_model

    def available(self) -> bool:
        return bool(self.settings.anthropic_api_key.strip())

    async def generate(self, system: str, user: str, max_tokens: int | None = None) -> LLMResult:
        if not self.available():
            raise RuntimeError('Claude API key is missing')
        payload = {
            'model': self.model,
            'max_tokens': max_tokens or self.settings.max_output_tokens,
            'temperature': self.settings.temperature,
            'system': system,
            'messages': [{'role': 'user', 'content': user}]
        }
        headers = {
            'x-api-key': self.settings.anthropic_api_key,
            'anthropic-version': '2023-06-01',
            'content-type': 'application/json'
        }
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.post(self.settings.anthropic_api_url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
        parts = data.get('content', [])
        text = '\n'.join(part.get('text', '') for part in parts if part.get('type') == 'text').strip()
        return LLMResult(text=text or 'I am ready to help with one small step.', provider=self.provider_name, model=self.model)
