"""TelegramSender unit tests."""

from unittest.mock import Mock, patch

import httpx
import pytest
from ditto_platform.services.notification.channels.telegram import TelegramSender
from ditto_platform.services.notification.config import NotificationSettings
from loguru import logger


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

    def test_send_returns_false_on_generic_exception(self) -> None:
        """Generic failures are contained at the notification boundary."""
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

            assert sender.send("Test message") is False

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

    def test_http_status_log_contains_only_stable_non_secret_error_facts(
        self,
    ) -> None:
        """HTTP failures must never serialize the bot token or sensitive URL."""
        bot_token = "secret-token:123456"
        settings = NotificationSettings(
            telegram_bot_token=bot_token,
            telegram_chat_id="test_chat_id",
        )
        sender = TelegramSender(settings)
        sensitive_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        request = httpx.Request("POST", sensitive_url)
        response = httpx.Response(403, request=request)
        error = httpx.HTTPStatusError(
            "Forbidden",
            request=request,
            response=response,
        )
        records: list[dict[str, object]] = []
        sink_id = logger.add(
            lambda message: records.append(message.record),
            level="ERROR",
        )

        client_path = (
            "ditto_platform.services.notification.channels.telegram.httpx.Client"
        )
        try:
            with patch(client_path) as mock_client_class:
                mock_client_instance = Mock()
                mock_client_instance.__enter__ = Mock(return_value=mock_client_instance)
                mock_client_instance.__exit__ = Mock(return_value=False)
                mock_client_instance.post = Mock(side_effect=error)
                mock_client_class.return_value = mock_client_instance

                assert sender.send("Test message") is False
        finally:
            logger.remove(sink_id)

        serialized_records = repr(records)
        assert bot_token not in serialized_records
        assert sensitive_url not in serialized_records
        assert records
        extra = records[-1]["extra"]
        assert isinstance(extra, dict)
        assert extra == {
            "event": "telegram_http_error",
            "error_code": "TELEGRAM_HTTP_STATUS",
            "status_code": 403,
        }

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

    @pytest.mark.parametrize(
        ("exception_factory", "event", "error_code"),
        [
            (
                lambda request, url: httpx.TimeoutException(
                    f"timeout calling {url}",
                    request=request,
                ),
                "telegram_timeout",
                "TELEGRAM_TIMEOUT",
            ),
            (
                lambda request, url: httpx.NetworkError(
                    f"network failure calling {url}",
                    request=request,
                ),
                "telegram_network_error",
                "TELEGRAM_NETWORK_ERROR",
            ),
        ],
    )
    def test_transport_error_logs_never_contain_sensitive_request_url(
        self,
        exception_factory: object,
        event: str,
        error_code: str,
    ) -> None:
        """Transport exceptions can carry the request URL and must be sanitized."""
        bot_token = "transport-secret:987654"
        settings = NotificationSettings(
            telegram_bot_token=bot_token,
            telegram_chat_id="test_chat_id",
        )
        sender = TelegramSender(settings)
        sensitive_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        request = httpx.Request("POST", sensitive_url)
        factory = exception_factory
        assert callable(factory)
        error = factory(request, sensitive_url)
        records: list[dict[str, object]] = []
        sink_id = logger.add(
            lambda message: records.append(message.record),
            level="WARNING",
        )

        client_path = (
            "ditto_platform.services.notification.channels.telegram.httpx.Client"
        )
        try:
            with patch(client_path) as mock_client_class:
                mock_client_instance = Mock()
                mock_client_instance.__enter__ = Mock(return_value=mock_client_instance)
                mock_client_instance.__exit__ = Mock(return_value=False)
                mock_client_instance.post = Mock(side_effect=error)
                mock_client_class.return_value = mock_client_instance

                assert sender.send("Test message") is False
        finally:
            logger.remove(sink_id)

        serialized_records = repr(records)
        assert bot_token not in serialized_records
        assert sensitive_url not in serialized_records
        assert records
        extra = records[-1]["extra"]
        assert isinstance(extra, dict)
        assert extra == {"event": event, "error_code": error_code}

    def test_send_returns_false_on_unexpected_error(self) -> None:
        """Unexpected errors (for example encoding errors) are contained."""
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

            assert sender.send("Test message") is False

    def test_unexpected_error_log_does_not_duplicate_sensitive_exception_text(
        self,
    ) -> None:
        """Unexpected errors are contained and logging remains secret-safe."""
        bot_token = "unexpected-secret:24680"
        settings = NotificationSettings(
            telegram_bot_token=bot_token,
            telegram_chat_id="test_chat_id",
        )
        sender = TelegramSender(settings)
        sensitive_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        records: list[dict[str, object]] = []
        sink_id = logger.add(
            lambda message: records.append(message.record),
            level="ERROR",
        )

        client_path = (
            "ditto_platform.services.notification.channels.telegram.httpx.Client"
        )
        try:
            with patch(client_path) as mock_client_class:
                mock_client_instance = Mock()
                mock_client_instance.__enter__ = Mock(return_value=mock_client_instance)
                mock_client_instance.__exit__ = Mock(return_value=False)
                mock_client_instance.post = Mock(
                    side_effect=RuntimeError(f"unexpected request to {sensitive_url}")
                )
                mock_client_class.return_value = mock_client_instance

                assert sender.send("Test message") is False
        finally:
            logger.remove(sink_id)

        serialized_records = repr(records)
        assert bot_token not in serialized_records
        assert sensitive_url not in serialized_records
        assert records
        extra = records[-1]["extra"]
        assert isinstance(extra, dict)
        assert extra == {
            "event": "telegram_unexpected_error",
            "error_code": "TELEGRAM_UNEXPECTED_ERROR",
            "error_type": "RuntimeError",
        }
