import json
import re

from ..models import ChatHistoryItem, TutoringState
from ..schemas.tutor_interpretation import TutorInputInterpretation
from .llm.router import LLMRouter


def _history_role(item: ChatHistoryItem | dict) -> str:
    if isinstance(item, dict):
        return str(item.get('role') or '')
    return str(getattr(item, 'role', '') or '')


def _history_content(item: ChatHistoryItem | dict) -> str:
    if isinstance(item, dict):
        return str(item.get('content') or '')
    return str(getattr(item, 'content', '') or '')


class TutorSemanticInterpreter:
    """Use an LLM as a typed language interpreter, never as a state manager."""

    def __init__(self, router: LLMRouter | None = None) -> None:
        self.router = router or LLMRouter()

    async def interpret(
        self,
        subject: str,
        message: str,
        history: list[ChatHistoryItem],
        state: TutoringState,
    ) -> TutorInputInterpretation:
        system = (
            'You are a strict tutor input interpreter for Grades 3-6. '
            'Return one JSON object only. It must validate against the supplied JSON schema. '
            'Interpret the child message; do not answer the problem and do not calculate for the child. '
            'Extract only the student\'s intended final answer into answer. '
            'Never output tutor lifecycle fields or invent quantities. '
            'Use high confidence only when the meaning and task reference are clear. '
            f'JSON schema: {json.dumps(TutorInputInterpretation.model_json_schema(), separators=(",", ":"))}'
        )
        recent_history = '\n'.join(f'{_history_role(item)}: {_history_content(item)}' for item in history[-4:])
        user = (
            f'Current tutor subject: {subject}\n'
            f'Active task: {state.active_problem or state.main_problem or "none"}\n'
            f'Current step: {state.current_question or state.current_step or "none"}\n'
            f'Paused task available: {"yes" if state.paused_main_problem or any(record.status == "paused" for record in state.task_records) else "no"}\n'
            f'Recent history:\n{recent_history or "none"}\n'
            f'Student message: {message}'
        )
        try:
            result = await self.router.generate(system=system, user=user, purpose='classifier')
            parsed = self._extract_json(result.text)
            return TutorInputInterpretation.model_validate(parsed)
        except Exception:
            return self.safe_unclear()

    def safe_unclear(self) -> TutorInputInterpretation:
        return TutorInputInterpretation(
            intent='unclear',
            confidence='low',
            answer=None,
            normalized_expression=None,
            problem=None,
            refers_to_task='unknown',
            requested_action='clarify',
            emotion=None,
            needs_clarification=True,
            clarification_question='Do you want to answer the current step, or work on a different problem?',
            interpretation_note='The message could not be interpreted safely.',
        )

    def _extract_json(self, text: str) -> dict:
        raw = str(text or '').strip()
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r'\{.*\}', raw, re.S)
            if not match:
                raise
            parsed = json.loads(match.group(0))
        if not isinstance(parsed, dict):
            raise ValueError('Semantic interpretation must be a JSON object.')
        return parsed
