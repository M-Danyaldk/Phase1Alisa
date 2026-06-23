import backend.app.main as main_module
import backend.app.services.voice_service as voice_module
from backend.app.models import TutorHelperBranch, TutorStepRecord, TutorStepSupportState, TutoringState
from backend.app.tutor_math_practice_bank import select_tutor_math_question


def _expect(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def _legacy_student_problem_state() -> TutoringState:
    return TutoringState(
        current_subject='Math',
        problem_id='legacy-problem',
        problem_kind='word_problem',
        word_problem_schema={'original_text': 'There are 7 boxes with 2 balls each.'},
        main_problem='There are 7 boxes with 2 balls each. How many balls are there?',
        active_problem='There are 7 boxes with 2 balls each. How many balls are there?',
        full_problem='There are 7 boxes with 2 balls each. How many balls are there?',
        ordered_steps=[TutorStepRecord(step_id='step-1', expression='7 * 2', expected_answer='14')],
        current_step_index=0,
        current_step_id='step-1',
        current_expression='7 * 2',
        current_step='7 * 2',
        current_question='What is 7 x 2?',
        expected_answer='14',
        attempt_count=2,
        attempts_per_step={'legacy:step-1': 2},
        support_per_step={'legacy:step-1': TutorStepSupportState(help_level=2, shown_hint_ids=['concept', 'strategy'])},
        helper_branch=TutorHelperBranch(branch_id='helper-1', branch_type='side_question', question='what is denominator?', status='active'),
        pending_input_kind='ambiguous_word_problem',
        pending_new_problem='How many boxes are there?',
        tutor_practice_question_id='old-practice',
        tutor_practice_grade=4,
        tutor_practice_topic='fractions',
        tutor_practice_hint_1='old hint 1',
        tutor_practice_hint_2='old hint 2',
        tutor_practice_explanation='old explanation',
        recent_tutor_practice_question_ids=['old-practice'],
        problem_status='awaiting_step',
        mode='practice',
        status='waiting_for_student',
    )


def main() -> None:
    failures: list[str] = []
    practice_question = select_tutor_math_question(4, topic='fractions')
    base_state = _legacy_student_problem_state()

    chat_practice = main_module._tutor_math_question_state(base_state, 'Math', 'ready', practice_question)
    voice_practice = voice_module._tutor_math_question_state(base_state, 'Math', 'ready', practice_question)

    for label, state in [('chat', chat_practice), ('voice', voice_practice)]:
        _expect(state.problem_kind == '', f'{label} tutor-practice state kept the earlier problem kind.', failures)
        _expect(not state.ordered_steps, f'{label} tutor-practice state kept structured steps from the student problem.', failures)
        _expect(not state.attempts_per_step and not state.support_per_step, f'{label} tutor-practice state kept old attempt or hint history.', failures)
        _expect(state.pending_input_kind == '' and state.pending_new_problem == '', f'{label} tutor-practice state kept pending student-problem clarification fields.', failures)
        _expect(state.helper_branch.status == 'idle', f'{label} tutor-practice state kept a helper branch from the earlier student problem.', failures)
        _expect(state.current_question == practice_question.question, f'{label} tutor-practice state did not store the new practice question.', failures)
        _expect(state.problem_status == 'tutor_practice' and state.mode == 'tutor_practice_question', f'{label} tutor-practice state did not enter tutor-practice mode cleanly.', failures)
        _expect(state.tutor_practice_question_id == practice_question.id, f'{label} tutor-practice state did not store the new practice question id.', failures)

    if failures:
        print('Tutor flow-alignment check failed:')
        for failure in failures:
            print(f'- {failure}')
        raise SystemExit(1)

    print('Tutor flow-alignment check passed.')
    print('- Starting tutor practice clears stale student-problem structure, attempts, helper branches, and pending clarification state.')


if __name__ == '__main__':
    main()
