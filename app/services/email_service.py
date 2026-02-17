"""Email sending via SMTP (aiosmtplib). Used for OTP, verification, invites. No-op when SMTP not configured."""

import logging
from email.message import EmailMessage

import aiosmtplib

from app.config import settings

logger = logging.getLogger(__name__)


class EmailService:
    """Async email sender. Skips send and logs warning if SMTP_HOST/USER/PASSWORD not set."""

    @staticmethod
    async def send_email(to_email: str, subject: str, body: str) -> None:
        if not all([settings.SMTP_HOST, settings.SMTP_USER, settings.SMTP_PASSWORD]):
            logger.warning("SMTP not configured. Skipping email send.")
            return
        message = EmailMessage()
        # From: use EMAILS_FROM_NAME/EMAILS_FROM_EMAIL or fall back to InternTrack / SMTP_USER.
        message["From"] = (
            f"{settings.EMAILS_FROM_NAME or 'InternTrack'} <{settings.EMAILS_FROM_EMAIL or settings.SMTP_USER}>"
        )
        message["To"] = to_email
        message["Subject"] = subject
        message.set_content(body)
        try:
            await aiosmtplib.send(
                message,
                hostname=settings.SMTP_HOST,
                port=settings.SMTP_PORT,
                username=settings.SMTP_USER,
                password=settings.SMTP_PASSWORD,
                start_tls=True,  # Upgrade to TLS after connect (e.g. port 587).
            )
            logger.info("Email sent to %s", to_email)
        except Exception as e:
            logger.error("Failed to send email to %s: %s", to_email, e)


# Single instance for dependency injection (auth, invitation, etc.).
email_service = EmailService()
