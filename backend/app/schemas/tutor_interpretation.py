import re
from fractions import Fraction
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..assessment_validation import normalize_math_text, safe_eval_expression


TutorIntent = Literal[
    'greeting',
    'acknowledge',
    'answer_current_step',
    'continuation_yes',
    'continuation_no',
    'new_problem',
    'related_question',
    'side_question',
    'request_hint',
    'stronger_hint_request',
    'request_explanation',
    'request_example',
    'clarify_prompt',
    'continue_current',
    'switch_problem',
    'confirm_switch',
    'reject_switch',
    'topic_switch',
    'subject_switch',
    'pause',
    'resume',
    'emotion',
    'meta_feedback',
    'off_subject',
    'unclear',
]
InterpretationConfidence = Literal['high', 'medium', 'low']
TaskReference = Literal['active_task', 'new_task', 'paused_task', 'no_task', 'unknown']
RequestedAction = Literal[
    'solve',
    'explain',
    'check_answer',
    'give_hint',
    'give_example',
    'continue',
    'switch',
    'clarify',
    'cancel',
    'pause',
    'resume',
    'none',
]
MathOperation = Literal[
    'addition',
    'subtraction',
    'multiplication',
    'division',
    'comparison',
    'mixed_operations',
    'equivalent_fraction',
    'fraction_addition',
    'fraction_subtraction',
    'fraction_multiplication',
    'fraction_division',
    'decimal_addition',
    'decimal_subtraction',
    'decimal_multiplication',
    'decimal_division',
    'ratio',
    'percent',
    'area',
    'perimeter',
    'volume',
    'measurement_conversion',
    'elapsed_time',
    'money',
    'multi_step',
    'unknown',
]
ProblemKind = Literal['expression', 'word_problem', 'conceptual', 'geometry', 'measurement', 'data', 'unknown']
QuestionType = Literal[
    'arithmetic_single_step',
    'arithmetic_multi_step',
    'fraction_comparison',
    'equivalent_fraction',
    'conceptual_math',
    'word_problem',
    'continuation_choice',
    'side_question',
    'emotion_support',
    'unknown',
]
QuantityRole = Literal[
    'given',
    'unknown',
    'rate',
    'group_count',
    'group_size',
    'part',
    'whole',
    'numerator',
    'denominator',
    'length',
    'width',
    'height',
    'time',
    'price',
    'total',
    'change',
]


class StrictTutorSchema(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, str_strip_whitespace=True)


def _validated_expression(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = normalize_math_text(value).replace('Ã—', '*').replace('Ã·', '/')
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    if not normalized or len(normalized) > 160:
        raise ValueError('Expression must be non-empty and at most 160 characters.')
    if re.search(r'[^0-9+\-*/().\s]', normalized):
        raise ValueError('Expression contains unsupported characters.')
    if safe_eval_expression(normalized) is None:
        raise ValueError('Expression is not deterministically evaluable.')
    return normalized


class TutorQuantity(StrictTutorSchema):
    value: str = Field(min_length=1, max_length=40)
    unit: str = Field(default='', max_length=60)
    label: str = Field(default='', max_length=100)
    role: QuantityRole = 'given'

    @field_validator('value')
    @classmethod
    def validate_numeric_value(cls, value: str) -> str:
        cleaned = value.replace(' ', '')
        try:
            Fraction(cleaned)
        except (ValueError, ZeroDivisionError) as exc:
            raise ValueError('Quantity value must be a normalized number or fraction.') from exc
        return cleaned


class StructuredMathProblem(StrictTutorSchema):
    original_text: str = Field(min_length=1, max_length=2000)
    problem_kind: ProblemKind = 'word_problem'
    quantities: list[TutorQuantity] = Field(default_factory=list, max_length=12)
    operation: MathOperation
    confidence: InterpretationConfidence
    expression: str | None = None
    requested_value: str | None = Field(default=None, max_length=160)
    unit: str | None = Field(default=None, max_length=60)
    sufficient_information: bool
    assumptions: list[str] = Field(default_factory=list, max_length=5)

    @field_validator('expression')
    @classmethod
    def validate_expression(cls, value: str | None) -> str | None:
        return _validated_expression(value)

    @field_validator('assumptions')
    @classmethod
    def validate_assumptions(cls, values: list[str]) -> list[str]:
        if any(not value.strip() or len(value) > 180 for value in values):
            raise ValueError('Assumptions must be short non-empty statements.')
        return values

    @model_validator(mode='after')
    def validate_problem_consistency(self) -> 'StructuredMathProblem':
        if self.sufficient_information:
            if self.operation == 'unknown':
                raise ValueError('A sufficient problem cannot use an unknown operation.')
            if not self.expression:
                raise ValueError('A sufficient problem requires a verified expression candidate.')
            if not self.requested_value:
                raise ValueError('A sufficient problem requires the requested value.')
        elif self.expression is not None:
            raise ValueError('An insufficient problem cannot claim a complete expression.')
        return self


class TutorInputInterpretation(StrictTutorSchema):
    schema_version: Literal['1.0'] = '1.0'
    intent: TutorIntent
    confidence: InterpretationConfidence
    answer: str | None = Field(default=None, max_length=240)
    normalized_expression: str | None = None
    problem: StructuredMathProblem | None = None
    question_type: QuestionType | None = None
    refers_to_task: TaskReference
    requested_action: RequestedAction
    emotion: str | None = Field(default=None, max_length=60)
    needs_clarification: bool = False
    clarification_question: str | None = Field(default=None, max_length=240)
    interpretation_note: str = Field(min_length=1, max_length=240)

    @field_validator('normalized_expression')
    @classmethod
    def validate_normalized_expression(cls, value: str | None) -> str | None:
        return _validated_expression(value)

    @model_validator(mode='after')
    def validate_interpretation_consistency(self) -> 'TutorInputInterpretation':
        if self.intent == 'answer_current_step' and not self.answer:
            raise ValueError('An answer intent requires an extracted answer.')
        if self.intent in {'new_problem', 'switch_problem'} and not (self.normalized_expression or self.problem):
            raise ValueError('A new or switched problem requires an expression or structured problem.')
        if self.intent == 'request_hint' and self.requested_action != 'give_hint':
            raise ValueError('A hint intent must request the give_hint action.')
        if self.intent == 'stronger_hint_request' and self.requested_action != 'give_hint':
            raise ValueError('A stronger hint intent must request the give_hint action.')
        if self.intent == 'request_explanation' and self.requested_action != 'explain':
            raise ValueError('An explanation intent must request the explain action.')
        if self.intent == 'request_example' and self.requested_action != 'give_example':
            raise ValueError('An example intent must request the give_example action.')
        if self.intent == 'clarify_prompt' and self.requested_action != 'clarify':
            raise ValueError('A clarify-prompt intent must request clarification help.')
        if self.intent in {'continuation_yes', 'continuation_no'} and self.requested_action != 'continue':
            raise ValueError('Continuation-choice intents must request a continue action.')
        if self.intent == 'emotion' and not self.emotion:
            raise ValueError('An emotion intent requires an emotion label.')
        if self.intent != 'emotion' and self.emotion is not None:
            raise ValueError('Only an emotion intent may include an emotion label.')
        if self.confidence == 'low' and not self.needs_clarification:
            raise ValueError('Low-confidence interpretations must request clarification.')
        if self.needs_clarification and not self.clarification_question:
            raise ValueError('Clarification requires one student-facing question.')
        if not self.needs_clarification and self.clarification_question is not None:
            raise ValueError('A clarification question cannot be supplied when clarification is false.')
        if self.intent in {'greeting', 'acknowledge', 'continue_current', 'pause', 'resume', 'continuation_yes', 'continuation_no'}:
            if self.answer is not None or self.normalized_expression is not None or self.problem is not None:
                raise ValueError('Conversation-control intents cannot carry answer or problem payloads.')
        if self.question_type == 'continuation_choice' and self.intent not in {'continuation_yes', 'continuation_no', 'unclear'}:
            raise ValueError('Continuation-choice question type must use continuation intent labels or unclear.')
        return self
