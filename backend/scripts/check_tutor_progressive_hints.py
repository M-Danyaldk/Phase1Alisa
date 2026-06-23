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

    fraction_compare = start_task(
        TutoringState(
            current_subject='Math',
            active_problem='Which is larger: 7/8 or 5/8?',
            current_step='Which is larger: 7/8 or 5/8?',
            current_question='Which is larger: 7/8 or 5/8?',
            expected_answer='7/8',
            skill='fraction comparison',
            tutor_practice_topic='equivalent fractions and decimals',
            problem_status='tutor_practice',
            mode='tutor_practice_question',
            status='waiting_for_student',
        ),
        'Which is larger: 7/8 or 5/8?',
        subject='Math',
    )
    fraction_text_1, fraction_state_1 = build_progressive_hint_reply(fraction_compare, help_request=True)
    fraction_text_2, _ = build_progressive_hint_reply(fraction_state_1, help_request=True)
    _expect('same denominator' in fraction_text_1.lower() or 'numerator' in fraction_text_1.lower(), 'Fraction-comparison first hint was not route-aware.', failures)
    _expect('7 or 5' in fraction_text_2 or '7/8' in fraction_text_2, 'Fraction-comparison stronger hint did not stay grounded in the actual choices.', failures)

    equivalent = start_task(
        TutoringState(
            current_subject='Math',
            active_problem='What fraction is equivalent to 1/2: 2/4 or 1/4?',
            current_step='What fraction is equivalent to 1/2: 2/4 or 1/4?',
            current_question='What fraction is equivalent to 1/2: 2/4 or 1/4?',
            expected_answer='2/4',
            skill='equivalent fractions',
            tutor_practice_topic='equivalent fractions and decimals',
            problem_status='tutor_practice',
            mode='tutor_practice_question',
            status='waiting_for_student',
        ),
        'What fraction is equivalent to 1/2: 2/4 or 1/4?',
        subject='Math',
    )
    equivalent_text_1, equivalent_state_1 = build_progressive_hint_reply(equivalent, help_request=True)
    equivalent_text_2, _ = build_progressive_hint_reply(equivalent_state_1, help_request=True)
    _expect('equivalent fractions name the same amount' in equivalent_text_1.lower(), 'Equivalent-fraction first hint did not explain the equivalence idea.', failures)
    _expect('same amount as 1/2' in equivalent_text_2.lower(), 'Equivalent-fraction stronger hint did not stay anchored to the target fraction.', failures)

    conceptual = start_task(
        TutoringState(
            current_subject='Math',
            active_problem='How many fourths make one whole?',
            current_step='How many fourths make one whole?',
            current_question='How many fourths make one whole?',
            expected_answer='4',
            skill='unit fractions',
            problem_status='tutor_practice',
            mode='tutor_practice_question',
            status='waiting_for_student',
        ),
        'How many fourths make one whole?',
        subject='Math',
    )
    conceptual_text, _ = build_progressive_hint_reply(conceptual, help_request=True)
    _expect('whole' in conceptual_text.lower() and 'equal parts' in conceptual_text.lower(), 'Conceptual-math hint was not grounded in the whole/parts idea.', failures)

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

    fraction_state = start_task(
        TutoringState(
            current_subject='Math',
            active_problem='Which is larger: 7/8 or 5/8?',
            current_step='Which is larger: 7/8 or 5/8?',
            current_question='Which is larger: 7/8 or 5/8?',
            expected_answer='7/8',
            skill='fraction comparison',
            tutor_practice_topic='equivalent fractions and decimals',
            problem_status='tutor_practice',
            mode='tutor_practice_question',
            status='waiting_for_student',
        ),
        'Which is larger: 7/8 or 5/8?',
        subject='Math',
    )
    mismatch_router = _FakeHintRouter(json.dumps({
        'level': 1,
        'hint_kind': 'concept',
        'hint_text': 'Use the related multiplication fact: 8 × ? = 7.',
        'follow_up_question': '',
        'reveals_final_answer': False,
    }))
    mismatch_text, mismatch_state, mismatch_model, _ = await build_progressive_hint_reply_with_fallback(
        fraction_state,
        help_request=True,
        router=mismatch_router,
    )
    mismatch_support = current_step_support(mismatch_state)
    _expect(mismatch_model == 'deterministic-progressive-hint', 'Route-mismatched fraction hint was not rejected.', failures)
    _expect('llm_concept' not in mismatch_support.shown_hint_ids, 'Route-mismatched LLM hint was still recorded.', failures)
    _expect('same denominator' in mismatch_text.lower() or 'numerator' in mismatch_text.lower(), 'Rejected route-mismatched hint did not fall back to the grounded fraction hint.', failures)

    guard_leak_router = _FakeHintRouter(json.dumps({
        'level': 1,
        'hint_kind': 'concept',
        'hint_text': 'I understand. That message will not count as an answer attempt.',
        'follow_up_question': 'What Math problem should we work on?',
        'reveals_final_answer': False,
    }))
    guard_text, guard_state, guard_model, _ = await build_progressive_hint_reply_with_fallback(
        word_state,
        help_request=True,
        router=guard_leak_router,
    )
    guard_support = current_step_support(guard_state)
    _expect(guard_model == 'deterministic-progressive-hint', 'Guard-leak hint text was not rejected.', failures)
    _expect('llm_concept' not in guard_support.shown_hint_ids, 'Guard-leak hint was still recorded as an LLM hint.', failures)
    _expect('what math problem should we work on' not in guard_text.lower(), 'Rejected guard-leak hint text reached the student.', failures)


if __name__ == '__main__':
    main()
