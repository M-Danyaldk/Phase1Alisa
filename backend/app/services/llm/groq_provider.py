import httpx
from .base import LLMResult
from ...config import get_settings

class GroqProvider:
    provider_name = 'groq'

    def __init__(self) -> None:
        self.settings = get_settings()
        self.model = self.settings.groq_model

    def available(self) -> bool:
        return bool(self.settings.groq_api_key.strip())

    async def generate(self, system: str, user: str, max_tokens: int | None = None) -> LLMResult:
        if not self.available():
            raise RuntimeError('Groq API key is missing')
        payload = {
            'model': self.model,
            'temperature': self.settings.temperature,
            'max_tokens': max_tokens or self.settings.max_output_tokens,
            'messages': [
                {'role': 'system', 'content': system},
                {'role': 'user', 'content': user}
            ]
        }
        headers = {
            'Authorization': f'Bearer {self.settings.groq_api_key}',
            'content-type': 'application/json'
        }
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.post(self.settings.groq_api_url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
        text = data.get('choices', [{}])[0].get('message', {}).get('content', '').strip()
        return LLMResult(text=text or 'I am ready to help with one small step.', provider=self.provider_name, model=self.model)
