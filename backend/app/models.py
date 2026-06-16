from typing import Literal, Optional, List
from pydantic import BaseModel, Field

from .curriculum import LAUNCH_GRADES

Subject = Literal['Math', 'ELA', 'Writing']
TopicSource = Literal['manual', 'default', 'assessment']

class StudentProfile(BaseModel):
    id: Optional[int] = None
    name: str = Field(default='Student', min_length=1)
    grade: int = Field(default=4, ge=min(LAUNCH_GRADES), le=max(LAUNCH_GRADES))
    subjects: list[str] = Field(default_factory=lambda: ['Math', 'ELA', 'Writing'])
    math_level: str = 'Not assessed yet'
    ela_level: str = 'Not assessed yet'
    writing_level: str = 'Not assessed yet'
    confidence: str = 'Unsure yet'
    learning_goals: str = ''
    difficulty_level: str = ''
    focus_notes: str = ''
    parent_notes: str = ''

class ChatHistoryItem(BaseModel):
    role: str
    content: str
    provider: Optional[str] = None
    subject: Optional[str] = None


class TutorStepRecord(BaseModel):
    step_id: str = ''
    label: str = ''
    description: str = ''
    expression: str = ''
    expected_answer: str = ''
    result: str = ''
    updated_expression: str = ''
    status: str = 'pending'
    attempts: int = 0
    explanation: str = ''


class TutorHelperBranch(BaseModel):
    branch_id: str = ''
    branch_type: str = ''
    question: str = ''
    linked_step_id: str = ''
    return_step_id: str = ''
    status: str = 'idle'


class TutorQueuedQuestion(BaseModel):
    question_id: str = ''
    question: str = ''
    subject: str = ''
    source: str = 'student'
    status: str = 'queued'


class TutoringState(BaseModel):
    problem_id: str = ''
    main_problem: str = ''
    active_problem: str = ''
    current_subject: str = ''
    full_problem: str = ''
    ordered_steps: list[TutorStepRecord] = Field(default_factory=list)
    current_step_index: int = 0
    current_step_id: str = ''
    completed_steps: list[str] = Field(default_factory=list)
    current_expression: str = ''
    remaining_steps: list[str] = Field(default_factory=list)
    completed_step_results: list[str] = Field(default_factory=list)
    step_results: dict[str, str] = Field(default_factory=dict)
    attempts_per_step: dict[str, int] = Field(default_factory=dict)
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
    helper_branch: TutorHelperBranch = Field(default_factory=TutorHelperBranch)
    queued_followup_questions: list[TutorQueuedQuestion] = Field(default_factory=list)
    pending_input_kind: str = ''
    pending_new_problem: str = ''
    paused_main_problem: str = ''
    paused_current_step: str = ''
    paused_current_question: str = ''
    paused_completed_steps: list[str] = Field(default_factory=list)
    return_step_index: int = 0
    return_step_id: str = ''
    final_answer: str = ''
    problem_status: str = 'idle'
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

class ChatOpeningRequest(BaseModel):
    student: StudentProfile
    child_id: Optional[str] = None
    subject: Subject
    topic: str = 'general practice'
    topic_source: TopicSource = 'manual'

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

class ChatOpeningResponse(BaseModel):
    reply: str
    provider: str
    model: str
    fallback_used: bool = False
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
    celebration_title: str = 'Great work!'
    celebration_message: str = ''
    performance_label: str = 'Learning Path Ready'
    score_summary: str = ''
    strengths_for_child: list[str] = Field(default_factory=list)
    practice_next: str = ''
    next_step_message: str = ''
    badge_label: str = 'All Done!'
    encouragement: str = ''

class HomeworkFeedbackResponse(BaseModel):
    feedback: str
    provider: str
    model: str
