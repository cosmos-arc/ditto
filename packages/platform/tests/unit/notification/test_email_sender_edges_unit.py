"""SMTP-free success and failure tests for the email notification channel."""

from __future__ import annotations

import smtplib
from unittest.mock import MagicMock, patch

import ditto_platform.services.notification.channels.email as email_module
import pytest
from ditto_platform.services.notification.channels.email import EmailSender
from ditto_platform.services.notification.config import NotificationSettings


def _settings(**overrides: object) -> NotificationSettings:
    values: dict[str, object] = {
        "email_smtp_host": "smtp.invalid",
        "email_smtp_port": 2525,
        "email_from": "ditto@example.test",
        "email_to": "first@example.test,second@example.test",
    }
    values.update(overrides)
    return NotificationSettings.model_validate(values)


def test_sender_without_recipients_skips_smtp() -> None:
    log = MagicMock()
    with (
        patch.object(email_module, "logger", log),
        patch.object(email_module.smtplib, "SMTP") as smtp,
    ):
        sender = EmailSender(_settings(email_to=""))

        assert sender.channel_name == "email"
        assert sender.send("<p>unused</p>") is False

    smtp.assert_not_called()
    assert [call.kwargs["event"] for call in log.warning.call_args_list] == [
        "email_not_configured",
        "email_skipped",
    ]


def test_sender_builds_html_message_without_optional_smtp_credentials() -> None:
    with patch.object(email_module.smtplib, "SMTP") as smtp:
        server = smtp.return_value.__enter__.return_value
        sender = EmailSender(_settings())

        assert sender.send("<strong>ready</strong>") is True

    smtp.assert_called_once_with("smtp.invalid", 2525)
    server.starttls.assert_not_called()
    server.login.assert_not_called()
    message = server.send_message.call_args.args[0]
    assert message["From"] == "ditto@example.test"
    assert message["To"] == "first@example.test, second@example.test"
    assert message.get_content_type() == "text/html"
    assert "<strong>ready</strong>" in message.get_content()


def test_sender_authenticates_when_both_credentials_are_configured() -> None:
    with patch.object(email_module.smtplib, "SMTP") as smtp:
        server = smtp.return_value.__enter__.return_value
        sender = EmailSender(_settings(email_username="ditto", email_password="secret"))

        assert sender.send("authenticated") is True

    server.starttls.assert_called_once_with()
    server.login.assert_called_once_with("ditto", "secret")
    server.send_message.assert_called_once()


@pytest.mark.parametrize(
    ("failure", "event"),
    [
        (smtplib.SMTPAuthenticationError(535, b"rejected"), "email_auth_error"),
        (smtplib.SMTPConnectError(421, "unavailable"), "email_connect_error"),
        (smtplib.SMTPRecipientsRefused({}), "email_recipients_refused"),
        (smtplib.SMTPException("protocol failure"), "email_smtp_error"),
        (OSError("network failure"), "email_network_error"),
    ],
)
def test_sender_contains_known_smtp_and_network_failures(
    failure: Exception,
    event: str,
) -> None:
    log = MagicMock()
    with (
        patch.object(email_module, "logger", log),
        patch.object(email_module.smtplib, "SMTP", side_effect=failure),
    ):
        assert EmailSender(_settings()).send("content") is False

    assert log.error.call_args.kwargs == {"event": event}


def test_sender_reraises_unexpected_programming_errors() -> None:
    log = MagicMock()
    with (
        patch.object(email_module, "logger", log),
        patch.object(
            email_module.smtplib,
            "SMTP",
            side_effect=ValueError("invalid message state"),
        ),
        pytest.raises(ValueError, match="invalid message state"),
    ):
        EmailSender(_settings()).send("content")

    assert log.error.call_args.kwargs["event"] == "email_unexpected_error"
    assert log.error.call_args.kwargs["error_type"] == "ValueError"
