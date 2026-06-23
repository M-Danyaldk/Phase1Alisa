from __future__ import annotations

from ..models import TutorHelperBranch, TutoringState
from ..tutor_math_practice_bank import TutorMathPracticeQuestion


def clear_tutor_practice_artifacts(state: TutoringState) -> TutoringState:
    return state.model_copy(update={
        'tutor_practice_question_id': '',
        'tutor_practice_grade': 0,
        'tutor_practice_topic': '',
        'tutor_practice_hint_1': '',
        'tutor_practice_hint_2': '',
        'tutor_practice_explanation': '',
        'attempts_per_step': {},
        'support_per_step': {},
        'helper_branch': TutorHelperBranch(),
        'queued_followup_questions': [],
        'attempt_count': 0,
        'hint_given': False,
        'answer_revealed': False,
        'next_similar_question': '',
        'final_answer': '',
    })


def align_tutor_practice_transition(
    previous_state: TutoringState,
    next_state: TutoringState,
) -> TutoringState:
    if previous_state.mode not in {'tutor_practice_question', 'awaiting_more_practice_choice'}:
        return next_state
    if next_state.problem_status == 'tutor_practice' or next_state.mode == 'awaiting_more_practice_choice':
        return next_state
    return clear_tutor_practice_artifacts(next_state)


def build_aligned_tutor_practice_state(
    state: TutoringState,
    *,
    subject: str,
    student_message: str,
    practice_question: TutorMathPracticeQuestion,
    recent_question_ids: list[str],
    source_label: str,
) -> TutoringState:
    return state.model_copy(update={
        'problem_id': '',
        'problem_kind': '',
        'word_problem_schema': {},
        'main_problem': '',
        'active_problem': practice_question.question,
        'full_problem': '',
        'ordered_steps': [],
        'current_step_index': 0,
        'current_step_id': '',
        'completed_steps': [],
        'current_expression': '',
        'remaining_steps': [],
        'completed_step_results': [],
        'step_results': {},
        'attempts_per_step': {},
        'support_per_step': {},
        'current_subject': subject,
        'current_step': practice_question.question,
        'current_question': practice_question.question,
        'expected_answer': practice_question.expected_answer,
        'answer_unit': '',
        'answer_label': '',
        'display_answer': '',
        'student_answer': student_message,
        'correctness_status': '',
        'skill': practice_question.skill,
        'step_number': 1,
        'attempt_count': 0,
        'hint_given': False,
        'answer_revealed': False,
        'next_similar_question': '',
        'tutor_practice_question_id': practice_question.id,
        'tutor_practice_grade': practice_question.grade,
        'tutor_practice_topic': practice_question.topic,
        'tutor_practice_hint_1': practice_question.hint_1,
        'tutor_practice_hint_2': practice_question.hint_2,
        'tutor_practice_explanation': practice_question.worked_explanation,
        'recent_tutor_practice_question_ids': recent_question_ids,
        'helper_branch': TutorHelperBranch(),
        'queued_followup_questions': [],
        'pending_input_kind': '',
        'pending_new_problem': '',
        'return_step_index': 0,
        'return_step_id': '',
        'final_answer': '',
        'problem_status': 'tutor_practice',
        'mode': 'tutor_practice_question',
        'status': 'waiting_for_student',
        'memory_note': f'{source_label}: {practice_question.question}',
    })
