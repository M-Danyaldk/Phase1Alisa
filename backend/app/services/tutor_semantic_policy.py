from pydantic import BaseModel

from ..models import TutoringState
from ..schemas.tutor_interpretation import TutorInputInterpretation
from .tutor_question_type_router import infer_active_question_type
from ..utils.task_lifecycle import can_resume_paused_task


class TutorSemanticPolicyDecision(BaseModel):
    label: str = 'unknown'
    confidence: str = 'low'
    reason: str = ''
    answer: str = ''
    normalized_expression: str = ''
    question_type: str = ''
    requested_action: str = ''
    refers_to_task: str = ''
    needs_clarification: bool = False
    clarification_question: str = ''
    allowed: bool = True


class TutorSemanticPolicy:
    """Deterministic gate between typed LLM interpretation and tutor routing."""

    STATE_CHANGING_LABELS = {'answer_current_step', 'new_problem', 'switch_request', 'topic_switch'}

    def resolve(self, interpretation: TutorInputInterpretation, state: TutoringState) -> TutorSemanticPolicyDecision:
        label = self._mapped_label(interpretation)
        active_question_type = infer_active_question_type(state)
        decision = TutorSemanticPolicyDecision(
            label=label,
            confidence=interpretation.confidence,
            reason=interpretation.interpretation_note,
            answer=interpretation.answer or '',
            normalized_expression=interpretation.normalized_expression or '',
            question_type=interpretation.question_type or (active_question_type if active_question_type != 'unknown' else ''),
            requested_action=interpretation.requested_action,
            refers_to_task=interpretation.refers_to_task,
            needs_clarification=interpretation.needs_clarification,
            clarification_question=interpretation.clarification_question or '',
        )
        if interpretation.confidence == 'low':
            return self._clarify(decision, interpretation)

        if label in self.STATE_CHANGING_LABELS and interpretation.confidence != 'high':
            return self._clarify(decision, interpretation)

        route_mismatch = self._route_mismatch(interpretation, active_question_type)
        if route_mismatch:
            return self._clarify(decision, interpretation, route_mismatch)

        if interpretation.intent == 'answer_current_step':
            if not self._has_current_step(state):
                return self._clarify(decision, interpretation, 'There is no active step to check yet.')
            if interpretation.refers_to_task not in {'active_task', 'unknown'}:
                return self._clarify(decision, interpretation, 'The answer does not clearly refer to the active task.')
            return decision

        if interpretation.intent == 'new_problem':
            if self._has_active_unfinished_task(state):
                return self._clarify(
                    decision,
                    interpretation,
                    'A different task is already active, so switching needs confirmation.',
                    'Do you want to pause the current problem and work on the new one first?',
                )
            return decision

        if interpretation.intent in {'switch_problem', 'confirm_switch'}:
            if not (interpretation.normalized_expression or interpretation.problem):
                return self._clarify(decision, interpretation, 'Switch request did not include a verified new task.')
            if interpretation.refers_to_task not in {'new_task', 'unknown'}:
                return self._clarify(decision, interpretation, 'Switch request does not clearly point to a new task.')
            return decision

        if interpretation.intent == 'resume':
            if not can_resume_paused_task(state):
                return self._clarify(
                    decision,
                    interpretation,
                    'There is no paused task available to resume.',
                    'There is no saved problem to resume. What would you like to work on now?',
                )
            return decision

        if interpretation.intent == 'continue_current':
            if not self._has_active_unfinished_task(state):
                return self._clarify(
                    decision,
                    interpretation,
                    'There is no active task to continue.',
                    'What would you like to continue with?',
                )
            return decision

        if interpretation.intent in {'continuation_yes', 'continuation_no'}:
            if infer_active_question_type(state) != 'continuation_choice':
                return self._clarify(
                    decision,
                    interpretation,
                    'Continuation choice was interpreted, but the tutor is not waiting on a continuation prompt.',
                    'Do you want to continue the current problem, or start something different?',
                )
            if interpretation.question_type and interpretation.question_type != 'continuation_choice':
                return self._clarify(decision, interpretation, 'Continuation choice did not match the active prompt type.')
            return decision

        if interpretation.intent in {'request_hint', 'stronger_hint_request', 'request_explanation', 'request_example', 'related_question', 'clarify_prompt', 'side_question'}:
            if not self._has_active_unfinished_task(state):
                return self._clarify(
                    decision,
                    interpretation,
                    'There is no active task for this help request.',
                    'What problem would you like help with?',
                )
            return decision

        return decision

    def _mapped_label(self, interpretation: TutorInputInterpretation) -> str:
        label_map = {
            'greeting': 'greeting',
            'acknowledge': 'acknowledge',
            'answer_current_step': 'answer_current_step',
            'continuation_yes': 'continuation_yes',
            'continuation_no': 'continuation_no',
            'new_problem': 'new_problem',
            'related_question': 'related_question',
            'side_question': 'related_question',
            'request_hint': 'help_request',
            'stronger_hint_request': 'help_request',
            'request_explanation': 'related_question',
            'request_example': 'related_question',
            'clarify_prompt': 'clarification_about_context',
            'continue_current': 'continue_current',
            'switch_problem': 'switch_request',
            'confirm_switch': 'switch_request',
            'reject_switch': 'clarification_about_context',
            'topic_switch': 'topic_switch',
            'subject_switch': 'switch_request',
            'pause': 'pause',
            'resume': 'resume',
            'emotion': 'emotion',
            'meta_feedback': 'meta_feedback',
            'off_subject': 'off_subject',
            'unclear': 'clarification_about_context',
        }
        return label_map.get(interpretation.intent, 'unknown')

    def _clarify(
        self,
        decision: TutorSemanticPolicyDecision,
        interpretation: TutorInputInterpretation,
        reason: str = '',
        question: str = '',
    ) -> TutorSemanticPolicyDecision:
        return decision.model_copy(update={
            'label': 'clarification_about_context',
            'needs_clarification': True,
            'clarification_question': (
                question
                or interpretation.clarification_question
                or 'Do you want to answer the current step, or work on a different problem?'
            ),
            'allowed': False,
            'reason': reason or decision.reason,
        })

    def _route_mismatch(self, interpretation: TutorInputInterpretation, active_question_type: str) -> str:
        interpreted = interpretation.question_type or ''
        if not interpreted or interpreted == 'unknown' or active_question_type == 'unknown':
            return ''
        if interpreted == active_question_type:
            return ''
        compatible_routes = {
            ('arithmetic_single_step', 'arithmetic_multi_step'),
            ('arithmetic_multi_step', 'arithmetic_single_step'),
            ('conceptual_math', 'fraction_comparison'),
            ('conceptual_math', 'equivalent_fraction'),
            ('fraction_comparison', 'conceptual_math'),
            ('equivalent_fraction', 'conceptual_math'),
        }
        if (interpreted, active_question_type) in compatible_routes:
            return ''
        return f'Interpreted route {interpreted} did not match the active route {active_question_type}.'

    def _has_current_step(self, state: TutoringState) -> bool:
        return bool((state.current_question or state.current_step).strip() and state.problem_status not in {'finished', 'idle'})

    def _has_active_unfinished_task(self, state: TutoringState) -> bool:
        return bool(
            state.problem_status not in {'finished', 'idle'}
            and (
                state.active_task_id
                or state.active_problem.strip()
                or state.main_problem.strip()
                or state.current_question.strip()
                or state.current_step.strip()
            )
        )
