from .base import LLMResult
from .claude_provider import ClaudeProvider
from .groq_provider import GroqProvider
from ...config import get_settings
from ..app_data_service import AppDataService

class LLMRouter:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.providers = {
            'claude': ClaudeProvider(),
            'groq': GroqProvider(),
        }

    async def generate(self, system: str, user: str, purpose: str = 'chat') -> LLMResult:
        primary = self._resolve_provider(self.settings.primary_llm_provider)
        fallback = self._resolve_provider(self.settings.fallback_llm_provider)
        max_tokens = self._max_tokens_for_purpose(purpose)

        if primary is None:
            if fallback is not None and fallback.available():
                result = await fallback.generate(system, user, max_tokens=max_tokens)
                result.fallback_used = True
                await self._record(result, purpose)
                return result
            return self._local_fallback(purpose, fallback_used=False)

        if primary.available():
            try:
                result = await primary.generate(system, user, max_tokens=max_tokens)
                await self._record(result, purpose)
                return result
            except Exception as exc:
                if not self.settings.fallback_on_llm_error:
                    raise exc
                if fallback is not None and fallback.provider_name != primary.provider_name and fallback.available():
                    result = await fallback.generate(system, user, max_tokens=max_tokens)
                    result.fallback_used = True
                    await self._record(result, purpose)
                    return result
                return self._local_fallback(purpose, fallback_used=True)

        if fallback is not None and fallback.provider_name != primary.provider_name and fallback.available():
            result = await fallback.generate(system, user, max_tokens=max_tokens)
            result.fallback_used = True
            await self._record(result, purpose)
            return result

        return self._local_fallback(purpose, fallback_used=False)

    def _resolve_provider(self, provider_name: str):
        normalized = self.settings.normalized_llm_provider(provider_name)
        if not self.settings.llm_provider_supported(normalized):
            return None
        return self.providers[normalized]

    def _max_tokens_for_purpose(self, purpose: str) -> int:
        if purpose == 'chat':
            return min(self.settings.chat_max_output_tokens, 800)
        if purpose == 'assessment':
            return min(self.settings.assessment_max_output_tokens, 1600)
        if purpose == 'report':
            return min(self.settings.report_max_output_tokens, 1600)
        if purpose == 'homework':
            return min(self.settings.homework_max_output_tokens, 1200)
        if purpose == 'classifier':
            return min(self.settings.classifier_max_output_tokens, 300)
        return self.settings.max_output_tokens

    async def _record(self, result: LLMResult, purpose: str) -> None:
        try:
            await AppDataService().record_llm_event(result.provider, result.model, purpose, result.fallback_used)
        except Exception:
            pass

    def _local_fallback(self, purpose: str, fallback_used: bool) -> LLMResult:
        templates = {
            'chat': 'No worries, I will help. Let us do one small step at a time, and I will show the next part clearly.',
            'assessment': '{"estimated_level":"Needs live LLM evaluation","score_label":"Local fallback","strengths":["Student attempted the task"],"learning_gaps":["Connect Claude or Groq to evaluate accurately"],"recommended_progression":["Review one concept at a time with Ms Alisia"],"parent_summary":"The assessment was received, but live LLM evaluation is not connected yet."}',
            'homework': 'Nice try. Your file was received in Phase 1, but detailed worksheet and handwriting analysis will be added in the next phase. For now, I can help from your note and suggest one small next step.'
        }
        return LLMResult(text=templates.get(purpose, templates['chat']), provider='local_fallback', model='rules', fallback_used=fallback_used)
