from __future__ import annotations

import uuid

from ..models import TutorTaskRecord, TutoringState


LIFECYCLE_FIELDS = {'active_task_id', 'task_records'}


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
    if not active:
        return state
    if state.problem_status == 'finished' or state.status == 'finished':
        return complete_active_task(state)
    return sync_active_task(state)


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
            records.append(record.model_copy(update={'status': 'paused'}))
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
    return state.model_dump(exclude=LIFECYCLE_FIELDS)


def _restore_snapshot(state: TutoringState, snapshot: dict, overrides: dict) -> TutoringState:
    values = state.model_dump()
    values.update(snapshot)
    values.update(overrides)
    return TutoringState.model_validate(values)


def _state_problem(state: TutoringState) -> str:
    if state.problem_kind == 'word_problem' and state.full_problem:
        return str(state.full_problem).strip()
    return str(state.main_problem or state.active_problem or state.current_question or '').strip()


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
