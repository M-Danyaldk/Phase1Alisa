import asyncio
import json

from backend.app.models import TutoringState
from backend.app.services.llm.base import LLMResult
from backend.app.services.tutor_progressive_hints import (
    build_progressive_hint_reply,
    build_progressive_hint_reply_with_fallback,
    current_step_support,
)
from backend.app.utils.task_lifecycle import start_task


def _expect(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def main() -> None:
    failures: list[str] = []
    base = start_task(
        TutoringState(
            current_subject='Math',
            active_problem='45 * 6',
            current_step='45 * 6',
            current_question='What is 45 * 6?',
            expected_answer='270',
            problem_status='awaiting_step',
            mode='practice',
            status='waiting_for_student',
        ),
        '45 * 6',
        subject='Math',
    )

    first_text, first = build_progressive_hint_reply(base, help_request=True)
    second_text, second = build_progressive_hint_reply(first, help_request=True)
    third_text, third = build_progressive_hint_reply(second, help_request=True)
    support = current_step_support(third)

    _expect(first.attempt_count == second.attempt_count == third.attempt_count == 0, 'Help requests changed the answer-attempt count.', failures)
    _expect(support.help_level == 3, 'Three help requests did not reach worked-substep guidance.', failures)
    _expect(support.shown_hint_ids == ['concept', 'strategy', 'worked_substep'], 'Hint IDs repeated or advanced out of order.', failures)
    _expect(first_text != second_text != third_text, 'Progressive help repeated the same response.', failures)
    _expect('40' in second_text and '40 × 6 = 240' in third_text, 'Multiplication help did not become progressively more concrete.', failures)

    after_two_hints = second.model_copy(update={'attempt_count': 1})
    attempt_text, after_attempt = build_progressive_hint_reply(after_two_hints, help_request=False)
    attempt_support = current_step_support(after_attempt)
    _expect(attempt_support.help_level == 3 and 'worked_substep' in attempt_support.shown_hint_ids, 'A wrong attempt repeated a weaker previously shown hint.', failures)
    _expect('40 × 6 = 240' in attempt_text, 'A wrong attempt after two hints did not advance to a worked sub-step.', failures)

    division = start_task(
        TutoringState(
            current_subject='Math',
            active_problem='36 / 4',
            current_step='36 / 4',
            current_question='What is 36 / 4?',
            expected_answer='9',
            problem_status='awaiting_step',
            mode='practice',
            status='waiting_for_student',
        ),
        '36 / 4',
        subject='Math',
    )
    _, division_first = build_progressive_hint_reply(division, help_request=True)
    division_second_text, _ = build_progressive_hint_reply(division_first, help_request=True)
    _expect('4 × ? = 36' in division_second_text, 'Division strategy did not use inverse multiplication.', failures)

    asyncio.run(_check_strict_llm_fallback(failures))

    if failures:
        print('Tutor progressive-hint check failed:')
        for failure in failures:
            print(f'- {failure}')
        raise SystemExit(1)
    print('Tutor progressive-hint check passed.')
    print('- Help and answer attempts remain separate.')
    print('- Concept, strategy, and worked-substep hints advance without repetition.')
    print('- Prior hints influence the next wrong-answer response.')
    print('- Strict LLM fallback accepts safe schema hints and rejects answer leaks.')


class _FakeHintRouter:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls = 0

    async def generate(self, system: str, user: str, purpose: str = 'chat') -> LLMResult:
        self.calls += 1
        return LLMResult(text=self.text, provider='fake', model='fake-hint')


async def _check_strict_llm_fallback(failures: list[str]) -> None:
    problem = 'A theater has 28 rows with 35 seats in each row. 180 seats are occupied. How many seats are empty?'
    word_state = start_task(
        TutoringState(
            current_subject='Math',
            problem_kind='word_problem',
            full_problem=problem,
            active_problem=problem,
            current_step='28 * 35 - 180',
            current_question='Find the empty seats.',
            expected_answer='800',
            answer_label='empty seats',
            problem_status='awaiting_step',
            mode='practice',
            status='waiting_for_student',
        ),
        problem,
        subject='Math',
    )
    safe_router = _FakeHintRouter(json.dumps({
        'level': 1,
        'hint_kind': 'concept',
        'hint_text': 'First find the total number of seats before thinking about the occupied seats.',
        'follow_up_question': 'Which operation finds all the seats?',
        'reveals_final_answer': False,
    }))
    safe_text, safe_state, safe_model, _ = await build_progressive_hint_reply_with_fallback(
        word_state,
        help_request=True,
        router=safe_router,
    )
    safe_support = current_step_support(safe_state)
    _expect(safe_router.calls == 1, 'Strict fallback was not tried for a complex word-problem step.', failures)
    _expect(safe_model == 'strict-llm-progressive-hint', 'Valid strict fallback hint was not accepted.', failures)
    _expect('800' not in safe_text and 'llm_concept' in safe_support.shown_hint_ids, 'Safe strict hint leaked the final answer or did not record the LLM hint ID.', failures)

    leaking_router = _FakeHintRouter(json.dumps({
        'level': 1,
        'hint_kind': 'concept',
        'hint_text': 'The answer is 800 empty seats.',
        'follow_up_question': '',
        'reveals_final_answer': True,
    }))
    leak_text, leak_state, leak_model, _ = await build_progressive_hint_reply_with_fallback(
        word_state,
        help_request=True,
        router=leaking_router,
    )
    leak_support = current_step_support(leak_state)
    _expect(leak_model == 'deterministic-progressive-hint', 'Answer-leaking strict fallback hint was not rejected.', failures)
    _expect('llm_concept' not in leak_support.shown_hint_ids, 'Rejected strict hint was still recorded as an LLM hint.', failures)
    _expect('The answer is 800' not in leak_text, 'Rejected strict hint text was shown to the student.', failures)


if __name__ == '__main__':
    main()
