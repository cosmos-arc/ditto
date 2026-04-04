"""Tests for API error classes."""

import pytest


@pytest.mark.unit
class TestAPIError:
    """测试 APIError 基类."""

    def test_default_values(self) -> None:
        """验证默认值: status_code=500, code='INTERNAL_ERROR'."""
        from ditto_interfaces.api.errors import APIError

        error = APIError("Something went wrong")

        assert error.message == "Something went wrong"
        assert error.status_code == 500
        assert error.error_code == "INTERNAL_ERROR"

    def test_custom_message(self) -> None:
        """验证自定义消息."""
        from ditto_interfaces.api.errors import APIError

        error = APIError("Custom error message")

        assert error.message == "Custom error message"
        assert str(error) == "Custom error message"

    def test_custom_status_code(self) -> None:
        """验证自定义状态码."""
        from ditto_interfaces.api.errors import APIError

        error = APIError("Not found", status_code=404)

        assert error.status_code == 404
        assert error.error_code == "INTERNAL_ERROR"

    def test_custom_error_code(self) -> None:
        """验证自定义错误码."""
        from ditto_interfaces.api.errors import APIError

        error = APIError("Bad request", error_code="BAD_REQUEST")

        assert error.status_code == 500
        assert error.error_code == "BAD_REQUEST"

    def test_all_custom_values(self) -> None:
        """验证所有自定义值."""
        from ditto_interfaces.api.errors import APIError

        error = APIError(
            message="Service unavailable",
            status_code=503,
            error_code="SERVICE_UNAVAILABLE",
        )

        assert error.message == "Service unavailable"
        assert error.status_code == 503
        assert error.error_code == "SERVICE_UNAVAILABLE"

    def test_inherits_from_ditto_exception(self) -> None:
        """验证继承自 DittoException."""
        from ditto_interfaces.api.errors import APIError
        from ditto_interfaces.exceptions import DittoException

        error = APIError("test")
        assert isinstance(error, DittoException)
        assert isinstance(error, Exception)


@pytest.mark.unit
class TestDateRangeError:
    """测试 DateRangeError 日期范围错误."""

    def test_error_properties(self) -> None:
        """验证错误属性: status_code=400, error_code='DATE_RANGE_ERROR'."""
        from ditto_interfaces.api.errors import DateRangeError

        error = DateRangeError(
            start_date="2024-12-01",
            end_date="2024-01-01",
        )

        assert error.status_code == 400
        assert error.error_code == "DATE_RANGE_ERROR"
        assert "2024-12-01" in error.message
        assert "2024-01-01" in error.message
        assert error.start_date == "2024-12-01"
        assert error.end_date == "2024-01-01"

    def test_message_format(self) -> None:
        """验证消息格式."""
        from ditto_interfaces.api.errors import DateRangeError

        error = DateRangeError(
            start_date="2025-01-01",
            end_date="2024-01-01",
        )

        expected_msg = (
            "start_date (2025-01-01) cannot be greater than end_date (2024-01-01)"
        )
        assert expected_msg in error.message

    def test_inherits_from_api_error(self) -> None:
        """验证继承自 APIError."""
        from ditto_interfaces.api.errors import APIError, DateRangeError

        error = DateRangeError(start_date="2024-12-01", end_date="2024-01-01")
        assert isinstance(error, APIError)


@pytest.mark.unit
class TestRateLimitError:
    """测试 RateLimitError 限流错误."""

    def test_error_properties(self) -> None:
        """验证错误属性: status_code=429, error_code='RATE_LIMIT_ERROR'."""
        from ditto_interfaces.api.errors import RateLimitError

        error = RateLimitError(retry_after=60)

        assert error.status_code == 429
        assert error.error_code == "RATE_LIMIT_ERROR"
        assert error.retry_after == 60
        assert "60" in error.message

    def test_default_retry_after(self) -> None:
        """验证默认 retry_after=60."""
        from ditto_interfaces.api.errors import RateLimitError

        error = RateLimitError()

        assert error.retry_after == 60
        assert "60" in error.message

    def test_custom_retry_after(self) -> None:
        """验证自定义 retry_after."""
        from ditto_interfaces.api.errors import RateLimitError

        error = RateLimitError(retry_after=120)

        assert error.retry_after == 120
        assert "120" in error.message
        assert "Rate limit exceeded. Retry after 120 seconds." in error.message

    def test_inherits_from_api_error(self) -> None:
        """验证继承自 APIError."""
        from ditto_interfaces.api.errors import APIError, RateLimitError

        error = RateLimitError(retry_after=30)
        assert isinstance(error, APIError)
