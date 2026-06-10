from backend.app.models import ChatHistoryItem, TutoringState
from backend.app.tutoring_logic import build_chat_directives
from backend.app.main import _direct_math_attempt_count, _direct_math_check_reply
from backend.app.services.tutor_answer_checker import TutorAnswerChecker


def main() -> None:
    failures: list[str] = []
    history = [ChatHistoryItem(role='msalisia', content='What is 90 + 12?')]

    directives, _, _, direct_state = build_chat_directives(
        'I do not know how to solve 34 x 3. Please help me step by step.',
        [],
        TutoringState(),
    )
    direct_text = ' '.join(directives).lower()
    if 'first useful worked step' not in direct_text or 'do not finish the whole problem' not in direct_text:
        failures.append('Direct step-by-step math help did not require one worked step before finishing.')
    if direct_state.attempt_count != 0 or direct_state.answer_revealed:
        failures.append(f'Direct help state was attempt={direct_state.attempt_count} revealed={direct_state.answer_revealed}.')

    opening_math_history = [ChatHistoryItem(role='msalisia', content='Let us start with one quick question: what is 6 × 7?')]
    directives, _, _, override_state = build_chat_directives(
        'I do not know how to solve 34 x 3. Please help me step by step.',
        opening_math_history,
        TutoringState(current_question='what is 6 × 7?'),
    )
    override_text = ' '.join(directives).lower()
    if override_state.attempt_count != 0 or override_state.current_question:
        failures.append(f'Direct math help after opener was treated as answer attempt: attempt={override_state.attempt_count} current={override_state.current_question!r}.')
    if 'new direct question' not in override_text or '34 x 3' not in override_text:
        failures.append('Direct math help after opener did not override the previous quick question.')

    opening_reading_history = [ChatHistoryItem(role='msalisia', content='What does sprinted mean?')]
    directives, _, _, reading_state = build_chat_directives(
        'Can you help me understand what main idea means? Give me one small example.',
        opening_reading_history,
        TutoringState(current_question='What does sprinted mean?'),
    )
    reading_text = ' '.join(directives).lower()
    if reading_state.attempt_count != 0 or reading_state.current_question:
        failures.append(f'Direct reading help after opener was treated as answer attempt: attempt={reading_state.attempt_count} current={reading_state.current_question!r}.')
    if 'new direct question' not in reading_text or 'real question' not in reading_text:
        failures.append('Direct reading help after opener did not override the previous quick question.')

    _, _, _, first_state = build_chat_directives('100', history, TutoringState(current_question='What is 90 + 12?'))
    if first_state.attempt_count != 1 or first_state.answer_revealed:
        failures.append(f'First wrong attempt state was attempt={first_state.attempt_count} revealed={first_state.answer_revealed}.')

    directives, _, _, second_state = build_chat_directives(
        '101',
        history,
        TutoringState(current_question='What is 90 + 12?', attempt_count=1),
    )
    second_text = ' '.join(directives).lower()
    if second_state.attempt_count != 2 or second_state.answer_revealed:
        failures.append(f'Second wrong attempt state was attempt={second_state.attempt_count} revealed={second_state.answer_revealed}.')
    if 'stronger hint' not in second_text or 'do not reveal the final answer' not in second_text:
        failures.append('Second wrong attempt did not require a stronger hint without reveal.')

    directives, _, _, third_state = build_chat_directives(
        '103',
        history,
        TutoringState(current_question='What is 90 + 12?', attempt_count=2),
    )
    third_text = ' '.join(directives).lower()
    if third_state.attempt_count != 3 or not third_state.answer_revealed:
        failures.append(f'Third wrong attempt state was attempt={third_state.attempt_count} revealed={third_state.answer_revealed}.')
    if 'give the correct answer' not in third_text or 'one new similar same-topic question' not in third_text:
        failures.append('Third wrong attempt did not require answer reveal plus similar practice.')

    checker = TutorAnswerChecker()
    wrong_check = checker.check_direct_math_statement('The problem is 34 x 3. My answer is 100. Is that correct?')
    first_direct_reply = _direct_math_check_reply(wrong_check, 1)
    second_direct_reply = _direct_math_check_reply(wrong_check, 2)
    third_direct_reply = _direct_math_check_reply(wrong_check, 3)
    if '102' in first_direct_reply:
        failures.append('Direct wrong-answer first attempt revealed the final answer.')
    if '102' in second_direct_reply or '90 + 12' not in second_direct_reply:
        failures.append('Direct wrong-answer second attempt did not give a stronger non-reveal hint.')
    if '34 × 3 = 102' not in third_direct_reply or '45 × 4' not in third_direct_reply:
        failures.append('Direct wrong-answer third attempt did not reveal and give similar practice.')
    direct_attempt = _direct_math_attempt_count(
        TutoringState(current_question='34 × 3', attempt_count=1),
        wrong_check,
    )
    if direct_attempt != 2:
        failures.append(f'Direct math attempt count was {direct_attempt}, expected 2.')

    if failures:
        print('Tutoring ladder check failed:')
        for failure in failures:
            print(f'- {failure}')
        raise SystemExit(1)

    print('Tutoring ladder check passed.')
    print('- Direct step-by-step help starts with one worked step.')
    print('- First wrong try gives a small hint only.')
    print('- Second wrong try gives a stronger hint without revealing.')
    print('- Third wrong try reveals, explains, and gives similar practice.')
    print('- Direct "my answer is ..." math checks follow the same ladder.')
    print('- New direct questions override the opening quick question.')


if __name__ == '__main__':
    main()
