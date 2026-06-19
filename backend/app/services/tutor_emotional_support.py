import re

from pydantic import BaseModel

from ..models import TutoringState
from ..utils.attempt_policy import preserve_attempt_progress
from ..utils.task_lifecycle import pause_active_task


CRISIS_PATTERNS = (
    r'\bwant to die\b',
    r'\bkill myself\b',
    r'\bhurt myself\b',
    r'\bnot safe\b',
    r'\bdon.t want to be alive\b',
    r'\bdo not want to be alive\b',
    r'\bdon.t feel safe\b',
    r'\bdo not feel safe\b',
    r'\bend my life\b',
    r'\bbetter off dead\b',
)


class EmotionalSupportPlan(BaseModel):
    emotion: str = 'upset'
    intensity: str = 'moderate'
    support_count: int = 1
    safety_escalation: bool = False


def build_emotional_support_plan(state: TutoringState, message: str, emotion: str) -> EmotionalSupportPlan:
    text = ' '.join(str(message or '').lower().split())
    safety_escalation = any(re.search(pattern, text) for pattern in CRISIS_PATTERNS)
    count = max(0, int(state.emotional_support_count or 0)) + 1
    intensity = 'urgent' if safety_escalation else ('high' if emotion == 'overwhelmed' or count >= 3 else 'moderate')
    return EmotionalSupportPlan(
        emotion='crisis' if safety_escalation else (emotion or 'upset'),
        intensity=intensity,
        support_count=count,
        safety_escalation=safety_escalation,
    )


def apply_emotional_support(state: TutoringState, message: str, plan: EmotionalSupportPlan) -> TutoringState:
    return_mode = state.emotional_return_mode or state.mode or 'solve'
    return_status = state.emotional_return_status or state.status or 'solving'
    next_state = state.model_copy(update={
        'student_answer': message,
        'correctness_status': '',
        'emotion_label': plan.emotion,
        'emotion_intensity': plan.intensity,
        'emotional_support_count': plan.support_count,
        'emotional_support_mode': 'safety' if plan.safety_escalation else 'choice',
        'emotional_return_mode': return_mode,
        'emotional_return_status': return_status,
        'mode': 'safety_support' if plan.safety_escalation else 'emotional_checkin',
        'status': 'waiting_for_trusted_adult' if plan.safety_escalation else 'waiting_for_student',
    })
    next_state = preserve_attempt_progress(state, next_state)
    if plan.safety_escalation:
        return pause_active_task(_restore_learning_mode(next_state)).model_copy(update={
            'emotion_label': plan.emotion,
            'emotion_intensity': plan.intensity,
            'emotional_support_count': plan.support_count,
            'emotional_support_mode': 'safety',
            'emotional_return_mode': return_mode,
            'emotional_return_status': return_status,
            'mode': 'safety_support',
            'status': 'waiting_for_trusted_adult',
        })
    return next_state


def build_emotional_support_reply(plan: EmotionalSupportPlan, state: TutoringState) -> str:
    if plan.safety_escalation:
        return (
            'I’m really glad you told me. Your safety matters more than this Math problem.\n\n'
            'Please tell a trusted adult who is with you right now—such as a parent, caregiver, teacher, or counselor. '
            'If you might be in immediate danger, ask that adult to contact local emergency services now.\n\n'
            'The lesson is paused. Please go to a trusted adult now.'
        )

    openings = {
        'tired': 'I hear you. You sound tired, and we do not have to push through a big step.',
        'frustrated': 'I hear you. This is frustrating, so let’s make the next move smaller.',
        'overwhelmed': 'I hear you. This feels like too much right now, so we will slow it down.',
        'nervous': 'I hear you. It is okay to feel nervous; you do not need to solve everything at once.',
        'sad': 'I hear you. We can be gentle with this and take the pressure off.',
        'upset': 'I hear you. We can slow down and choose what feels manageable.',
        'discouraged': 'I hear you. Struggling with one problem does not mean you are bad at Math.',
    }
    opening = openings.get(plan.emotion, openings['upset'])
    saved = '\n\nYour Math problem is saved, including your exact step.' if _has_learning_task(state) else ''
    if plan.intensity == 'high':
        return f'{opening}{saved}\n\nWould you like to **take a break** or try **one tiny step**?'
    return f'{opening}{saved}\n\nChoose: **take a break**, **one tiny step**, or **explain it differently**.'


def detect_emotional_support_choice(message: str, state: TutoringState) -> str:
    if state.emotional_support_mode != 'choice' and state.mode != 'emotional_checkin':
        return ''
    text = ' '.join(str(message or '').lower().split())
    if re.search(r'\b(take a break|break|pause|stop for now)\b', text):
        return 'break'
    if re.search(r'\b(one (?:tiny|small) step|tiny step|small step|keep going|continue|try)\b', text):
        return 'tiny_step'
    if re.search(r'\b(explain (?:it )?(?:differently|again)|different way|another way)\b', text):
        return 'different_explanation'
    return ''


def resolve_emotional_support_choice(state: TutoringState, choice: str) -> TutoringState:
    restored = _restore_learning_mode(state).model_copy(update={
        'emotional_support_mode': '',
        'student_answer': '',
        'correctness_status': '',
    })
    restored = preserve_attempt_progress(state, restored)
    if choice == 'break':
        return pause_active_task(restored).model_copy(update={'mode': 'paused', 'status': 'paused'})
    return restored


def build_emotional_choice_reply(state: TutoringState, choice: str) -> str:
    if choice == 'break':
        return 'Of course. Your Math problem and exact step are saved. Come back when you are ready.'
    question = (state.current_question or state.current_step or '').strip()
    if choice == 'different_explanation':
        if question:
            return f'Let’s look at it a different way and focus on only this part:\n\n**Current step:** {question}'
        return 'Let’s try a different explanation with one simple example.'
    if question:
        return f'Okay—just one tiny step. No need to finish the whole problem yet.\n\n**Current step:** {question}'
    return 'Okay—just one tiny step. Tell me the first number you notice in the problem.'


def build_safety_followup_reply() -> str:
    return (
        'The lesson is still paused because your safety comes first. '
        'Please stay with a trusted adult such as a parent, caregiver, teacher, or counselor. '
        'If you might be in immediate danger, ask that adult to contact local emergency services now.'
    )


def _restore_learning_mode(state: TutoringState) -> TutoringState:
    mode = state.emotional_return_mode or ('practice' if state.current_question or state.current_step else 'solve')
    status = state.emotional_return_status or ('waiting_for_student' if state.current_question or state.current_step else 'solving')
    return state.model_copy(update={'mode': mode, 'status': status})


def _has_learning_task(state: TutoringState) -> bool:
    return bool(state.active_task_id or state.main_problem or state.active_problem or state.current_question or state.current_step)
