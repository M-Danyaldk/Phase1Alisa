import re
from fractions import Fraction

from pydantic import BaseModel, Field

from ..assessment_validation import normalize_math_text, safe_eval_expression
from ..models import TutoringState
from ..utils.task_lifecycle import reconcile_task_lifecycle


class MathResponseGuardResult(BaseModel):
    text: str
    response_kind: str = 'explanation'
    valid: bool = True
    repaired: bool = False
    violations: list[str] = Field(default_factory=list)


class TutorMathResponseGuard:
    """Enforce one output contract after either rules or an LLM compose a reply."""

    def validate(
        self,
        text: str,
        state: TutoringState,
        *,
        intent_label: str = '',
        source: str = '',
    ) -> MathResponseGuardResult:
        verified_state = reconcile_task_lifecycle(state)
        reply = self._normalize_notation(str(text or '').strip())
        violations: list[str] = []

        if not reply:
            violations.append('empty_response')
        if reply.count('?') > 1:
            violations.append('multiple_questions')
        if self._missing_required_step_prompt(reply, verified_state):
            violations.append('missing_current_step_prompt')
        if self._has_incorrect_equation(reply):
            violations.append('incorrect_arithmetic')
        if self._has_incorrect_answer_claim(reply, verified_state):
            violations.append('incorrect_answer_claim')
        if self._reveals_too_early(reply, verified_state):
            violations.append('premature_answer_reveal')
        if self._references_stale_main_problem(reply, verified_state):
            violations.append('stale_problem_reference')
        if intent_label and intent_label != 'answer_current_step' and self._uses_wrong_answer_language(reply):
            violations.append('non_answer_graded_as_wrong')

        kind = self._response_kind(reply, verified_state, intent_label)
        if not violations:
            return MathResponseGuardResult(text=reply, response_kind=kind)

        repaired = self._safe_repair(verified_state, intent_label, violations)
        return MathResponseGuardResult(
            text=repaired,
            response_kind='redirect' if verified_state.current_question or verified_state.current_step else 'clarification',
            valid=False,
            repaired=True,
            violations=violations,
        )

    def apply_metadata(self, state: TutoringState, result: MathResponseGuardResult, source: str = '') -> TutoringState:
        verified_state = reconcile_task_lifecycle(state)
        return verified_state.model_copy(update={
            'last_response_kind': result.response_kind,
            'last_response_source': source,
            'last_response_validated': True,
            'last_response_repaired': result.repaired,
            'last_response_violations': list(result.violations),
        })

    def _has_incorrect_equation(self, text: str) -> bool:
        normalized = (
            normalize_math_text(text)
            .replace('×', '*')
            .replace('÷', '/')
            .replace('Ã—', '*')
            .replace('Ã·', '/')
        )
        equations = re.findall(
            r'(?<![\w/])([()0-9.\s+\-*/]+?)\s*=\s*(-?\d+(?:\.\d+)?(?:/\d+)?)',
            normalized,
        )
        for expression, stated in equations:
            expression = expression.strip(' .')
            if not expression or not any(operator in expression for operator in '+-*/'):
                continue
            expected = safe_eval_expression(expression)
            actual = self._numeric_value(stated)
            if expected is not None and actual is not None and expected != actual:
                return True
        return False

    def _reveals_too_early(self, text: str, state: TutoringState) -> bool:
        if state.attempt_count >= 3 or state.answer_revealed or not state.expected_answer:
            return False
        if state.correctness_status not in {'incorrect', 'partially_correct', 'unclear'}:
            return False
        expected = re.escape(state.expected_answer.strip())
        reveal_patterns = (
            rf'\b(?:final\s+)?answer\s+(?:is|:)\s*{expected}\b',
            rf'=\s*{expected}\b',
        )
        return any(re.search(pattern, text, re.I) for pattern in reveal_patterns)

    def _has_incorrect_answer_claim(self, text: str, state: TutoringState) -> bool:
        expected = self._numeric_value(state.expected_answer)
        if expected is None:
            return False
        claims = re.findall(
            r'\b(?:the\s+answer|final\s+answer|(?<!your\s)answer)\s*(?:is|:)\s*(-?\d+(?:\.\d+)?(?:/\d+)?)',
            text,
            re.I,
        )
        return any((value := self._numeric_value(claim)) is not None and value != expected for claim in claims)

    def _numeric_value(self, text: str) -> Fraction | None:
        match = re.fullmatch(r'\s*(-?\d+(?:\.\d+)?(?:/\d+)?)\s*', str(text or ''))
        if not match:
            return None
        try:
            return Fraction(match.group(1))
        except (ValueError, ZeroDivisionError):
            return None

    def _references_stale_main_problem(self, text: str, state: TutoringState) -> bool:
        active = self._canonical_problem(state.active_problem or state.main_problem)
        if not active or state.problem_status in {'finished', 'idle'}:
            return False
        matches = re.findall(r'\*\*?Main problem:?\*\*?\s*([^\n]+)', text, re.I)
        for match in matches:
            mentioned = self._canonical_problem(match)
            if mentioned and mentioned != active:
                return True
        return False

    def _missing_required_step_prompt(self, text: str, state: TutoringState) -> bool:
        unresolved = bool(state.current_question or state.current_step)
        retrying = state.correctness_status in {'incorrect', 'partially_correct', 'unclear'} and state.attempt_count < 3
        return unresolved and retrying and '?' not in text

    def _uses_wrong_answer_language(self, text: str) -> bool:
        if re.search(r'\bwill not count (?:as|against)\b', text, re.I):
            return False
        return bool(re.search(r'\b(not quite|wrong answer|incorrect|try that answer again|nice try)\b', text, re.I))

    def _safe_repair(self, state: TutoringState, intent_label: str, violations: list[str]) -> str:
        question = self._clean_verified_question(state.current_question or state.current_step)
        problem = (state.active_problem or state.main_problem).strip()
        if 'non_answer_graded_as_wrong' in violations:
            opening = 'I understand. That message will not count as an answer attempt.'
        elif 'incorrect_arithmetic' in violations or 'incorrect_answer_claim' in violations:
            opening = 'Let me correct that and keep us on the verified Math step.'
        elif 'premature_answer_reveal' in violations:
            opening = 'Letâ€™s keep the answer hidden and work through the current step.'
        else:
            opening = 'Letâ€™s stay with the current Math problem one step at a time.'
        if question:
            return f'{opening}\n\n{question}'
        if problem:
            return f'{opening}\n\n**Problem:** {problem}'
        return f'{opening}\n\nWhat Math problem should we work on?'

    def _response_kind(self, text: str, state: TutoringState, intent_label: str) -> str:
        lower = text.lower()
        if state.emotional_support_mode:
            return 'emotional_support'
        if 'hint' in lower or (state.correctness_status in {'incorrect', 'partially_correct'} and state.attempt_count < 3):
            return 'hint'
        if state.answer_revealed or '**final answer:**' in lower or 'final answer:' in lower:
            return 'completion'
        if intent_label in {'clarification_about_context', 'related_question', 'help_request'}:
            return 'explanation'
        if '?' in text:
            return 'step_prompt'
        return 'explanation'

    def _normalize_notation(self, text: str) -> str:
        text = re.sub(r'(?<=\d)\s*\*\s*(?=\d)', ' × ', text)
        return re.sub(r'[ \t]+', ' ', text)

    def _canonical_problem(self, text: str) -> str:
        normalized = normalize_math_text(str(text or '')).lower()
        normalized = normalized.replace('×', '*').replace('÷', '/').replace('Ã—', '*').replace('Ã·', '/')
        return re.sub(r'[^a-z0-9+\-*/().]', '', normalized)

    def _clean_verified_question(self, text: str) -> str:
        cleaned = str(text or '').strip()
        for marker in (
            'Now try this step:',
            'Try this same question again:',
            'Try the same question one more time:',
            'Try this same question:',
        ):
            if cleaned.startswith(marker):
                cleaned = cleaned.split(marker, 1)[-1].strip()
        return cleaned
