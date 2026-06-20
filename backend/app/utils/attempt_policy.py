from __future__ import annotations

import hashlib

from ..models import TutoringState


MAX_ATTEMPTS_BEFORE_REVEAL = 3


def attempt_scope_key(state: TutoringState, step_id: str = '') -> str:
    task_key = state.active_task_id or state.problem_id or 'legacy-task'
    step_text = (
        step_id
        or state.current_step_id
        or state.current_question
        or state.current_step
        or state.active_problem
        or 'general-step'
    )
    normalized = ' '.join(str(step_text).lower().split())
    step_key = step_id or state.current_step_id or hashlib.sha1(normalized.encode('utf-8')).hexdigest()[:12]
    return f'{task_key}:{step_key}'


def attempt_count_for(state: TutoringState, step_id: str = '') -> int:
    key = attempt_scope_key(state, step_id)
    if key in state.attempts_per_step:
        return int(state.attempts_per_step[key])
    # Compatibility with states saved before task-scoped attempt keys existed.
    if step_id and step_id in state.attempts_per_step:
        return int(state.attempts_per_step[step_id])
    return int(state.attempt_count or 0)


def register_answer_attempt(state: TutoringState, *, is_answer: bool = True) -> TutoringState:
    if not is_answer:
        return state
    key = attempt_scope_key(state)
    attempts = dict(state.attempts_per_step)
    if key in attempts:
        current = attempts[key]
    elif state.current_step_id and state.current_step_id in attempts:
        current = attempts[state.current_step_id]
    elif not attempts:
        current = state.attempt_count
    else:
        current = 0
    next_count = min(int(current or 0) + 1, MAX_ATTEMPTS_BEFORE_REVEAL)
    attempts[key] = next_count
    if state.current_step_id:
        # Keep the legacy key during rollout; the task-scoped key above is authoritative.
        attempts[state.current_step_id] = next_count
    return state.model_copy(update={
        'attempt_count': next_count,
        'attempts_per_step': attempts,
        'hint_given': next_count in {1, 2},
        'answer_revealed': next_count >= MAX_ATTEMPTS_BEFORE_REVEAL,
    })


def ensure_answer_attempt_registered(previous: TutoringState, current: TutoringState) -> TutoringState:
    previous_count = attempt_count_for(previous)
    current_count = attempt_count_for(current)
    if current_count > previous_count:
        return current
    return register_answer_attempt(current)


def reset_attempt_display(state: TutoringState) -> TutoringState:
    return state.model_copy(update={
        'attempt_count': 0,
        'hint_given': False,
        'answer_revealed': False,
    })


def preserve_attempt_progress(source: TutoringState, target: TutoringState) -> TutoringState:
    return target.model_copy(update={
        'attempt_count': source.attempt_count,
        'attempts_per_step': dict(source.attempts_per_step),
        'support_per_step': {**source.support_per_step, **target.support_per_step},
        'hint_given': source.hint_given,
        'answer_revealed': source.answer_revealed,
    })


def preserve_tutor_practice_context(source: TutoringState, target: TutoringState) -> TutoringState:
    if source.mode != 'tutor_practice_question' or source.problem_status != 'tutor_practice':
        return target
    return target.model_copy(update={
        'active_task_id': source.active_task_id,
        'task_records': list(source.task_records),
        'active_problem': source.active_problem,
        'current_step': source.current_step,
        'current_question': source.current_question,
        'expected_answer': source.expected_answer,
        'correctness_status': '',
        'skill': source.skill,
        'step_number': source.step_number,
        'attempt_count': source.attempt_count,
        'attempts_per_step': dict(source.attempts_per_step),
        'support_per_step': {**source.support_per_step, **target.support_per_step},
        'hint_given': source.hint_given or target.hint_given,
        'answer_revealed': source.answer_revealed,
        'next_similar_question': source.next_similar_question,
        'tutor_practice_question_id': source.tutor_practice_question_id,
        'tutor_practice_grade': source.tutor_practice_grade,
        'tutor_practice_topic': source.tutor_practice_topic,
        'tutor_practice_hint_1': source.tutor_practice_hint_1,
        'tutor_practice_hint_2': source.tutor_practice_hint_2,
        'tutor_practice_explanation': source.tutor_practice_explanation,
        'recent_tutor_practice_question_ids': list(source.recent_tutor_practice_question_ids),
        'problem_status': 'tutor_practice',
        'mode': 'tutor_practice_question',
        'status': 'waiting_for_student',
    })


def attempt_stage(attempt_count: int) -> str:
    if attempt_count <= 0:
        return 'none'
    if attempt_count == 1:
        return 'small_hint'
    if attempt_count == 2:
        return 'strong_hint'
    return 'reveal'


def should_reveal(attempt_count: int) -> bool:
    return attempt_count >= MAX_ATTEMPTS_BEFORE_REVEAL
