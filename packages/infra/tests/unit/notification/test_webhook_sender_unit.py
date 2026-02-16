"""WebhookSender unit tests."""

from unittest.mock import Mock, patch

import httpx
import pytest
from ditto_infra.services.notification.channels.webhook import WebhookSender
from ditto_infra.services.notification.config import NotificationSettings


class TestWebhookSenderInit:
    """Tests for WebhookSender initialization."""

    def test_channel_name(self) -> None:
        """Test channel_name property."""
        settings = NotificationSettings(webhook_url="https://example.com/webhook")
        sender = WebhookSender(settings)

        assert sender.channel_name == "webhook"


class TestWebhookSenderSend:
    """Tests for WebhookSender.send method."""

    def test_send_success(self) -> None:
        """Test successful message sending."""
        settings = NotificationSettings(webhook_url="https://example.com/webhook")
        sender = WebhookSender(settings)

        client_path = "ditto_infra.services.notification.channels.webhook.httpx.Client"
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

    def test_send_returns_false_without_url(self) -> None:
        """Test send returns False when webhook URL not configured."""
        settings = NotificationSettings(webhook_url=None)
        sender = WebhookSender(settings)

        result = sender.send("Test message")

        assert result is False

    def test_send_returns_false_on_timeout(self) -> None:
        """Test send returns False on timeout exception."""
        settings = NotificationSettings(webhook_url="https://example.com/webhook")
        sender = WebhookSender(settings)

        client_path = "ditto_infra.services.notification.channels.webhook.httpx.Client"
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
        settings = NotificationSettings(webhook_url="https://example.com/webhook")
        sender = WebhookSender(settings)

        client_path = "ditto_infra.services.notification.channels.webhook.httpx.Client"
        with patch(client_path) as mock_client_class:
            mock_response = Mock()
            mock_response.status_code = 404
            error = httpx.HTTPStatusError(
                "Not Found", request=Mock(), response=mock_response
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
        settings = NotificationSettings(webhook_url="https://example.com/webhook")
        sender = WebhookSender(settings)

        client_path = "ditto_infra.services.notification.channels.webhook.httpx.Client"
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
        settings = NotificationSettings(webhook_url="https://example.com/webhook")
        sender = WebhookSender(settings)

        client_path = "ditto_infra.services.notification.channels.webhook.httpx.Client"
        with patch(client_path) as mock_client_class:
            mock_client_instance = Mock()
            mock_client_instance.__enter__ = Mock(return_value=mock_client_instance)
            mock_client_instance.__exit__ = Mock(return_value=False)
            # 模拟 httpx 内部抛出非预期的 ValueError（编码错误）
            mock_client_instance.post = Mock(
                side_effect=ValueError("Invalid header value")
            )
            mock_client_class.return_value = mock_client_instance

            # 未预期的错误应该抛出
            with pytest.raises(ValueError, match="Invalid header value"):
                sender.send("Test message")


__all__ = ["TestWebhookSenderInit", "TestWebhookSenderSend"]
