"""Email alert sender."""

import os
import smtplib
from email.message import EmailMessage

from ditto_foundation import logger

from ditto_datahub.alerts.base import AlertMessage, AlertSender


class EmailAlertSender(AlertSender):
    """Email alert sender via SMTP."""

    def __init__(
        self,
        smtp_host: str | None = None,
        smtp_port: int | None = None,
        username: str | None = None,
        password: str | None = None,
        from_addr: str | None = None,
        to_addrs: list[str] | None = None,
    ) -> None:
        """
        Initialize email alert sender.

        Args:
            smtp_host: SMTP server host. Defaults to SMTP_HOST env var.
            smtp_port: SMTP server port. Defaults to SMTP_PORT env var.
            username: SMTP username. Defaults to SMTP_USERNAME env var.
            password: SMTP password. Defaults to SMTP_PASSWORD env var.
            from_addr: From address. Defaults to EMAIL_FROM env var.
            to_addrs: To addresses. Defaults to EMAIL_TO env var (comma-separated).

        """
        self._smtp_host = smtp_host or os.getenv("SMTP_HOST", "localhost")
        self._smtp_port = smtp_port or int(os.getenv("SMTP_PORT", "587"))
        self._username = username or os.getenv("SMTP_USERNAME")
        self._password = password or os.getenv("SMTP_PASSWORD")
        self._from_addr = from_addr or os.getenv("EMAIL_FROM", "noreply@ditto.local")
        self._to_addrs = to_addrs or (
            os.getenv("EMAIL_TO", "").split(",") if os.getenv("EMAIL_TO") else []
        )

        if not self._to_addrs:
            logger.warning(
                "Email recipients not configured",
                event="email_not_configured",
            )

    @property
    def name(self) -> str:
        """Sender name."""
        return "email"

    def send(self, message: AlertMessage) -> bool:
        """Send alert via email."""
        if not self._to_addrs:
            logger.warning(
                "Email alert skipped (no recipients)",
                event="email_skipped",
                title=message.title,
            )
            return False

        try:
            msg = EmailMessage()
            msg["From"] = self._from_addr
            msg["To"] = ", ".join(self._to_addrs)
            msg["Subject"] = f"[{message.level.value.upper()}] {message.title}"
            msg.set_content(message.format())

            host = self._smtp_host or "localhost"
            with smtplib.SMTP(host, int(self._smtp_port)) as server:
                if self._username and self._password:
                    server.starttls()
                    server.login(self._username, self._password)
                server.send_message(msg)

            logger.debug(
                "Email alert sent",
                event="email_sent",
                title=message.title,
                recipients=len(self._to_addrs),
            )
            return True

        except Exception as e:
            logger.error(
                "Email alert failed",
                event="email_error",
                title=message.title,
                error=str(e),
            )
            return False
