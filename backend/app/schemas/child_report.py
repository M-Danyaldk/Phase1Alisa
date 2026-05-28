from pydantic import BaseModel

from .homework import HomeworkHistoryItem


class SubjectProgress(BaseModel):
    subject: str
    level: str
    progress_percentage: int = 0
    current_topic: str | None = None
    strong_area: str | None = None
    needs_review: str | None = None
    recent_improvement: str | None = None
    completed_lessons: int = 0
    assessment_count: int = 0
    chat_count: int = 0
    message_count: int = 0
    last_activity_at: str | None = None


class AssessmentSummary(BaseModel):
    id: int | str | None = None
    subject: str
    estimated_level: str
    score_label: str | None = None
    strengths: list[str] = []
    learning_gaps: list[str] = []
    recommended_progression: list[str] = []
    recommended_next_topics: list[str] = []
    parent_summary: str | None = None
    created_at: str | None = None


class TutorSessionSummary(BaseModel):
    thread_id: str
    subject: str
    topic: str | None = None
    title: str | None = None
    message_count: int = 0
    time_spent: str = 'Not tracked yet'
    hints_used: int = 0
    practice_attempts: int = 0
    improvement_status: str = 'Progress details will appear as more sessions are saved.'
    next_step: str = 'Continue with one short practice session.'
    last_activity_at: str | None = None


class ChildReportResponse(BaseModel):
    child_id: str
    child_name: str
    grade_level: str
    report_period: str
    subject_filter: str
    current_learning_level: str
    last_updated_at: str | None = None
    lessons_completed: int = 0
    questions_practiced: int = 0
    assessment_status: str
    overall_summary: str
    weekly_progress: str
    time_spent_learning: str
    brain_break_summary: str
    subject_progress: list[SubjectProgress]
    recent_assessments: list[AssessmentSummary]
    recent_tutor_sessions: list[TutorSessionSummary]
    homework_uploads: list[HomeworkHistoryItem] = []
    strengths: list[str]
    weak_areas: list[str]
    recommended_next_steps: list[str]


class WeeklyReportEmailPreview(BaseModel):
    child_id: str
    child_name: str
    parent_id: str
    report_period: str = 'week'
    subject_line: str
    greeting: str
    summary: str
    subject_progress: list[SubjectProgress]
    strengths: list[str]
    weak_areas: list[str]
    recommended_next_steps: list[str]
    brain_break_summary: str
    generated_at: str
    email_connected: bool = False
    email_note: str = 'Weekly email sending is prepared, but no email provider is connected yet.'
