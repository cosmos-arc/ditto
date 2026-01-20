"""Unit tests for Email sender."""

from unittest.mock import MagicMock, patch

import pytest
from ditto_datahub.alerts.base import AlertLevel, AlertMessage
from ditto_datahub.alerts.email import EmailAlertSender


@pytest.mark.unit
class TestEmailAlertSender:
    """Tests for EmailAlertSender."""

    def test_sender_name_is_email(self) -> None:
        """Test that sender name is 'email'."""
        sender = EmailAlertSender(
            smtp_host="localhost",
            smtp_port=587,
            from_addr="test@example.com",
            to_addrs=["recipient@example.com"],
        )
        assert sender.name == "email"

    def test_initialization_with_parameters(self) -> None:
        """Test initialization with explicit parameters."""
        sender = EmailAlertSender(
            smtp_host="smtp.example.com",
            smtp_port=587,
            username="user",
            password="pass",
            from_addr="sender@example.com",
            to_addrs=["recipient1@example.com", "recipient2@example.com"],
        )

        assert sender._smtp_host == "smtp.example.com"
        assert sender._smtp_port == 587
        assert sender._username == "user"
        assert sender._password == "pass"
        assert sender._from_addr == "sender@example.com"
        assert sender._to_addrs == ["recipient1@example.com", "recipient2@example.com"]

    def test_initialization_defaults_from_env(self) -> None:
        """Test initialization uses environment variables as defaults."""
        with patch("os.getenv") as mock_getenv:
            mock_getenv.side_effect = lambda key, default=None: {
                "SMTP_HOST": "env-host.com",
                "SMTP_PORT": "25",
                "EMAIL_FROM": "env-from@example.com",
                "EMAIL_TO": "env-to@example.com",
            }.get(key, default)

            sender = EmailAlertSender()

            assert sender._smtp_host == "env-host.com"
            assert sender._smtp_port == 25
            assert sender._from_addr == "env-from@example.com"
            assert sender._to_addrs == ["env-to@example.com"]

    def test_send_returns_false_when_no_recipients(self) -> None:
        """Test that send returns False when no recipients configured."""
        sender = EmailAlertSender(to_addrs=[])

        message = AlertMessage(
            level=AlertLevel.ERROR,
            title="Test Alert",
            content="Test content",
        )

        result = sender.send(message)

        assert result is False

    def test_send_returns_true_on_success(self) -> None:
        """Test that send returns True on successful email send."""
        with patch("smtplib.SMTP") as mock_smtp:
            mock_server = MagicMock()
            mock_smtp.return_value.__enter__.return_value = mock_server

            sender = EmailAlertSender(
                to_addrs=["recipient@example.com"],
                username="user",
                password="pass",
            )

            message = AlertMessage(
                level=AlertLevel.ERROR,
                title="Test Alert",
                content="Test content",
            )

            result = sender.send(message)

            assert result is True
            mock_server.starttls.assert_called_once()
            mock_server.login.assert_called_once_with("user", "pass")
            mock_server.send_message.assert_called_once()

    def test_send_without_auth(self) -> None:
        """Test that send works without authentication."""
        with patch("smtplib.SMTP") as mock_smtp:
            mock_server = MagicMock()
            mock_smtp.return_value.__enter__.return_value = mock_server

            sender = EmailAlertSender(
                to_addrs=["recipient@example.com"],
            )

            message = AlertMessage(
                level=AlertLevel.WARNING,
                title="Test Warning",
                content="Warning content",
            )

            result = sender.send(message)

            assert result is True
            mock_server.starttls.assert_not_called()
            mock_server.login.assert_not_called()
            mock_server.send_message.assert_called_once()

    def test_send_returns_false_on_exception(self) -> None:
        """Test that send returns False when exception occurs."""
        with patch("smtplib.SMTP") as mock_smtp:
            mock_smtp.side_effect = Exception("SMTP error")

            sender = EmailAlertSender(
                to_addrs=["recipient@example.com"],
            )

            message = AlertMessage(
                level=AlertLevel.ERROR,
                title="Test Alert",
                content="Test content",
            )

            result = sender.send(message)

            assert result is False

    def test_send_formats_message_correctly(self) -> None:
        """Test that send formats message correctly."""
        with patch("smtplib.SMTP") as mock_smtp:
            mock_server = MagicMock()
            mock_smtp.return_value.__enter__.return_value = mock_server

            sender = EmailAlertSender(
                from_addr="sender@example.com",
                to_addrs=["recipient@example.com"],
            )

            message = AlertMessage(
                level=AlertLevel.CRITICAL,
                title="Critical Alert",
                content="Critical content",
                context={"key": "value"},
            )

            sender.send(message)

            # Check email headers
            sent_msg = mock_server.send_message.call_args[0][0]
            assert sent_msg["From"] == "sender@example.com"
            assert sent_msg["To"] == "recipient@example.com"
            assert "[CRITICAL]" in sent_msg["Subject"]
            assert "Critical Alert" in sent_msg["Subject"]

            # Check email body
            body = sent_msg.get_content()
            assert "Critical Alert" in body
            assert "Critical content" in body
            assert "key: value" in body

    def test_multiple_recipients_joined_with_comma(self) -> None:
        """Test that multiple recipients are joined correctly."""
        with patch("smtplib.SMTP") as mock_smtp:
            mock_server = MagicMock()
            mock_smtp.return_value.__enter__.return_value = mock_server

            sender = EmailAlertSender(
                to_addrs=["recipient1@example.com", "recipient2@example.com"],
            )

            message = AlertMessage(
                level=AlertLevel.INFO,
                title="Test",
                content="Content",
            )

            sender.send(message)

            sent_msg = mock_server.send_message.call_args[0][0]
            assert sent_msg["To"] == "recipient1@example.com, recipient2@example.com"

    def test_smtp_host_default_to_localhost(self) -> None:
        """Test that SMTP host defaults to localhost."""
        with patch("os.getenv") as mock_getenv:
            mock_getenv.side_effect = lambda key, default=None: default
            sender = EmailAlertSender()
            assert sender._smtp_host == "localhost"

    def test_smtp_port_default_to_587(self) -> None:
        """Test that SMTP port defaults to 587."""
        with patch("os.getenv") as mock_getenv:
            mock_getenv.side_effect = lambda key, default=None: default
            sender = EmailAlertSender()
            assert sender._smtp_port == 587

    def test_from_addr_default_to_noreply(self) -> None:
        """Test that from address defaults to noreply@ditto.local."""
        with patch("os.getenv") as mock_getenv:
            mock_getenv.side_effect = lambda key, default=None: default
            sender = EmailAlertSender()
            assert sender._from_addr == "noreply@ditto.local"
