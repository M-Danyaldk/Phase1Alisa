from typing import Literal

from pydantic import BaseModel, Field


ReportCategory = Literal['something_wrong', 'unsafe_or_uncomfortable', 'confusing_answer', 'technical_issue', 'other']
ReportSource = Literal['learning', 'homework', 'assessment']
ReporterType = Literal['child', 'parent']


class ProblemReportRequest(BaseModel):
    reporter_type: ReporterType = 'child'
    child_id: str
    source: ReportSource
    category: ReportCategory = 'other'
    description: str = Field(default='', max_length=1000)
    subject: str | None = Field(default=None, max_length=40)
    session_id: str | None = None
    thread_id: str | None = None
    message_id: str | None = None
    message_context: str | None = Field(default=None, max_length=2000)


class ProblemReportResponse(BaseModel):
    success: bool
    message: str
    report_id: str | None = None
    support_alert_sent: bool = False
