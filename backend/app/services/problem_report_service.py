import logging
from datetime import UTC, datetime

from fastapi import HTTPException

from ..schemas.problem_reports import ProblemReportRequest
from .email_service import EmailService
from .supabase_client import SupabaseClient, SupabaseClientError

logger = logging.getLogger(__name__)
SUPPORT_EMAIL = 'support@msalisia.com'


class ProblemReportService:
    def __init__(self) -> None:
        self.supabase = SupabaseClient()

    async def create_report(self, parent_id: str, reporter_user_id: str | None, payload: ProblemReportRequest) -> dict:
        now = datetime.now(UTC).isoformat()
        report_payload = {
            'parent_id': parent_id,
            'child_id': payload.child_id,
            'learning_session_id': payload.session_id,
            'chat_message_id': payload.message_id,
            'reporter_user_id': reporter_user_id,
            'reporter_type': payload.reporter_type,
            'issue_category': payload.category,
            'description': payload.description.strip(),
            'status': 'open',
            'alert_sent_to_support': False,
            'metadata': {
                'source': payload.source,
                'subject': payload.subject,
                'thread_id': payload.thread_id,
                'message_context': payload.message_context,
                'reported_at': now,
            },
        }
        try:
            records = await self.supabase.insert('problem_reports', report_payload)
        except SupabaseClientError as exc:
            if self._missing_problem_reports_table(exc):
                raise HTTPException(status_code=503, detail='Problem reporting is not set up yet.') from exc
            raise HTTPException(status_code=exc.status_code, detail='We could not send the report right now. Please try again.') from exc

        report = records[0] if records else report_payload
        support_alert_sent = await self._send_support_alert(report)
        if support_alert_sent and report.get('id'):
            try:
                await self.supabase.update('problem_reports', {'id': f'eq.{report["id"]}'}, {
                    'alert_sent_to_support': True,
                    'updated_at': datetime.now(UTC).isoformat(),
                })
            except SupabaseClientError as exc:
                logger.warning('Problem report support alert flag update failed for %s: %s', report.get('id'), exc)
        return {
            'success': True,
            'message': 'Thanks — your report has been sent.',
            'report_id': report.get('id'),
            'support_alert_sent': support_alert_sent,
        }

    async def _send_support_alert(self, report: dict) -> bool:
        try:
            await EmailService().send_support_alert(
                recipient_email=SUPPORT_EMAIL,
                subject='New MsAlisia problem report',
                text=self._support_alert_text(report),
            )
            return True
        except Exception as exc:
            logger.warning('Problem report support alert failed for %s: %s', report.get('id'), exc)
            return False

    def _support_alert_text(self, report: dict) -> str:
        metadata = report.get('metadata') or {}
        return (
            'A new MsAlisia problem report was submitted.\n\n'
            f"Report ID: {report.get('id') or 'Not available'}\n"
            f"Reporter type: {report.get('reporter_type')}\n"
            f"Parent ID: {report.get('parent_id')}\n"
            f"Child ID: {report.get('child_id')}\n"
            f"Source: {metadata.get('source') or 'Not provided'}\n"
            f"Subject: {metadata.get('subject') or 'Not provided'}\n"
            f"Category: {report.get('issue_category')}\n"
            f"Description: {report.get('description') or 'No description provided'}\n"
            f"Thread ID: {metadata.get('thread_id') or 'Not provided'}\n"
            f"Session ID: {report.get('learning_session_id') or 'Not provided'}\n"
        )

    def _missing_problem_reports_table(self, exc: SupabaseClientError) -> bool:
        message = str(exc).lower()
        return 'problem_reports' in message and ('schema cache' in message or 'could not find' in message or 'does not exist' in message)
