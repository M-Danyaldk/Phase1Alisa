from dataclasses import dataclass
from typing import Protocol

@dataclass
class LLMResult:
    text: str
    provider: str
    model: str
    fallback_used: bool = False

class LLMProvider(Protocol):
    provider_name: str
    model: str
    async def generate(self, system: str, user: str, max_tokens: int | None = None) -> LLMResult: ...
