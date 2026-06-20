from __future__ import annotations

import uuid

from ..models import TutorTaskRecord, TutoringState

# Only task-scoped values belong in a resumable snapshot. Session-wide values such
# as recent-question rotation, emotional counters, and response diagnostics must
# not roll back when an older task is resumed.
TASK_SNAPSHOT_FIELDS = {
    'problem_id',
    'problem_kind',
    'word_problem_schema',
    'main_problem',
    'active_problem',
    'current_subject',
    'full_problem',
    'ordered_steps',
    'current_step_index',
    'current_step_id',
    'completed_steps',
    'current_expression',
    'remaining_steps',
    'completed_step_results',
    'step_results',
    'attempts_per_step',
    'support_per_step',
    'current_step',
    'current_question',
    'expected_answer',
    'answer_unit',
    'answer_label',
    'display_answer',
    'student_answer',
    'correctness_status',
    'skill',
    'step_number',
    'attempt_count',
    'hint_given',
    'answer_revealed',
    'next_similar_question',
    'tutor_practice_question_id',
    'tutor_practice_grade',
    'tutor_practice_topic',
    'tutor_practice_hint_1',
    'tutor_practice_hint_2',
    'tutor_practice_explanation',
    'helper_branch',
    'queued_followup_questions',
    'pending_input_kind',
    'pending_new_problem',
    'return_step_index',
    'return_step_id',
    'final_answer',
    'problem_status',
    'mode',
    'status',
    'memory_note',
}


def ensure_task_lifecycle(state: TutoringState) -> TutoringState:
    if state.task_records:
        return _normalize_task_records(state)

    problem = _state_problem(state)
    if not problem:
        if state.problem_status in {'finished', 'idle'} and state.paused_main_problem:
            return _clear_legacy_paused_fields(state)
        return state

    terminal = state.problem_status == 'finished' or state.status == 'finished'
    record = TutorTaskRecord(
        task_id=state.problem_id or _new_task_id(),
        subject=state.current_subject or 'Math',
        problem_text=problem,
        source='legacy',
        status='completed' if terminal else 'active',
        final_answer=state.final_answer if terminal else '',
        snapshot=_snapshot(state),
    )
    return state.model_copy(update={
        'active_task_id': '' if terminal else record.task_id,
        'task_records': [record],
        **(_legacy_paused_clear_update() if terminal else {}),
    })


def start_task(
    state: TutoringState,
    problem_text: str,
    *,
    subject: str = 'Math',
    topic: str = '',
    source: str = 'student',
    previous: str = 'pause',
) -> TutoringState:
    state = ensure_task_lifecycle(state)
    problem = str(problem_text or '').strip()
    if not problem:
        return state

    active = active_task(state)
    if active and _same_problem(active.problem_text, problem):
        return sync_active_task(state)

    transitioned = state
    if active:
        transitioned = pause_active_task(state) if previous == 'pause' else abandon_active_task(state)

    record = TutorTaskRecord(
        task_id=_new_task_id(),
        subject=subject or state.current_subject or 'Math',
        topic=topic,
        problem_text=problem,
        source=source,
        status='active',
        snapshot=_snapshot(transitioned),
    )
    return transitioned.model_copy(update={
        'active_task_id': record.task_id,
        'task_records': _trim_records([*transitioned.task_records, record]),
    })


def transition_to_task(
    previous_state: TutoringState,
    next_state: TutoringState,
    problem_text: str,
    *,
    subject: str = 'Math',
    topic: str = '',
    source: str = 'student',
    previous: str = 'pause',
) -> TutoringState:
    previous_state = ensure_task_lifecycle(previous_state)
    transitioned = pause_active_task(previous_state) if previous == 'pause' else abandon_active_task(previous_state)
    merged = next_state.model_copy(update={
        'active_task_id': transitioned.active_task_id,
        'task_records': transitioned.task_records,
    })
    return start_task(merged, problem_text, subject=subject, topic=topic, source=source, previous='pause')


def sync_active_task(state: TutoringState) -> TutoringState:
    active = active_task(state)
    if not active:
        return state
    records = [
        record.model_copy(update={
            'problem_text': _state_problem(state) or record.problem_text,
            'snapshot': _snapshot(state),
        }) if record.task_id == active.task_id else record
        for record in state.task_records
    ]
    return state.model_copy(update={'task_records': records})


def pause_active_task(state: TutoringState) -> TutoringState:
    return _transition_active(state, 'paused')


def complete_active_task(state: TutoringState) -> TutoringState:
    return _transition_active(state, 'completed')


def abandon_active_task(state: TutoringState) -> TutoringState:
    return _transition_active(state, 'abandoned')


def active_task(state: TutoringState) -> TutorTaskRecord | None:
    if not state.active_task_id:
        return None
    return next((record for record in state.task_records if record.task_id == state.active_task_id and record.status == 'active'), None)


def latest_paused_task(state: TutoringState) -> TutorTaskRecord | None:
    return next((record for record in reversed(state.task_records) if record.status == 'paused'), None)


def can_resume_paused_task(state: TutoringState) -> bool:
    if state.task_records:
        return latest_paused_task(state) is not None
    return bool(state.paused_main_problem.strip() and state.problem_status not in {'finished', 'idle'})


def complete_and_resume_latest(state: TutoringState) -> TutoringState:
    if not state.task_records and state.paused_main_problem.strip():
        return state.model_copy(update={
            'active_problem': state.paused_main_problem.strip(),
            'current_step': state.paused_current_step,
            'current_question': state.paused_current_question or state.paused_current_step,
            'expected_answer': state.paused_expected_answer,
            'completed_steps': list(state.paused_completed_steps),
            'mode': 'resume_paused_problem_notice',
            'status': 'waiting_for_student',
            **_legacy_paused_clear_update(),
        })
    completed = complete_active_task(state)
    paused = latest_paused_task(completed)
    if not paused:
        return _clear_legacy_paused_fields(completed)

    restored_values = {
        'active_task_id': paused.task_id,
        'task_records': [
            record.model_copy(update={'status': 'active'}) if record.task_id == paused.task_id else record
            for record in completed.task_records
        ],
        'mode': 'resume_paused_problem_notice',
        'status': 'waiting_for_student',
        **_legacy_paused_clear_update(),
    }
    return _restore_snapshot(completed, paused.snapshot, restored_values)


def resume_latest_paused_task(state: TutoringState) -> TutoringState:
    state = ensure_task_lifecycle(state)
    paused = latest_paused_task(state)
    if not paused:
        return state
    current = active_task(state)
    current_snapshot = _snapshot(state)
    records = []
    for record in state.task_records:
        if current and record.task_id == current.task_id and record.task_id != paused.task_id:
            records.append(record.model_copy(update={'status': 'paused', 'snapshot': current_snapshot}))
        elif record.task_id == paused.task_id:
            records.append(record.model_copy(update={'status': 'active'}))
        else:
            records.append(record)
    restored_values = {
        'active_task_id': paused.task_id,
        'task_records': records,
        'mode': 'practice' if (paused.snapshot.get('current_question') or paused.snapshot.get('current_step')) else 'solve',
        'status': 'waiting_for_student',
        **_legacy_paused_clear_update(),
    }
    return _restore_snapshot(state, paused.snapshot, restored_values)


def reconcile_task_lifecycle(state: TutoringState) -> TutoringState:
    state = ensure_task_lifecycle(state)
    active = active_task(state)
    if active and (state.problem_status == 'finished' or state.status == 'finished'):
        state = complete_active_task(state)
        active = None

    if active:
        live_problem = _state_problem(state)
        if not live_problem or not _same_problem(live_problem, active.problem_text):
            restored_values = {
                'active_task_id': active.task_id,
                'task_records': state.task_records,
                'current_subject': active.subject or state.current_subject,
            }
            state = _restore_snapshot(state, active.snapshot, restored_values)
            if not _state_problem(state):
                state = state.model_copy(update={'active_problem': active.problem_text})
        return _project_paused_task(sync_active_task(state))

    if state.task_records:
        terminal_answer = state.final_answer
        state = _clear_live_task_state(state)
        if terminal_answer:
            state = state.model_copy(update={'final_answer': terminal_answer})
        return _project_paused_task(state)
    return state


def _transition_active(state: TutoringState, status: str) -> TutoringState:
    state = ensure_task_lifecycle(state)
    active = active_task(state)
    if not active:
        return state
    snapshot = _snapshot(state)
    records = [
        record.model_copy(update={
            'status': status,
            'final_answer': state.final_answer if status == 'completed' else record.final_answer,
            'snapshot': snapshot if status == 'paused' else {},
        }) if record.task_id == active.task_id else record
        for record in state.task_records
    ]
    return state.model_copy(update={
        'active_task_id': '',
        'task_records': _trim_records(records),
        **(_legacy_paused_clear_update() if status in {'completed', 'abandoned'} else {}),
    })


def _normalize_task_records(state: TutoringState) -> TutoringState:
    active_ids = [record.task_id for record in state.task_records if record.status == 'active']
    chosen = state.active_task_id if state.active_task_id in active_ids else (active_ids[-1] if active_ids else '')
    records = []
    for record in state.task_records:
        if record.status == 'active' and record.task_id != chosen:
            records.append(record.model_copy(update={
                'status': 'paused' if record.snapshot else 'abandoned',
            }))
        else:
            records.append(record)
    return state.model_copy(update={'active_task_id': chosen, 'task_records': records})


def _trim_records(records: list[TutorTaskRecord], paused_limit: int = 10, terminal_limit: int = 20) -> list[TutorTaskRecord]:
    active = [record for record in records if record.status == 'active']
    paused = [record for record in records if record.status == 'paused'][-paused_limit:]
    terminal = [record for record in records if record.status in {'completed', 'abandoned'}][-terminal_limit:]
    keep_ids = {record.task_id for record in [*terminal, *paused, *active]}
    return [record for record in records if record.task_id in keep_ids]


def _snapshot(state: TutoringState) -> dict:
    return state.model_dump(include=TASK_SNAPSHOT_FIELDS)


def _restore_snapshot(state: TutoringState, snapshot: dict, overrides: dict) -> TutoringState:
    values = state.model_dump()
    values.update({key: value for key, value in snapshot.items() if key in TASK_SNAPSHOT_FIELDS})
    values.update(overrides)
    return TutoringState.model_validate(values)


def _clear_live_task_state(state: TutoringState) -> TutoringState:
    defaults = TutoringState(current_subject=state.current_subject)
    preserve_support_control = bool(
        state.emotional_support_mode
        or state.mode in {'safety_support', 'emotional_support'}
        or state.status == 'waiting_for_trusted_adult'
    )
    update = {
        field: getattr(defaults, field)
        for field in TASK_SNAPSHOT_FIELDS
        if field != 'current_subject'
    }
    if preserve_support_control:
        update.update({
            'mode': state.mode,
            'status': state.status,
            'problem_status': state.problem_status,
        })
    return state.model_copy(update=update)


def _project_paused_task(state: TutoringState) -> TutoringState:
    """Expose legacy paused fields as a read-only projection of lifecycle records."""
    paused = latest_paused_task(state)
    if not paused:
        return _clear_legacy_paused_fields(state)
    snapshot = paused.snapshot
    paused_problem = str(
        snapshot.get('main_problem')
        or snapshot.get('active_problem')
        or paused.problem_text
        or ''
    ).strip()
    update = {
        'paused_main_problem': paused_problem,
        'paused_current_step': str(snapshot.get('current_step') or ''),
        'paused_current_question': str(snapshot.get('current_question') or snapshot.get('current_step') or ''),
        'paused_expected_answer': str(snapshot.get('expected_answer') or ''),
        'paused_completed_steps': list(snapshot.get('completed_steps') or []),
    }
    if active_task(state) is None and not (
        state.emotional_support_mode
        or state.mode in {'safety_support', 'emotional_support'}
        or state.status == 'waiting_for_trusted_adult'
    ):
        update.update({'mode': 'paused', 'status': 'paused', 'problem_status': 'idle'})
    return state.model_copy(update=update)


def _state_problem(state: TutoringState) -> str:
    if state.problem_kind == 'word_problem' and state.full_problem:
        return str(state.full_problem).strip()
    # active_problem represents the task currently in front of the student. A
    # main_problem may remain populated as compatibility context while a
    # temporary task is active, so it must not override the active task here.
    return str(state.active_problem or state.main_problem or state.current_question or '').strip()


def _same_problem(left: str, right: str) -> bool:
    return ' '.join(str(left or '').lower().split()) == ' '.join(str(right or '').lower().split())


def _new_task_id() -> str:
    return f'task-{uuid.uuid4().hex}'


def _legacy_paused_clear_update() -> dict:
    return {
        'paused_main_problem': '',
        'paused_current_step': '',
        'paused_current_question': '',
        'paused_expected_answer': '',
        'paused_completed_steps': [],
    }


def _clear_legacy_paused_fields(state: TutoringState) -> TutoringState:
    return state.model_copy(update=_legacy_paused_clear_update())
