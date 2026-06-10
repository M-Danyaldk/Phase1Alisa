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


if __name__ == '__main__':
    main()
