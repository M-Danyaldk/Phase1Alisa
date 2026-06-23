import re
from difflib import SequenceMatcher

from pydantic import BaseModel

from ..models import ChatHistoryItem, TutoringState
from ..tutoring_logic import (
    _has_unfinished_main_problem,
    _looks_like_answer_to_current_math_step,
    _normalized,
    detect_confused_intent,
    detect_context_clarification_intent,
    detect_definition_intent,
    detect_explicit_subject_switch,
    detect_homework_or_skip_intent,
    detect_math_expression,
    detect_switch_task_intent,
    detect_tutor_concern_intent,
)
from ..assessment_validation import normalize_word_numbers_in_text
from .tutor_semantic_interpreter import TutorSemanticInterpreter
from .tutor_question_type_router import infer_active_question_type
from .tutor_semantic_policy import TutorSemanticPolicy

INTENT_LABELS = {
    'greeting',
    'acknowledge',
    'continue_current',
    'answer_current_step',
    'continuation_yes',
    'continuation_no',
    'related_question',
    'new_problem',
    'side_question',
    'switch_request',
    'topic_switch',
    'help_request',
    'stronger_hint_request',
    'clarify_prompt',
    'emotion',
    'pause',
    'resume',
    'meta_feedback',
    'clarification_about_context',
    'off_subject',
    'unknown',
}

NON_ANSWER_INTENTS = {
    'greeting',
    'acknowledge',
    'continue_current',
    'related_question',
    'new_problem',
    'switch_request',
    'topic_switch',
    'help_request',
    'emotion',
    'pause',
    'resume',
    'meta_feedback',
    'clarification_about_context',
    'off_subject',
}

MATH_TOPIC_ALIASES = {
    'fraction': ('fraction', 'fractions', 'numerator', 'denominator', 'equivalent fraction'),
    'lcm': ('lcm', 'least common multiple'),
    'decimal': ('decimal', 'decimals'),
    'multiplication': ('multiplication', 'multiply', 'times tables', 'times table'),
    'division': ('division', 'divide'),
    'addition': ('addition', 'add'),
    'subtraction': ('subtraction', 'subtract'),
    'geometry': ('geometry', 'shape', 'shapes'),
    'area': ('area',),
    'perimeter': ('perimeter',),
    'word_problem': ('word problem', 'word problems'),
    'ratio': ('ratio', 'ratios'),
    'percent': ('percent', 'percentage', 'percents'),
    'measurement': ('measurement', 'measurements'),
    'time': ('time', 'elapsed time'),
    'money': ('money',),
    'factor': ('factor', 'factors', 'multiple', 'multiples'),
    'place_value': ('place value',),
    'negative_number': ('negative number', 'negative numbers'),
    'expression': ('expression', 'expressions', 'equation', 'equations'),
    'data': ('data', 'graph', 'graphs'),
}

MATH_TOPIC_MISSPELLINGS = {
    'fraction': ('frction', 'fracton', 'frations', 'fracion', 'fraccion', 'fracshun', 'fractionn', 'fractoin', 'fratcion'),
    'lcm': ('least commen multiple', 'least common multple', 'least comun multiple'),
    'decimal': ('decimel', 'decimals'),
    'multiplication': ('multipliction', 'multiplicaton', 'multiplcation'),
    'division': ('divison', 'devision'),
    'addition': ('additon', 'adition'),
    'subtraction': ('substraction', 'subtracion', 'subtrction'),
    'geometry': ('geomtry', 'geometery'),
    'perimeter': ('perimiter', 'peremeter'),
}

EMOTION_ALIASES = {
    'crisis': ('i want to die', 'kill myself', 'hurt myself', 'i want to hurt myself', 'i might hurt myself', "i don't want to be alive", 'i do not want to be alive', 'i am not safe'),
    'tired': ('i am tired', "i'm tired", 'im tired', 'feeling tired', 'too tired'),
    'frustrated': ('i am frustrated', "i'm frustrated", 'im frustrated', 'this is frustrating'),
    'upset': ('i am upset', "i'm upset", 'im upset'),
    'sad': ('i am sad', "i'm sad", 'im sad'),
    'nervous': ('i am nervous', "i'm nervous", 'im nervous', 'i am worried', "i'm worried"),
    'overwhelmed': ('i am overwhelmed', "i'm overwhelmed", 'im overwhelmed', 'this is too much'),
    'discouraged': ("i can't do this", 'i cannot do this', "i'm stupid", 'i am stupid', 'i hate math', 'i am bad at math', "i'm bad at math", 'i give up'),
}


class IntentClassificationResult(BaseModel):
    label: str = 'unknown'
    confidence: str = 'low'
    reason: str = ''
    emotion: str = ''
    question_type: str = ''
    requested_topic: str = ''
    answer: str = ''
    normalized_expression: str = ''
    requested_action: str = ''
    refers_to_task: str = ''
    needs_clarification: bool = False
    clarification_question: str = ''
    interpretation_source: str = 'deterministic'

    @property
    def counts_as_answer(self) -> bool:
        return self.label == 'answer_current_step'


class TutorIntentClassifier:
    def __init__(
        self,
        semantic_interpreter: TutorSemanticInterpreter | None = None,
        semantic_policy: TutorSemanticPolicy | None = None,
    ) -> None:
        self.semantic_interpreter = semantic_interpreter or TutorSemanticInterpreter()
        self.semantic_policy = semantic_policy or TutorSemanticPolicy()

    def classify_deterministically(
        self,
        subject: str,
        message: str,
        history: list[ChatHistoryItem],
        state: TutoringState,
    ) -> IntentClassificationResult:
        text = _normalized(message)
        question_type = infer_active_question_type(state)
        if not text:
            return IntentClassificationResult()

        if question_type == 'continuation_choice':
            if self._is_continuation_yes(text):
                return self._result(
                    label='continuation_yes',
                    confidence='high',
                    reason='Student accepted the continuation-choice prompt.',
                    question_type=question_type,
                    requested_action='continue',
                    refers_to_task='active_task',
                )
            if self._is_continuation_no(text):
                return self._result(
                    label='continuation_no',
                    confidence='high',
                    reason='Student declined the continuation-choice prompt.',
                    question_type=question_type,
                    requested_action='continue',
                    refers_to_task='active_task',
                )

        if self._is_greeting(text):
            return self._result(
                label='greeting',
                confidence='high',
                reason='Student greeted the tutor rather than answering a learning question.',
                question_type=question_type,
            )

        if self._is_acknowledgement(text):
            return self._result(
                label='acknowledge',
                confidence='high',
                reason='Student acknowledged the tutor without submitting an answer.',
                question_type=question_type,
            )

        emotion = self._detected_emotion(text)
        if emotion:
            return self._result(
                label='emotion',
                confidence='high',
                reason='Student expressed an emotional state rather than submitting an answer.',
                emotion=emotion,
                question_type=question_type,
            )

        if self._is_pause_request(text):
            return self._result(
                label='pause',
                confidence='high',
                reason='Student asked to pause or take a break.',
                question_type=question_type,
                requested_action='pause',
            )

        if self._is_continue_request(text) and not self._has_paused_task(state):
            return self._result(
                label='continue_current',
                confidence='high',
                reason='Student asked to continue the current active task.',
                question_type=question_type,
                requested_action='continue',
                refers_to_task='active_task',
            )

        if self._is_resume_request(text):
            return self._result(
                label='resume',
                confidence='high',
                reason='Student asked to resume a saved task.',
                question_type=question_type,
                requested_action='resume',
                refers_to_task='paused_task',
            )

        requested_topic = self._requested_math_topic(subject, text)
        if requested_topic:
            return self._result(
                label='topic_switch',
                confidence='high',
                reason='Student clearly requested a different Math topic.',
                requested_topic=requested_topic,
                question_type=question_type,
                requested_action='switch',
                refers_to_task='new_task',
            )

        if detect_explicit_subject_switch(message) or detect_switch_task_intent(message):
            return self._result(
                label='switch_request',
                confidence='high',
                reason='Student clearly asked to switch the current task.',
                question_type=question_type,
                requested_action='switch',
                refers_to_task='new_task',
            )

        if detect_tutor_concern_intent(message) or re.search(
            r'\b(you already|wrong question|that was wrong|you changed|you forgot|not what i asked)\b',
            text,
        ):
            return self._result(
                label='meta_feedback',
                confidence='high',
                reason='Student is commenting on the tutor or the conversation flow.',
                question_type=question_type,
            )

        if detect_context_clarification_intent(message):
            return self._result(
                label='clarification_about_context',
                confidence='high',
                reason='Student is clarifying which task the conversation is about.',
                question_type=question_type,
                requested_action='clarify',
            )

        if detect_homework_or_skip_intent(message):
            return self._result(
                label='help_request',
                confidence='high',
                reason='Student requested homework help or asked to skip the current check.',
                question_type=question_type,
                requested_action='give_hint',
                refers_to_task='active_task',
            )

        if detect_definition_intent(message):
            return self._result(
                label='related_question',
                confidence='high',
                reason='Student asked for a definition or explanation.',
                question_type=question_type,
                requested_action='explain',
                refers_to_task='active_task',
            )

        if self._is_stronger_hint_request(text):
            return self._result(
                label='stronger_hint_request',
                confidence='high',
                reason='Student explicitly asked for another or stronger hint.',
                question_type=question_type,
                requested_action='give_hint',
                refers_to_task='active_task',
            )

        if self._is_help_request(text):
            return self._result(
                label='help_request',
                confidence='high',
                reason='Student asked for help rather than submitting an answer.',
                question_type=question_type,
                requested_action='give_hint',
                refers_to_task='active_task',
            )

        if self._looks_like_related_question(text, state):
            return self._result(
                label='related_question',
                confidence='high',
                reason='Student asked why or how the current Math step works.',
                question_type=question_type,
                requested_action='explain',
                refers_to_task='active_task',
            )

        if self._looks_like_word_problem(text):
            return self._result(
                label='new_problem',
                confidence='high',
                reason='Student supplied a new text-based Math problem.',
                question_type=question_type,
                requested_action='solve',
                refers_to_task='new_task',
            )

        if _has_unfinished_main_problem(state) and _looks_like_answer_to_current_math_step(
            message,
            state.current_question or state.current_step,
        ):
            return self._result(
                label='answer_current_step',
                confidence='high',
                reason='Student supplied a likely answer to the active step.',
                question_type=question_type,
                requested_action='check_answer',
                refers_to_task='active_task',
                answer=message.strip(),
            )

        return IntentClassificationResult()

    def should_use_fallback(
        self,
        subject: str,
        message: str,
        history: list[ChatHistoryItem],
        state: TutoringState,
    ) -> bool:
        text = _normalized(message)
        active_question_type = infer_active_question_type(state)
        if not text:
            return False
        if not self._has_semantic_context(state, active_question_type):
            return False
        if detect_explicit_subject_switch(message):
            return False
        if detect_switch_task_intent(message):
            return False
        if detect_context_clarification_intent(message):
            return False
        if detect_tutor_concern_intent(message):
            return False
        if detect_homework_or_skip_intent(message):
            return False
        if detect_definition_intent(message):
            return False
        if _looks_like_answer_to_current_math_step(message, state.current_question or state.current_step):
            return False

        ambiguity_markers = (
            'i think',
            'maybe',
            'i mean',
            'no i mean',
            'or',
            'instead',
            'first',
            'before',
            'after',
            'came',
            'became',
            'how did',
            'what do you mean',
            'leave that',
            'come back',
            'for now',
            'this one',
        )
        mixed_math_and_text = detect_math_expression(message) and bool(re.search(r'[a-zA-Z]', message))
        ambiguous_text = any(marker in text for marker in ambiguity_markers)
        confused = detect_confused_intent(message) and len(text) > 12
        flexible_answer = bool(re.search(
            r'\b(final answer|my result|the result|should be|comes? to|equals?|i got|i reckon|probably)\b',
            text,
        ))
        normalized_word_answer = normalize_word_numbers_in_text(text).strip()
        word_number_answer = bool(
            state.current_question.strip()
            and re.fullmatch(r'-?\d+(?:\.\d+)?(?:/\d+)?', normalized_word_answer)
            and not detect_math_expression(message)
        )

        if mixed_math_and_text:
            return True
        if ambiguous_text:
            return True
        if confused:
            return True
        if flexible_answer:
            return True
        if word_number_answer:
            return True
        return False

    def _result(self, **updates) -> IntentClassificationResult:
        return IntentClassificationResult(**updates)

    async def classify_if_needed(
        self,
        subject: str,
        message: str,
        history: list[ChatHistoryItem],
        state: TutoringState,
    ) -> IntentClassificationResult:
        deterministic = self.classify_deterministically(subject, message, history, state)
        if deterministic.label != 'unknown':
            return deterministic
        if not self.should_use_fallback(subject, message, history, state):
            return IntentClassificationResult()
        result = await self._classify_with_llm(subject, message, history, state)
        if result.label not in INTENT_LABELS:
            return IntentClassificationResult()
        if result.confidence not in {'high', 'medium', 'low'}:
            result.confidence = 'low'
        if result.confidence == 'low':
            return result
        return result

    def _detected_emotion(self, text: str) -> str:
        if re.search(
            r"\b(want to die|kill myself|hurt myself|end my life|don['’]?t (?:want to be alive|feel safe)|do not (?:want to be alive|feel safe)|not safe|better off dead)\b",
            text,
        ):
            return 'crisis'
        for emotion, phrases in EMOTION_ALIASES.items():
            if any(re.search(rf'(?<![a-z]){re.escape(phrase)}(?![a-z])', text) for phrase in phrases):
                return emotion
        return ''

    def _is_pause_request(self, text: str) -> bool:
        return bool(re.search(r'\b(pause|take a break|need a break|stop for now|come back later)\b', text))

    def _is_greeting(self, text: str) -> bool:
        return bool(re.fullmatch(r'(?:hi|hello|hey|hiya|good morning|good afternoon|good evening)[!. ]*', text))

    def _is_acknowledgement(self, text: str) -> bool:
        return bool(re.fullmatch(
            r'(?:ok|okay|alright|all right|got it|i understand|understood|that makes sense|thanks|thank you)[!. ]*',
            text,
        ))

    def _is_continue_request(self, text: str) -> bool:
        if text in {'one tiny step', 'a tiny step', 'tiny step', 'smaller step'}:
            return True
        return bool(re.fullmatch(
            r'(?:ok(?:ay)?\s+)?(?:continue|keep going|go on|proceed|move on|next|next step)(?:\s+(?:with|to|on)\s+(?:this|the)(?:\s+problem)?)?[!. ]*',
            text,
        ))

    def _has_paused_task(self, state: TutoringState) -> bool:
        has_active_context = bool(
            state.current_question.strip()
            or state.current_step.strip()
            or state.active_problem.strip()
            or state.main_problem.strip()
        )
        return bool(
            state.mode == 'paused'
            or state.status == 'paused'
            or (
                not has_active_context
                and (
                    state.paused_main_problem.strip()
                    or any(record.status == 'paused' for record in state.task_records)
                )
            )
        )

    def _is_resume_request(self, text: str) -> bool:
        return bool(re.search(r"\b(i am back|i'm back|im back|continue|keep going|resume)\b", text))

    def _requested_math_topic(self, subject: str, text: str) -> str:
        if subject != 'Math':
            return ''
        request_shape = bool(re.search(
            r'\b(i want|i need|i would like|i\'d like|teach me|help me (?:learn|with)|can we|could we|let\'s|lets|move to|go to|practice|learn)\b',
            text,
        ))
        topic_like_only = self._is_short_topic_like_request(text)
        if not request_shape and not topic_like_only:
            return ''
        for topic, aliases in MATH_TOPIC_MISSPELLINGS.items():
            if any(re.search(rf'\b{re.escape(alias)}s?\b', text) for alias in aliases):
                return topic
        for topic, aliases in MATH_TOPIC_ALIASES.items():
            if any(re.search(rf'\b{re.escape(alias)}s?\b', text) for alias in aliases):
                return topic
        fuzzy_topic = self._fuzzy_math_topic(text)
        if fuzzy_topic:
            return fuzzy_topic
        return ''

    def _is_short_topic_like_request(self, text: str) -> bool:
        cleaned = re.sub(r'[^a-z0-9/ ]+', ' ', text)
        words = [word for word in cleaned.split() if word]
        if not words or len(words) > 5:
            return False
        help_context_words = {
            'why',
            'how',
            'what',
            'where',
            'when',
            'this',
            'here',
            'mean',
            'means',
            'understand',
            'confused',
            'explain',
        }
        if any(word in help_context_words for word in words):
            return False
        request_words = {
            'teach',
            'learn',
            'practice',
            'start',
            'topic',
            'question',
            'questions',
            'example',
            'examples',
            'me',
            'with',
            'do',
            'want',
            'need',
            'can',
            'we',
            'please',
            'a',
            'an',
        }
        topic_words = [word for word in words if word not in request_words]
        return bool(topic_words) and len(topic_words) <= 3

    def _fuzzy_math_topic(self, text: str) -> str:
        cleaned = re.sub(r'[^a-z0-9/ ]+', ' ', text)
        words = [word for word in cleaned.split() if word]
        request_words = {
            'teach',
            'learn',
            'practice',
            'start',
            'topic',
            'question',
            'questions',
            'example',
            'examples',
            'me',
            'with',
            'do',
            'want',
            'need',
            'can',
            'we',
            'please',
            'a',
            'an',
            'to',
            'the',
        }
        candidates = [word for word in words if word not in request_words and len(word) >= 3]
        if not candidates:
            return ''
        phrase = ' '.join(candidates)
        alias_pairs = [
            (topic, alias)
            for topic, aliases in MATH_TOPIC_ALIASES.items()
            for alias in aliases
            if len(alias) >= 4
        ]
        best_topic = ''
        best_score = 0.0
        for candidate in [*candidates, phrase]:
            for topic, alias in alias_pairs:
                if ' ' in alias and len(candidates) == 1:
                    continue
                score = SequenceMatcher(None, candidate, alias).ratio()
                threshold = 0.84 if len(candidate) <= 7 else 0.78
                if score >= threshold and score > best_score:
                    best_topic = topic
                    best_score = score
        return best_topic

    def _is_help_request(self, text: str) -> bool:
        return bool(re.search(
            r'^(hint|help|help me|show me|explain(?: it)?|give me (?:a |another )?hint|make it easier|i do not know|i don\'t know|i dont know|i (?:still )?do not understand|i (?:still )?don\'t understand|i (?:still )?dont understand|i am stuck|i\'m stuck|im stuck)\b',
            text,
        ))

    def _is_stronger_hint_request(self, text: str) -> bool:
        return bool(re.search(
            r'^(?:another|one more|stronger|better|bigger)\s+hint\b|^(?:give me|show me)\s+(?:another|one more|a stronger|more)\s+hint\b|^more help\b',
            text,
        ))

    def _is_continuation_yes(self, text: str) -> bool:
        return bool(re.fullmatch(
            r'(?:yes|yeah|yep|sure|okay|ok|please do|continue|go ahead|another one|one more|more|yes please|sure please|ok yes|okay yes|keep going)[!. ]*',
            text,
        ))

    def _is_continuation_no(self, text: str) -> bool:
        return bool(re.fullmatch(
            r'(?:no|no thanks|not now|stop|i am done|i\'m done|im done|maybe later|not today)[!. ]*',
            text,
        ))

    def _looks_like_related_question(self, text: str, state: TutoringState) -> bool:
        if not _has_unfinished_main_problem(state):
            return False
        return bool(re.match(r'^(why|how|what do you mean|where did|how did|why do|why did)\b', text))

    def _has_semantic_context(self, state: TutoringState, active_question_type: str) -> bool:
        if active_question_type in {'continuation_choice', 'side_question', 'emotion_support'}:
            return True
        return _has_unfinished_main_problem(state)

    def _looks_like_word_problem(self, text: str) -> bool:
        numbers = re.findall(r'\d+(?:\.\d+)?', text)
        if len(numbers) < 2:
            return False
        word_problem_markers = (
            'there are',
            'there were',
            'each ',
            'altogether',
            'in total',
            'how many',
            'how much',
            'left',
            'remaining',
            'capacity',
            'rows',
            'boxes',
            'students',
            'cookies',
            'balls',
            'seats',
        )
        return len(text) >= 35 and any(marker in text for marker in word_problem_markers)

    async def _classify_with_llm(
        self,
        subject: str,
        message: str,
        history: list[ChatHistoryItem],
        state: TutoringState,
    ) -> IntentClassificationResult:
        interpretation = await self.semantic_interpreter.interpret(subject, message, history, state)
        decision = self.semantic_policy.resolve(interpretation, state)
        return IntentClassificationResult(
            label=decision.label,
            confidence=decision.confidence,
            reason=decision.reason,
            emotion=interpretation.emotion or '',
            question_type=decision.question_type,
            answer=decision.answer,
            normalized_expression=decision.normalized_expression,
            requested_action=decision.requested_action,
            refers_to_task=decision.refers_to_task,
            needs_clarification=decision.needs_clarification,
            clarification_question=decision.clarification_question,
            interpretation_source='llm_schema',
        )
