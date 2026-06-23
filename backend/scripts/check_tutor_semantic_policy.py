from backend.app.models import TutoringState
from backend.app.schemas.tutor_interpretation import TutorInputInterpretation
from backend.app.services.tutor_semantic_policy import TutorSemanticPolicy
from backend.app.utils.task_lifecycle import pause_active_task, start_task


def _payload(**updates) -> TutorInputInterpretation:
    payload = {
        'schema_version': '1.0',
        'intent': 'answer_current_step',
        'confidence': 'high',
        'answer': '78',
        'normalized_expression': None,
        'problem': None,
        'question_type': None,
        'refers_to_task': 'active_task',
        'requested_action': 'check_answer',
        'emotion': None,
        'needs_clarification': False,
        'clarification_question': None,
        'interpretation_note': 'Student supplied an answer.',
    }
    payload.update(updates)
    return TutorInputInterpretation.model_validate(payload)


def _expect(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def main() -> None:
    failures: list[str] = []
    policy = TutorSemanticPolicy()
    active = start_task(TutoringState(
        current_subject='Math',
        active_problem='72 + 48',
        current_step='72 + 48',
        current_question='What is 72 + 48?',
        expected_answer='120',
        problem_status='awaiting_step',
        mode='practice',
        status='waiting_for_student',
    ), '72 + 48')

    answer = policy.resolve(_payload(), active)
    _expect(answer.label == 'answer_current_step' and answer.allowed, 'High-confidence active-step answer was blocked.', failures)

    no_step = policy.resolve(_payload(), TutoringState(current_subject='Math'))
    _expect(no_step.label == 'clarification_about_context' and not no_step.allowed, 'Answer without an active step was allowed.', failures)

    medium_switch = policy.resolve(_payload(
        intent='switch_problem',
        confidence='medium',
        answer=None,
        normalized_expression='64 + 55',
        refers_to_task='new_task',
        requested_action='switch',
        interpretation_note='Student may want a new problem first.',
    ), active)
    _expect(medium_switch.needs_clarification and not medium_switch.allowed, 'Medium-confidence switch changed state without confirmation.', failures)

    high_switch = policy.resolve(_payload(
        intent='switch_problem',
        confidence='high',
        answer=None,
        normalized_expression='64 + 55',
        refers_to_task='new_task',
        requested_action='switch',
        interpretation_note='Student clearly wants the new expression first.',
    ), active)
    _expect(high_switch.label == 'switch_request' and high_switch.allowed, 'High-confidence verified switch was not allowed.', failures)

    new_problem_no_active = policy.resolve(_payload(
        intent='new_problem',
        confidence='high',
        answer=None,
        normalized_expression='64 + 55',
        refers_to_task='new_task',
        requested_action='solve',
        interpretation_note='Student supplied a new expression.',
    ), TutoringState(current_subject='Math'))
    _expect(new_problem_no_active.label == 'new_problem' and new_problem_no_active.allowed, 'Fresh new problem was blocked when no task was active.', failures)

    new_problem_while_active = policy.resolve(_payload(
        intent='new_problem',
        confidence='high',
        answer=None,
        normalized_expression='64 + 55',
        refers_to_task='new_task',
        requested_action='solve',
        interpretation_note='Student supplied a separate expression while another task is active.',
    ), active)
    _expect(new_problem_while_active.needs_clarification and not new_problem_while_active.allowed, 'New problem while active skipped switch confirmation.', failures)

    resume_without_pause = policy.resolve(_payload(
        intent='resume',
        confidence='high',
        answer=None,
        refers_to_task='paused_task',
        requested_action='resume',
        interpretation_note='Student asked to resume.',
    ), TutoringState(current_subject='Math'))
    _expect(resume_without_pause.needs_clarification and not resume_without_pause.allowed, 'Resume was allowed with no paused task.', failures)

    paused = pause_active_task(active)
    resume_with_pause = policy.resolve(_payload(
        intent='resume',
        confidence='high',
        answer=None,
        refers_to_task='paused_task',
        requested_action='resume',
        interpretation_note='Student asked to resume.',
    ), paused)
    _expect(resume_with_pause.label == 'resume' and resume_with_pause.allowed, 'Resume was blocked despite a paused task.', failures)

    hint_no_task = policy.resolve(_payload(
        intent='request_hint',
        confidence='high',
        answer=None,
        refers_to_task='active_task',
        requested_action='give_hint',
        interpretation_note='Student asked for a hint.',
    ), TutoringState(current_subject='Math'))
    _expect(hint_no_task.needs_clarification and not hint_no_task.allowed, 'Hint request without an active task was allowed.', failures)

    continuation_yes = policy.resolve(_payload(
        intent='continuation_yes',
        answer=None,
        question_type='continuation_choice',
        requested_action='continue',
        interpretation_note='Student wants another practice question.',
    ), TutoringState(
        current_subject='Math',
        mode='awaiting_more_practice_choice',
        status='waiting_for_student',
        problem_status='finished',
    ))
    _expect(continuation_yes.label == 'continuation_yes' and continuation_yes.allowed, 'Continuation yes was not allowed through the policy.', failures)

    stronger_hint = policy.resolve(_payload(
        intent='stronger_hint_request',
        answer=None,
        question_type='arithmetic_single_step',
        requested_action='give_hint',
        interpretation_note='Student asked for a stronger hint.',
    ), active)
    _expect(stronger_hint.label == 'help_request' and stronger_hint.allowed, 'Stronger hint request was not mapped into help routing.', failures)

    reading_state = start_task(TutoringState(
        current_subject='ELA',
        active_problem='What is the main idea of the story?',
        current_question='What is the main idea of the story?',
        expected_answer='The big message of the story.',
        skill='main idea and key details',
        problem_status='awaiting_step',
        mode='practice',
        status='waiting_for_student',
    ), 'What is the main idea of the story?')
    reading_answer = policy.resolve(_payload(
        answer='The big message of the story.',
        question_type='reading_text',
        interpretation_note='Student answered the current reading question.',
    ), reading_state)
    _expect(reading_answer.label == 'answer_current_step' and reading_answer.allowed, 'Reading answer route was not allowed through deterministic policy.', failures)

    mismatched_route = policy.resolve(_payload(
        answer='7/8',
        question_type='fraction_comparison',
        interpretation_note='Route mismatch for current active prompt.',
    ), reading_state)
    _expect(
        mismatched_route.label == 'clarification_about_context' and not mismatched_route.allowed,
        'Route mismatch did not get blocked by deterministic policy.',
        failures,
    )

    continuation_without_prompt = policy.resolve(_payload(
        intent='continuation_yes',
        answer=None,
        question_type='continuation_choice',
        requested_action='continue',
        interpretation_note='Student wants another practice question.',
    ), active)
    _expect(
        continuation_without_prompt.label == 'clarification_about_context' and not continuation_without_prompt.allowed,
        'Continuation intent was allowed without an active continuation-choice prompt.',
        failures,
    )

    if failures:
        print('Tutor semantic policy check failed:')
        for failure in failures:
            print(f'- {failure}')
        raise SystemExit(1)

    print('Tutor semantic policy check passed.')
    print('- Typed LLM interpretations are converted through a deterministic policy table.')
    print('- State-changing actions require high confidence and a valid task context.')
    print('- Invalid answers, switches, resumes, and hint requests become clarification instead of state changes.')


if __name__ == '__main__':
    main()
