from typing import Literal

from pydantic import BaseModel

Subject = Literal['Math', 'ELA', 'Writing']
AchievementStatus = Literal['earned', 'locked', 'in_progress']


class StudentDashboardProfile(BaseModel):
    child_id: str
    name: str
    grade_level: str
    status: str
    weekly_focus: str


class StudentProgressItem(BaseModel):
    subject: Subject
    level: str
    enrolled_grade: str | None = None
    working_level: str | None = None
    working_level_source: str = 'assessment'
    progress_percentage: int
    current_focus: str
    next_step: str
    status: str


class StudentActivityItem(BaseModel):
    id: str
    title: str
    detail: str
    when: str
    subject: Subject | None = None


class StudentAchievement(BaseModel):
    id: str
    title: str
    detail: str
    status: AchievementStatus


class WeeklyRhythmResponse(BaseModel):
    child_id: str
    week_start_date: str
    week_end_date: str
    session_count: int
    active_tutoring_seconds: int = 0
    achievement_label: str
    display_label: str
    child_message: str
    parent_summary: str


class WeeklyRhythmListResponse(BaseModel):
    rhythms: list[WeeklyRhythmResponse]


class StudentDashboardResponse(BaseModel):
    student: StudentDashboardProfile
    assessment_status: str
    homework_status: str
    weekly_focus: str
    weekly_rhythm: WeeklyRhythmResponse
    subject_progress: list[StudentProgressItem]
    recent_activity: list[StudentActivityItem]
    achievements: list[StudentAchievement]
    recommended_next_actions: list[str]
    data_source: str = 'backend'
