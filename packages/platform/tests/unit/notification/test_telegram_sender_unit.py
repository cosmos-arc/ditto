"""TelegramSender unit tests."""

from unittest.mock import Mock, patch

import httpx
import pytest
from ditto_platform.services.notification.channels.telegram import TelegramSender
from ditto_platform.services.notification.config import NotificationSettings


class TestTelegramSenderInit:
    """Tests for TelegramSender initialization."""

    def test_init_with_valid_settings(self) -> None:
        """Test initialization with valid telegram settings."""
        settings = NotificationSettings(
            telegram_bot_token="test_token:123",
            telegram_chat_id="test_chat_id",
        )
        sender = TelegramSender(settings)

        assert sender.channel_name == "telegram"

    def test_init_raises_error_without_bot_token(self) -> None:
        """Test initialization raises ValueError without bot token."""
        settings = NotificationSettings(
            telegram_bot_token=None,
            telegram_chat_id="test_chat_id",
        )

        with pytest.raises(ValueError, match="telegram_bot_token is required"):
            TelegramSender(settings)

    def test_init_raises_error_without_chat_id(self) -> None:
        """Test initialization raises ValueError without chat id."""
        settings = NotificationSettings(
            telegram_bot_token="test_token:123",
            telegram_chat_id=None,
        )

        with pytest.raises(ValueError, match="telegram_chat_id is required"):
            TelegramSender(settings)

    def test_init_raises_error_with_empty_strings(self) -> None:
        """Test initialization raises ValueError with empty strings."""
        settings = NotificationSettings(
            telegram_bot_token="",
            telegram_chat_id="",
        )

        with pytest.raises(ValueError, match="telegram_bot_token is required"):
            TelegramSender(settings)


class TestTelegramSenderSend:
    """Tests for TelegramSender.send method."""

    def test_send_success(self) -> None:
        """Test successful message sending."""
        settings = NotificationSettings(
            telegram_bot_token="test_token:123",
            telegram_chat_id="test_chat_id",
        )
        sender = TelegramSender(settings)

        client_path = (
            "ditto_platform.services.notification.channels.telegram.httpx.Client"
        )
        with patch(client_path) as mock_client_class:
            mock_response = Mock()
            mock_response.raise_for_status = Mock()
            mock_client_instance = Mock()
            mock_client_instance.__enter__ = Mock(return_value=mock_client_instance)
            mock_client_instance.__exit__ = Mock(return_value=False)
            mock_client_instance.post = Mock(return_value=mock_response)
            mock_client_class.return_value = mock_client_instance

            result = sender.send("Test message")

            assert result is True
            mock_client_instance.post.assert_called_once()
            call_kwargs = mock_client_instance.post.call_args[1]
            assert call_kwargs["json"]["chat_id"] == "test_chat_id"
            assert call_kwargs["json"]["text"] == "Test message"
            assert call_kwargs["json"]["parse_mode"] == "Markdown"

    def test_send_raises_on_generic_exception(self) -> None:
        """Test send raises generic exceptions (not httpx exceptions)."""
        settings = NotificationSettings(
            telegram_bot_token="test_token:123",
            telegram_chat_id="test_chat_id",
        )
        sender = TelegramSender(settings)

        client_path = (
            "ditto_platform.services.notification.channels.telegram.httpx.Client"
        )
        with patch(client_path) as mock_client_class:
            mock_client_instance = Mock()
            mock_client_instance.__enter__ = Mock(return_value=mock_client_instance)
            mock_client_instance.__exit__ = Mock(return_value=False)
            mock_client_instance.post = Mock(
                side_effect=RuntimeError("Unexpected error")
            )
            mock_client_class.return_value = mock_client_instance

            # 未预期的异常应该抛出
            with pytest.raises(RuntimeError, match="Unexpected error"):
                sender.send("Test message")

    def test_send_returns_false_on_timeout(self) -> None:
        """Test send returns False on timeout exception."""
        settings = NotificationSettings(
            telegram_bot_token="test_token:123",
            telegram_chat_id="test_chat_id",
        )
        sender = TelegramSender(settings)

        client_path = (
            "ditto_platform.services.notification.channels.telegram.httpx.Client"
        )
        with patch(client_path) as mock_client_class:
            mock_client_instance = Mock()
            mock_client_instance.__enter__ = Mock(return_value=mock_client_instance)
            mock_client_instance.__exit__ = Mock(return_value=False)
            mock_client_instance.post = Mock(
                side_effect=httpx.TimeoutException("Request timeout")
            )
            mock_client_class.return_value = mock_client_instance

            result = sender.send("Test message")

            assert result is False

    def test_send_returns_false_on_http_status_error(self) -> None:
        """Test send returns False on HTTP status error."""
        settings = NotificationSettings(
            telegram_bot_token="test_token:123",
            telegram_chat_id="test_chat_id",
        )
        sender = TelegramSender(settings)

        client_path = (
            "ditto_platform.services.notification.channels.telegram.httpx.Client"
        )
        with patch(client_path) as mock_client_class:
            mock_response = Mock()
            mock_response.status_code = 403
            error = httpx.HTTPStatusError(
                "Forbidden", request=Mock(), response=mock_response
            )
            mock_client_instance = Mock()
            mock_client_instance.__enter__ = Mock(return_value=mock_client_instance)
            mock_client_instance.__exit__ = Mock(return_value=False)
            mock_client_instance.post = Mock(side_effect=error)
            mock_client_class.return_value = mock_client_instance

            result = sender.send("Test message")

            assert result is False

    def test_send_returns_false_on_network_error(self) -> None:
        """Test send returns False on network error."""
        settings = NotificationSettings(
            telegram_bot_token="test_token:123",
            telegram_chat_id="test_chat_id",
        )
        sender = TelegramSender(settings)

        client_path = (
            "ditto_platform.services.notification.channels.telegram.httpx.Client"
        )
        with patch(client_path) as mock_client_class:
            mock_client_instance = Mock()
            mock_client_instance.__enter__ = Mock(return_value=mock_client_instance)
            mock_client_instance.__exit__ = Mock(return_value=False)
            mock_client_instance.post = Mock(
                side_effect=httpx.NetworkError("Connection failed")
            )
            mock_client_class.return_value = mock_client_instance

            result = sender.send("Test message")

            assert result is False

    def test_send_raises_on_unexpected_error(self) -> None:
        """Test send raises unexpected errors (e.g., encoding errors)."""
        settings = NotificationSettings(
            telegram_bot_token="test_token:123",
            telegram_chat_id="test_chat_id",
        )
        sender = TelegramSender(settings)

        client_path = (
            "ditto_platform.services.notification.channels.telegram.httpx.Client"
        )
        with patch(client_path) as mock_client_class:
            mock_client_instance = Mock()
            mock_client_instance.__enter__ = Mock(return_value=mock_client_instance)
            mock_client_instance.__exit__ = Mock(return_value=False)
            mock_client_instance.post = Mock(side_effect=ValueError("Invalid encoding"))
            mock_client_class.return_value = mock_client_instance

            with pytest.raises(ValueError, match="Invalid encoding"):
                sender.send("Test message")
