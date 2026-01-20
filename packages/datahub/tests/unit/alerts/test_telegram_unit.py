"""Unit tests for Telegram sender."""

from unittest.mock import MagicMock, patch

import pytest
from ditto_datahub.alerts.base import AlertLevel, AlertMessage
from ditto_datahub.alerts.telegram import TelegramAlertSender
from httpx import Response


@pytest.mark.unit
class TestTelegramAlertSender:
    """Tests for TelegramAlertSender."""

    def test_sender_name_is_telegram(self) -> None:
        """Test that sender name is 'telegram'."""
        sender = TelegramAlertSender(
            bot_token="test_token",
            chat_id="test_chat",
        )
        assert sender.name == "telegram"

    def test_initialization_with_parameters(self) -> None:
        """Test initialization with explicit parameters."""
        sender = TelegramAlertSender(
            bot_token="test_bot_token",
            chat_id="test_chat_id",
        )

        assert sender._bot_token == "test_bot_token"
        assert sender._chat_id == "test_chat_id"

    def test_initialization_defaults_from_env(self) -> None:
        """Test initialization uses environment variables as defaults."""
        with patch("os.getenv") as mock_getenv:
            mock_getenv.side_effect = lambda key, default=None: {
                "TELEGRAM_BOT_TOKEN": "env_token",
                "TELEGRAM_CHAT_ID": "env_chat_id",
            }.get(key, default)

            sender = TelegramAlertSender()

            assert sender._bot_token == "env_token"
            assert sender._chat_id == "env_chat_id"

    def test_send_returns_false_when_not_configured(self) -> None:
        """Test that send returns False when bot_token or chat_id missing."""
        # No bot_token
        sender = TelegramAlertSender(bot_token=None, chat_id="test")
        message = AlertMessage(
            level=AlertLevel.ERROR,
            title="Test Alert",
            content="Test content",
        )
        assert sender.send(message) is False

        # No chat_id
        sender = TelegramAlertSender(bot_token="test", chat_id=None)
        assert sender.send(message) is False

        # Both None
        sender = TelegramAlertSender(bot_token=None, chat_id=None)
        assert sender.send(message) is False

    def test_send_returns_true_on_success(self) -> None:
        """Test that send returns True on successful API call."""
        with patch("httpx.post") as mock_post:
            mock_response = MagicMock(spec=Response)
            mock_response.raise_for_status = MagicMock()
            mock_post.return_value = mock_response

            sender = TelegramAlertSender(
                bot_token="test_token",
                chat_id="test_chat_id",
            )

            message = AlertMessage(
                level=AlertLevel.ERROR,
                title="Test Alert",
                content="Test content",
            )

            result = sender.send(message)

            assert result is True
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            assert "telegram.org" in call_args[0][0]
            assert call_args[1]["json"]["chat_id"] == "test_chat_id"
            assert "parse_mode" in call_args[1]["json"]

    def test_send_returns_false_on_http_error(self) -> None:
        """Test that send returns False when HTTP request fails."""
        with patch("httpx.post") as mock_post:
            mock_post.side_effect = Exception("HTTP error")

            sender = TelegramAlertSender(
                bot_token="test_token",
                chat_id="test_chat_id",
            )

            message = AlertMessage(
                level=AlertLevel.ERROR,
                title="Test Alert",
                content="Test content",
            )

            result = sender.send(message)

            assert result is False

    def test_send_returns_false_on_raise_for_status(self) -> None:
        """Test that send returns False when response status is error."""
        with patch("httpx.post") as mock_post:
            mock_response = MagicMock(spec=Response)
            mock_response.raise_for_status.side_effect = Exception("403 Forbidden")
            mock_post.return_value = mock_response

            sender = TelegramAlertSender(
                bot_token="test_token",
                chat_id="test_chat_id",
            )

            message = AlertMessage(
                level=AlertLevel.ERROR,
                title="Test Alert",
                content="Test content",
            )

            result = sender.send(message)

            assert result is False

    def test_send_formats_message_correctly(self) -> None:
        """Test that send formats message with AlertMessage.format()."""
        with patch("httpx.post") as mock_post:
            mock_response = MagicMock(spec=Response)
            mock_response.raise_for_status = MagicMock()
            mock_post.return_value = mock_response

            sender = TelegramAlertSender(
                bot_token="test_token",
                chat_id="test_chat_id",
            )

            message = AlertMessage(
                level=AlertLevel.CRITICAL,
                title="Critical Alert",
                content="Critical content",
                context={"key": "value"},
            )

            sender.send(message)

            # Check the payload
            call_args = mock_post.call_args
            payload = call_args[1]["json"]
            assert "Critical Alert" in payload["text"]
            assert "Critical content" in payload["text"]
            assert "key: value" in payload["text"]

    def test_send_uses_correct_url(self) -> None:
        """Test that send constructs correct Telegram API URL."""
        with patch("httpx.post") as mock_post:
            mock_response = MagicMock(spec=Response)
            mock_response.raise_for_status = MagicMock()
            mock_post.return_value = mock_response

            sender = TelegramAlertSender(
                bot_token="my_bot_token_123",
                chat_id="my_chat_id",
            )

            message = AlertMessage(
                level=AlertLevel.INFO,
                title="Test",
                content="Content",
            )

            sender.send(message)

            # Check URL construction
            url = mock_post.call_args[0][0]
            assert url == "https://api.telegram.org/botmy_bot_token_123/sendMessage"

    def test_send_sets_parse_mode_to_markdown(self) -> None:
        """Test that send sets parse_mode to Markdown."""
        with patch("httpx.post") as mock_post:
            mock_response = MagicMock(spec=Response)
            mock_response.raise_for_status = MagicMock()
            mock_post.return_value = mock_response

            sender = TelegramAlertSender(
                bot_token="test_token",
                chat_id="test_chat_id",
            )

            message = AlertMessage(
                level=AlertLevel.WARNING,
                title="Warning",
                content="Warning content",
            )

            sender.send(message)

            # Check parse_mode
            payload = mock_post.call_args[1]["json"]
            assert payload["parse_mode"] == "Markdown"

    def test_send_includes_timeout(self) -> None:
        """Test that send includes timeout parameter."""
        with patch("httpx.post") as mock_post:
            mock_response = MagicMock(spec=Response)
            mock_response.raise_for_status = MagicMock()
            mock_post.return_value = mock_response

            sender = TelegramAlertSender(
                bot_token="test_token",
                chat_id="test_chat_id",
            )

            message = AlertMessage(
                level=AlertLevel.INFO,
                title="Test",
                content="Content",
            )

            sender.send(message)

            # Check timeout
            timeout = mock_post.call_args[1]["timeout"]
            assert timeout == 10
