"""Email notification channel."""

import smtplib
from email.message import EmailMessage

from loguru import logger

from ditto_foundation.notification.config import NotificationSettings
from ditto_foundation.notification.sender import NotificationSender


class EmailSender(NotificationSender):
    """
    Email notification sender via SMTP.

    Sends HTML email notifications using configured SMTP server.
    """

    def __init__(self, settings: NotificationSettings) -> None:
        """
        Initialize email sender with settings.

        Args:
            settings: Notification settings with SMTP configuration.

        """
        self._settings = settings
        self._to_addrs = settings.email_to.split(",") if settings.email_to else []

        if not self._to_addrs:
            logger.warning(
                "Email recipients not configured",
                event="email_not_configured",
            )

    @property
    def channel_name(self) -> str:
        """Get channel identifier."""
        return "email"

    def send(self, rendered_content: str) -> bool:
        """
        Send rendered HTML email via SMTP.

        Args:
            rendered_content: Rendered HTML content to send.

        Returns:
            True if send was successful, False otherwise.

        """
        if not self._to_addrs:
            logger.warning(
                "Email alert skipped (no recipients)",
                event="email_skipped",
            )
            return False

        try:
            msg = EmailMessage()
            msg["From"] = self._settings.email_from
            msg["To"] = ", ".join(self._to_addrs)
            msg["Subject"] = "Ditto Notification"
            msg.set_content(rendered_content, subtype="html")

            with smtplib.SMTP(
                self._settings.email_smtp_host,
                self._settings.email_smtp_port,
            ) as server:
                if self._settings.email_username and self._settings.email_password:
                    server.starttls()
                    server.login(
                        self._settings.email_username,
                        self._settings.email_password,
                    )
                server.send_message(msg)

            logger.info(
                "Email alert sent successfully",
                event="email_sent",
                recipients=len(self._to_addrs),
            )
            return True

        except Exception as e:
            logger.error(
                "Email alert failed",
                event="email_error",
                error=str(e),
            )
            return False


__all__ = ["EmailSender"]
