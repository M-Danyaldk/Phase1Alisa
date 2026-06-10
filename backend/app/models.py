from typing import Literal, Optional, List
from pydantic import BaseModel, Field

from .curriculum import LAUNCH_GRADES

Subject = Literal['Math', 'ELA', 'Writing']
TopicSource = Literal['manual', 'default', 'assessment']

class StudentProfile(BaseModel):
    id: Optional[int] = None
    name: str = Field(default='Student', min_length=1)
    grade: int = Field(default=4, ge=min(LAUNCH_GRADES), le=max(LAUNCH_GRADES))
    math_level: str = 'Not assessed yet'
    ela_level: str = 'Not assessed yet'
    writing_level: str = 'Not assessed yet'
    confidence: str = 'Unsure yet'
    focus_notes: str = ''
    parent_notes: str = ''

class ChatHistoryItem(BaseModel):
    role: str
    content: str
    provider: Optional[str] = None
    subject: Optional[str] = None


class TutoringState(BaseModel):
    active_problem: str = ''
    current_subject: str = ''
    full_problem: str = ''
    completed_steps: list[str] = Field(default_factory=list)
    current_expression: str = ''
    remaining_steps: list[str] = Field(default_factory=list)
    current_step: str = ''
    current_question: str = ''
    expected_answer: str = ''
    student_answer: str = ''
    correctness_status: str = ''
    skill: str = ''
    step_number: int = 0
    attempt_count: int = 0
    hint_given: bool = False
    answer_revealed: bool = False
    next_similar_question: str = ''
    mode: str = 'solve'
    status: str = 'idle'
    memory_note: str = ''

class ChatRequest(BaseModel):
    student: StudentProfile
    subject: Subject
    topic: str = 'general practice'
    topic_source: TopicSource = 'manual'
    message: str
    history: List[ChatHistoryItem] = Field(default_factory=list)
    tutoring_state: TutoringState = Field(default_factory=TutoringState)
    thread_id: Optional[str] = None
    child_id: Optional[str] = None

class ChatResponse(BaseModel):
    reply: str
    provider: str
    model: str
    fallback_used: bool = False
    tutoring_state: TutoringState = Field(default_factory=TutoringState)
    thread_id: Optional[str] = None
    history_saved: bool = False
    history_error: Optional[str] = None
    resolved_topic: Optional[str] = None
    topic_source: Optional[str] = None
    assessed_level: Optional[str] = None

class AssessmentRequest(BaseModel):
    student: StudentProfile
    child_id: Optional[str] = None
    subject: Subject
    grade: int = Field(default=4, ge=min(LAUNCH_GRADES), le=max(LAUNCH_GRADES))
    questions: list[str]
    answers: list[str]
    question_ids: list[str] = Field(default_factory=list)
    assessment_version: Optional[int] = None


class AssessmentNextRequest(BaseModel):
    child_id: str
    subject: Subject


class AssessmentQuestionPrompt(BaseModel):
    id: str
    prompt: str


class AssessmentSelectionResponse(BaseModel):
    subject: Subject
    grade: int
    assessment_version: int
    question_ids: list[str]
    questions: list[AssessmentQuestionPrompt]


class AssessmentQuestionResult(BaseModel):
    question_id: str = ''
    position: int
    skill: str = ''
    question: str
    student_answer: str
    expected_answer: str = ''
    status: str = 'needs_review'
    validation_type: str = 'needs_review'
    confidence: str = 'low'
    feedback_note: str = ''
    child_feedback: str = ''
    next_topic_if_incorrect: str = ''

class AssessmentResult(BaseModel):
    subject: Subject
    enrolled_grade: int
    assessment_version: Optional[int] = None
    assessment_question_ids: list[str] = Field(default_factory=list)
    question_results: list[AssessmentQuestionResult] = Field(default_factory=list)
    correct_count: int = 0
    total_questions: int = 0
    estimated_level: str
    score_label: str
    strengths: list[str]
    learning_gaps: list[str]
    recommended_progression: list[str]
    recommended_next_topics: list[str] = Field(default_factory=list)
    parent_summary: str
    provider: str = 'local'
    model: str = 'rules'


class ChildAssessmentResult(BaseModel):
    subject: Subject
    child_message: str
    assessment_version: Optional[int] = None
    assessment_question_ids: list[str] = Field(default_factory=list)
    question_results: list[AssessmentQuestionResult] = Field(default_factory=list)
    correct_count: int = 0
    total_questions: int = 0
    estimated_level: str = 'Learning path ready'
    score_label: str = 'Learning path ready'
    strengths: list[str] = Field(default_factory=list)
    learning_gaps: list[str] = Field(default_factory=list)
    recommended_progression: list[str] = Field(default_factory=list)
    recommended_next_topics: list[str] = Field(default_factory=list)
    parent_summary: str = ''
    celebration_title: str = 'Check-in complete'
    celebration_message: str = ''
    performance_label: str = 'Learning Path Ready'
    score_summary: str = ''
    strengths_for_child: list[str] = Field(default_factory=list)
    practice_next: str = ''
    next_step_message: str = ''
    badge_label: str = 'Check-in Complete'
    encouragement: str = ''

class HomeworkFeedbackResponse(BaseModel):
    feedback: str
    provider: str
    model: str
