export type ActionableTutorState = {
  active_task_id?: string;
  active_problem?: string;
  main_problem?: string;
  current_step?: string;
  current_question?: string;
};

export function hasActionableTutorTask(state: ActionableTutorState): boolean {
  return Boolean(
    state.active_task_id
    || state.active_problem
    || state.main_problem
    || state.current_step
    || state.current_question
  );
}
