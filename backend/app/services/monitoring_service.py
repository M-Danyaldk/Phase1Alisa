import logging
from datetime import UTC, datetime

from fastapi import Request

from ..config import get_settings
from .email_service import EmailService

logger = logging.getLogger(__name__)


class MonitoringService:
    def __init__(self) -> None:
        self.settings = get_settings()

    def configure(self) -> None:
        if not self.settings.sentry_dsn.strip():
            logger.info('SENTRY_DSN is not configured; external error monitoring is disabled.')
            return
        try:
            import sentry_sdk  # type: ignore
        except Exception:
            logger.warning('SENTRY_DSN is configured, but sentry-sdk is not installed. External error monitoring is disabled.')
            return
        sentry_sdk.init(
            dsn=self.settings.sentry_dsn.strip(),
            environment=self.settings.app_env,
            traces_sample_rate=0.0,
        )

    async def capture_exception(self, request: Request, exc: Exception) -> None:
        route = f'{request.method} {request.url.path}'
        logger.exception('Unhandled backend error on %s', route)
        self._capture_sentry(exc)
        await self._send_owner_alert(route, exc)

    def _capture_sentry(self, exc: Exception) -> None:
        if not self.settings.sentry_dsn.strip():
            return
        try:
            import sentry_sdk  # type: ignore
            sentry_sdk.capture_exception(exc)
        except Exception:
            logger.debug('Sentry capture failed or sentry-sdk is unavailable.', exc_info=True)

    async def _send_owner_alert(self, route: str, exc: Exception) -> None:
        owner_email = self.settings.owner_alert_email.strip()
        if not owner_email:
            return
        text = (
            'A critical MsAlisia backend error occurred.\n\n'
            f'Environment: {self.settings.app_env}\n'
            f'Route: {route}\n'
            f'Error type: {type(exc).__name__}\n'
            f'Timestamp: {datetime.now(UTC).isoformat()}\n\n'
            'Review backend logs for details. No secrets are included in this alert.'
        )
        try:
            await EmailService().send_support_alert(
                recipient_email=owner_email,
                subject='Critical MsAlisia backend error',
                text=text,
            )
        except Exception as alert_exc:
            logger.warning('Owner critical-error alert was not sent: %s', alert_exc)
