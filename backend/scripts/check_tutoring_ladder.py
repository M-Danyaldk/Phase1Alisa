from backend.app.models import ChatHistoryItem, TutoringState
from backend.app.tutoring_logic import build_chat_directives
from backend.app.main import _answer_check_question, _correct_math_answer_reply, _direct_math_attempt_count, _direct_math_check_reply, _direct_math_help_expression, _direct_math_help_reply, _is_substep_of_active_problem, _substep_correct_finish_reply, _substep_reveal_continue_reply
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

    help_expression = _direct_math_help_expression('I do not know how to solve 34 x 3. Please help me step by step.')
    help_reply = _direct_math_help_reply(help_expression)
    if help_expression != '34 × 3':
        failures.append(f'Direct math help expression was {help_expression!r}, expected 34 × 3.')
    if '102' in help_reply or '30 × 3' not in help_reply or 'What is 30 × 3?' not in help_reply:
        failures.append('Direct math help reply did not give only the first useful step for 34 × 3.')

    other_help_expression = _direct_math_help_expression('Please explain 26 x 4 step by step.')
    other_help_reply = _direct_math_help_reply(other_help_expression)
    if other_help_expression != '26 × 4':
        failures.append(f'Direct math help expression was {other_help_expression!r}, expected 26 × 4.')
    if '104' in other_help_reply or '20 × 4' not in other_help_reply or 'What is 20 × 4?' not in other_help_reply:
        failures.append('Direct math help reply did not adapt the first step for another multiplication question.')

    _, _, _, first_state = build_chat_directives('100', history, TutoringState(current_question='What is 90 + 12?'))
    if first_state.attempt_count != 1 or first_state.answer_revealed:
        failures.append(f'First wrong attempt state was attempt={first_state.attempt_count} revealed={first_state.answer_revealed}.')

    _, _, _, clarification_state = build_chat_directives(
        'we were on 12-5',
        [ChatHistoryItem(role='msalisia', content='What fraction of the pizza is left?')],
        TutoringState(current_question='What fraction of the pizza is left?', attempt_count=1),
    )
    if clarification_state.attempt_count != 0 or clarification_state.current_question:
        failures.append(f'Context clarification was treated as an answer attempt: attempt={clarification_state.attempt_count} current={clarification_state.current_question!r}.')

    _, _, _, concern_state = build_chat_directives(
        'you should know what we are working on - is everything okay with you?',
        [ChatHistoryItem(role='msalisia', content='What is your answer?')],
        TutoringState(current_question='What is your answer?', attempt_count=1),
    )
    if concern_state.attempt_count != 0 or concern_state.current_question:
        failures.append(f'Tutor concern was treated as an answer attempt: attempt={concern_state.attempt_count} current={concern_state.current_question!r}.')

    clarification_directives, clarification_active, _, clarification_state = build_chat_directives(
        'we were on 12 - 5',
        [ChatHistoryItem(role='msalisia', content='Now that we know 30 x 3 = 90, let us finish the problem.')],
        TutoringState(active_problem='34 x 3', current_question='What is 60 + 30?', attempt_count=0),
    )
    clarification_text = ' '.join(clarification_directives).lower()
    if clarification_active != '34 x 3' or clarification_state.active_problem != '34 x 3':
        failures.append(f'Clarification replaced unfinished active problem: active={clarification_active!r} state={clarification_state.active_problem!r}.')
    if 'do not replace the unfinished active problem' not in clarification_text:
        failures.append('Clarification did not guard against switching away from an unfinished active problem.')

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

    directives, _, _, substep_third_state = build_chat_directives(
        '103',
        [ChatHistoryItem(role='msalisia', content='What is 60 + 30?')],
        TutoringState(active_problem='34 × 3', current_question='What is 60 + 30?', attempt_count=2),
    )
    substep_third_text = ' '.join(directives).lower()
    if not substep_third_state.answer_revealed:
        failures.append('Third wrong sub-step attempt did not mark answer as revealed.')
    if 'complete the original active problem' not in substep_third_text or 'do not give a new similar practice question' not in substep_third_text:
        failures.append('Third wrong sub-step attempt did not require finishing the active problem before similar practice.')
    if not _is_substep_of_active_problem(TutoringState(active_problem='34 × 3', current_question='What is 60 + 30?')):
        failures.append('Main sub-step guard did not detect 60 + 30 as part of 34 × 3.')

    checker = TutorAnswerChecker()
    substep_check = checker._check_math('What is 20 x 4?\n28 x 4', '94', '')
    substep_reply = _substep_reveal_continue_reply(
        substep_check,
        TutoringState(active_problem='28 x 4', current_question='What is 20 x 4?', attempt_count=3),
    )
    substep_reply_lower = substep_reply.lower()
    if 'try one similar' in substep_reply_lower or '21 x 4' in substep_reply_lower:
        failures.append('Deterministic third wrong sub-step reply still starts similar practice.')
    if '20 x 4 = 80' not in substep_reply or '28 x 4 = 80 + (8 x 4)' not in substep_reply or 'What is 8 x 4?' not in substep_reply:
        failures.append('Deterministic third wrong sub-step reply did not return to the original multiplication problem.')
    correct_substep_check = checker._check_math('What is 8 x 4?\n28 x 4', '32', '')
    correct_substep_reply = _substep_correct_finish_reply(
        correct_substep_check,
        TutoringState(active_problem='28 x 4', current_question='What is 8 x 4?', attempt_count=1),
    )
    if 'Final answer: 112' not in correct_substep_reply or 'Want to try one more' in correct_substep_reply:
        failures.append('Correct remaining sub-step did not finish the original multiplication problem.')

    wrong_check = checker.check_direct_math_statement('The problem is 34 x 3. My answer is 100. Is that correct?')
    first_direct_reply = _direct_math_check_reply(wrong_check, 1)
    second_direct_reply = _direct_math_check_reply(wrong_check, 2)
    third_direct_reply = _direct_math_check_reply(wrong_check, 3)
    if '102' in first_direct_reply:
        failures.append('Direct wrong-answer first attempt revealed the final answer.')
    if '102' in second_direct_reply or '90 + 12' not in second_direct_reply:
        failures.append('Direct wrong-answer second attempt did not give a stronger non-reveal hint.')
    if '34 × 3 = 102' not in third_direct_reply or 'Try one similar problem' not in third_direct_reply or '35 × 3' not in third_direct_reply:
        failures.append('Direct wrong-answer third attempt did not reveal and give similar practice.')
    direct_attempt = _direct_math_attempt_count(
        TutoringState(current_question='34 × 3', attempt_count=1),
        wrong_check,
    )
    if direct_attempt != 2:
        failures.append(f'Direct math attempt count was {direct_attempt}, expected 2.')

    vague_state = TutoringState(
        active_problem='12 - 5',
        current_question='What happens when you take away 5?',
        attempt_count=1,
    )
    current_answer_check = checker._check_math(_answer_check_question(vague_state, ''), '7', '')
    current_answer_reply = _correct_math_answer_reply(current_answer_check, vague_state)
    if not current_answer_check.is_correct or "Yes, that's correct!" not in current_answer_reply or '12 - 5 = 7' not in current_answer_reply:
        failures.append('Current-step math answer backstop did not accept 12 - 5 = 7 deterministically.')

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
    print('- Direct multiplication help is deterministic and does not reveal too early.')
    print('- Clarifications and tutor concerns are not graded as answer attempts.')
    print('- Correct current-step math answers can be confirmed deterministically.')
    print('- Multi-step problems finish the original problem before starting similar practice.')


if __name__ == '__main__':
    main()
