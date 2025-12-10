"""Tests for logging configuration."""

import json
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest

from ditto_foundation.logging_config import (
    LogConfig,
    StructuredLogger,
    setup_logging,
    get_logger,
    RequestLogger,
    BusinessLogger,
    LogLevelContext,
    request_logger,
    business_logger,
)


class TestLogConfig:
    """Test LogConfig model."""

    def test_default_config(self) -> None:
        """Test default configuration values."""
        config = LogConfig()
        assert config.level == "INFO"
        assert config.enable_console is True
        assert config.enable_file is True
        assert config.json_format is False
        assert config.rotation == "1 day"
        assert config.retention == "30 days"
        assert config.compression == "gz"

    def test_custom_config(self) -> None:
        """Test custom configuration values."""
        config = LogConfig(
            level="DEBUG",
            enable_console=False,
            json_format=True
        )
        assert config.level == "DEBUG"
        assert config.enable_console is False
        assert config.json_format is True


class TestStructuredLogger:
    """Test StructuredLogger class."""

    def test_init(self) -> None:
        """Test logger initialization."""
        logger = StructuredLogger("test_module")
        assert logger.name == "test_module"

    @patch("ditto_foundation.logging_config.logger")
    def test_info_without_kwargs(self, mock_logger: Mock) -> None:
        """Test info logging without additional data."""
        logger = StructuredLogger("test")
        logger.info("Test message")
        mock_logger.info.assert_called_once_with("Test message")

    @patch("ditto_foundation.logging_config.logger")
    def test_info_with_kwargs(self, mock_logger: Mock) -> None:
        """Test info logging with additional data."""
        logger = StructuredLogger("test")
        logger.info("Test message", key1="value1", key2=123)
        expected = "Test message | {\"key1\": \"value1\", \"key2\": 123}"
        mock_logger.info.assert_called_once_with(expected)

    @patch("ditto_foundation.logging_config.logger")
    def test_error_without_kwargs(self, mock_logger: Mock) -> None:
        """Test error logging without additional data."""
        logger = StructuredLogger("test")
        logger.error("Error message")
        mock_logger.error.assert_called_once_with("Error message")

    @patch("ditto_foundation.logging_config.logger")
    def test_error_with_kwargs(self, mock_logger: Mock) -> None:
        """Test error logging with additional data."""
        logger = StructuredLogger("test")
        logger.error("Error message", code=500, detail="Server error")
        expected = "Error message | {\"code\": 500, \"detail\": \"Server error\"}"
        mock_logger.error.assert_called_once_with(expected)

    @patch("ditto_foundation.logging_config.logger")
    def test_warning_with_kwargs(self, mock_logger: Mock) -> None:
        """Test warning logging with additional data."""
        logger = StructuredLogger("test")
        logger.warning("Warning message", user_id=123)
        expected = "Warning message | {\"user_id\": 123}"
        mock_logger.warning.assert_called_once_with(expected)

    @patch("ditto_foundation.logging_config.logger")
    def test_debug_with_kwargs(self, mock_logger: Mock) -> None:
        """Test debug logging with additional data."""
        logger = StructuredLogger("test")
        logger.debug("Debug message", step=1, total=10)
        expected = "Debug message | {\"step\": 1, \"total\": 10}"
        mock_logger.debug.assert_called_once_with(expected)

    @patch("ditto_foundation.logging_config.logger")
    def test_exception_with_kwargs(self, mock_logger: Mock) -> None:
        """Test exception logging with additional data."""
        logger = StructuredLogger("test")
        logger.exception("Exception occurred", error_type="ValueError")
        expected = "Exception occurred | {\"error_type\": \"ValueError\"}"
        mock_logger.exception.assert_called_once_with(expected)

    @patch("ditto_foundation.logging_config.logger")
    def test_bind(self, mock_logger: Mock) -> None:
        """Test bind method."""
        logger = StructuredLogger("test")
        logger.bind(request_id="123", user_id="456")
        mock_logger.bind.assert_called_once_with(request_id="123", user_id="456")


class TestSetupLogging:
    """Test setup_logging function."""

    @patch("ditto_foundation.logging_config.logger")
    @patch("ditto_foundation.logging_config.Path")
    def test_setup_with_default_config(self, mock_path: Mock, mock_logger: Mock) -> None:
        """Test setup with default configuration."""
        mock_log_dir = Mock()
        mock_path.return_value = mock_log_dir

        setup_logging()

        # Should remove default logger
        mock_logger.remove.assert_called_once()

        # Should create log directory
        mock_log_dir.mkdir.assert_called_once_with(parents=True, exist_ok=True)

    @patch("ditto_foundation.logging_config.logger")
    @patch("ditto_foundation.logging_config.Path")
    def test_setup_without_console(self, mock_path: Mock, mock_logger: Mock) -> None:
        """Test setup with console disabled."""
        mock_log_dir = Mock()
        mock_path.return_value = mock_log_dir

        config = LogConfig(enable_console=False)
        setup_logging(config)

        # Should not add console handler
        for call in mock_logger.add.call_args_list:
            args, kwargs = call
            assert args[0] != sys.stdout

    @patch("ditto_foundation.logging_config.logger")
    @patch("ditto_foundation.logging_config.Path")
    def test_setup_without_file(self, mock_path: Mock, mock_logger: Mock) -> None:
        """Test setup with file disabled."""
        mock_log_dir = Mock()
        mock_path.return_value = mock_log_dir

        config = LogConfig(enable_file=False)
        setup_logging(config)

        # Should only add console handler
        assert mock_logger.add.call_count == 1

    @patch("ditto_foundation.logging_config.logger")
    @patch("ditto_foundation.logging_config.Path")
    def test_setup_production_env(self, mock_path: Mock, mock_logger: Mock) -> None:
        """Test setup for production environment."""
        mock_log_dir = Mock()
        mock_path.return_value = mock_log_dir

        setup_logging(env="production")

        # Check console format for production
        console_calls = [
            call for call in mock_logger.add.call_args_list
            if call[0][0] == sys.stdout
        ]
        assert len(console_calls) == 1
        format_arg = console_calls[0][1]["format"]
        assert "{time:YYYY-MM-DD HH:mm:ss}" in format_arg
        assert console_calls[0][1]["colorize"] is False

    @patch("ditto_foundation.logging_config.logger")
    @patch("ditto_foundation.logging_config.Path")
    def test_setup_testing_env(self, mock_path: Mock, mock_logger: Mock) -> None:
        """Test setup for testing environment."""
        mock_log_dir = Mock()
        mock_path.return_value = mock_log_dir

        setup_logging(env="testing")

        # Should remove all handlers and add only warning level
        assert mock_logger.remove.call_count == 2  # Once at start, once for testing
        warning_calls = [
            call for call in mock_logger.add.call_args_list
            if call[1].get("level") == "WARNING"
        ]
        assert len(warning_calls) == 1

    @patch("ditto_foundation.logging_config.logger")
    @patch("ditto_foundation.logging_config.Path")
    def test_setup_with_json_format(self, mock_path: Mock, mock_logger: Mock) -> None:
        """Test setup with JSON format enabled."""
        mock_log_dir = Mock()
        mock_log_dir.__truediv__ = Mock(return_value=Path("test.log"))
        mock_path.return_value = mock_log_dir

        config = LogConfig(json_format=True)
        setup_logging(config)

        # Check that serialize=True is set for JSON format
        file_calls = [
            call for call in mock_logger.add.call_args_list
            if call[0][0] != sys.stdout
        ]
        # Should find a call with serialize=True
        assert any(call[1].get("serialize") is True for call in file_calls)

    @patch("ditto_foundation.logging_config.logger")
    @patch("ditto_foundation.logging_config.Path")
    def test_setup_custom_log_dir(self, mock_path: Mock, mock_logger: Mock) -> None:
        """Test setup with custom log directory."""
        custom_dir = Path("/custom/logs")
        custom_dir.mkdir = Mock()

        setup_logging(log_dir=custom_dir)

        # Should use custom directory
        custom_dir.mkdir.assert_called_once_with(parents=True, exist_ok=True)


class TestGetLogger:
    """Test get_logger function."""

    def test_get_logger(self) -> None:
        """Test getting a structured logger."""
        logger = get_logger("test_module")
        assert isinstance(logger, StructuredLogger)
        assert logger.name == "test_module"


class TestRequestLogger:
    """Test RequestLogger class."""

    @patch("ditto_foundation.logging_config.logger")
    def test_log_request(self, mock_logger: Mock) -> None:
        """Test logging a request."""
        logger = RequestLogger()
        logger.log_request(
            method="GET",
            path="/api/test",
            headers={"Authorization": "Bearer token"},
            query_params={"page": 1},
            request_id="123"
        )

        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args[0][0]
        assert "GET /api/test" in call_args

        # Check additional data
        log_data = mock_logger.info.call_args[1]
        assert log_data["event"] == "request"
        assert log_data["method"] == "GET"
        assert log_data["path"] == "/api/test"
        assert log_data["request_id"] == "123"

    @patch("ditto_foundation.logging_config.logger")
    def test_log_response_success(self, mock_logger: Mock) -> None:
        """Test logging a successful response."""
        logger = RequestLogger()
        logger.log_response(
            method="GET",
            path="/api/test",
            status_code=200,
            duration_ms=150.5,
            request_id="123"
        )

        mock_logger.info.assert_called_once()
        log_data = mock_logger.info.call_args[1]
        assert log_data["event"] == "response"
        assert log_data["status_code"] == 200
        assert log_data["duration_ms"] == 150.5

    @patch("ditto_foundation.logging_config.logger")
    def test_log_response_warning(self, mock_logger: Mock) -> None:
        """Test logging a warning response."""
        logger = RequestLogger()
        logger.log_response(
            method="POST",
            path="/api/test",
            status_code=400,
            duration_ms=50.0
        )

        mock_logger.warning.assert_called_once()
        log_data = mock_logger.warning.call_args[1]
        assert log_data["status_code"] == 400

    @patch("ditto_foundation.logging_config.logger")
    def test_log_response_error(self, mock_logger: Mock) -> None:
        """Test logging an error response."""
        logger = RequestLogger()
        logger.log_response(
            method="DELETE",
            path="/api/test",
            status_code=500,
            duration_ms=100.0
        )

        mock_logger.error.assert_called_once()
        log_data = mock_logger.error.call_args[1]
        assert log_data["status_code"] == 500

    @patch("ditto_foundation.logging_config.logger")
    def test_log_error(self, mock_logger: Mock) -> None:
        """Test logging an error."""
        logger = RequestLogger()
        error = ValueError("Test error")
        logger.log_error(
            method="GET",
            path="/api/test",
            error=error,
            request_id="456"
        )

        mock_logger.error.assert_called_once()
        call_args = mock_logger.error.call_args[0][0]
        assert "GET /api/test" in call_args
        assert "ValueError: Test error" in call_args

        log_data = mock_logger.error.call_args[1]
        assert log_data["event"] == "error"
        assert log_data["error_type"] == "ValueError"
        assert log_data["error_message"] == "Test error"
        assert log_data["request_id"] == "456"


class TestBusinessLogger:
    """Test BusinessLogger class."""

    @patch("ditto_foundation.logging_config.logger")
    def test_log_trade(self, mock_logger: Mock) -> None:
        """Test logging a trade."""
        logger = BusinessLogger()
        logger.log_trade(
            strategy="Rotation",
            symbol="510300",
            action="BUY",
            quantity=1000,
            price=3.5,
            order_id="ord123"
        )

        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args[0][0]
        assert "Trade: BUY 1000 510300 @ 3.5" in call_args

        log_data = mock_logger.info.call_args[1]
        assert log_data["event"] == "trade"
        assert log_data["strategy"] == "Rotation"
        assert log_data["symbol"] == "510300"
        assert log_data["action"] == "BUY"
        assert log_data["quantity"] == 1000
        assert log_data["price"] == 3.5
        assert log_data["order_id"] == "ord123"

    @patch("ditto_foundation.logging_config.logger")
    def test_log_signal(self, mock_logger: Mock) -> None:
        """Test logging a signal."""
        logger = BusinessLogger()
        logger.log_signal(
            strategy="Rotation",
            symbol="510300",
            signal_type="STRONG_BUY",
            confidence=0.85,
            factors={"rs": 1.5, "value": 0.8}
        )

        mock_logger.info.assert_called_once()
        log_data = mock_logger.info.call_args[1]
        assert log_data["event"] == "signal"
        assert log_data["signal_type"] == "STRONG_BUY"
        assert log_data["confidence"] == 0.85
        assert log_data["factors"] == {"rs": 1.5, "value": 0.8}

    @patch("ditto_foundation.logging_config.logger")
    def test_log_data_update_success(self, mock_logger: Mock) -> None:
        """Test logging a successful data update."""
        logger = BusinessLogger()
        logger.log_data_update(
            source="tushare",
            symbol="510300",
            update_type="daily",
            records=250,
            success=True
        )

        mock_logger.info.assert_called_once()
        log_data = mock_logger.info.call_args[1]
        assert log_data["event"] == "data_update"
        assert log_data["source"] == "tushare"
        assert log_data["records"] == 250
        assert log_data["success"] is True

    @patch("ditto_foundation.logging_config.logger")
    def test_log_data_update_failure(self, mock_logger: Mock) -> None:
        """Test logging a failed data update."""
        logger = BusinessLogger()
        logger.log_data_update(
            source="akshare",
            symbol="159919",
            update_type="realtime",
            records=0,
            success=False
        )

        mock_logger.error.assert_called_once()
        log_data = mock_logger.error.call_args[1]
        assert log_data["success"] is False
        assert "(failed)" in mock_logger.error.call_args[0][0]


class TestLogLevelContext:
    """Test LogLevelContext class."""

    def test_init(self) -> None:
        """Test context manager initialization."""
        context = LogLevelContext("DEBUG", "test_logger")
        assert context.level == "DEBUG"
        assert context.logger_name == "test_logger"
        assert context.original_level is None

    def test_enter(self) -> None:
        """Test entering context."""
        context = LogLevelContext("INFO")
        result = context.__enter__()
        assert result is context

    def test_exit(self) -> None:
        """Test exiting context."""
        context = LogLevelContext("INFO")
        # Should not raise any errors
        context.__exit__(None, None, None)

    def test_context_manager_usage(self) -> None:
        """Test context manager in with statement."""
        context = LogLevelContext("DEBUG")
        with context:
            # Context is active
            pass
        # Context is exited


class TestGlobalLoggers:
    """Test global logger instances."""

    def test_request_logger_global(self) -> None:
        """Test global request logger instance."""
        assert isinstance(request_logger, RequestLogger)

    def test_business_logger_global(self) -> None:
        """Test global business logger instance."""
        assert isinstance(business_logger, BusinessLogger)
