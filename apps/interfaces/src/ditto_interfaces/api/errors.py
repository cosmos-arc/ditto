"""API 层错误类."""

from ditto_interfaces.exceptions import DittoException


class APIError(DittoException):
    """
    API 错误基类.

    所有 API 层异常的基类，提供统一的错误处理接口。

    Attributes:
        message: 错误消息.
        status_code: HTTP 状态码，默认 500.
        error_code: 业务错误码，默认 'INTERNAL_ERROR'.

    """

    def __init__(
        self,
        message: str,
        status_code: int = 500,
        error_code: str = "INTERNAL_ERROR",
    ) -> None:
        super().__init__(message, error_code)
        self.status_code = status_code


class DateRangeError(APIError):
    """
    日期范围错误.

    当请求的日期范围无效时抛出（如开始日期晚于结束日期）。

    Attributes:
        start_date: 开始日期.
        end_date: 结束日期.
        status_code: HTTP 状态码，固定为 400.
        error_code: 业务错误码，固定为 'DATE_RANGE_ERROR'.

    """

    def __init__(self, start_date: str, end_date: str) -> None:
        message = (
            f"start_date ({start_date}) cannot be greater than end_date ({end_date})"
        )
        super().__init__(message, status_code=400, error_code="DATE_RANGE_ERROR")
        self.start_date = start_date
        self.end_date = end_date


class RateLimitError(APIError):
    """
    限流错误.

    当请求频率超过限制时抛出。

    Attributes:
        retry_after: 重试等待秒数.
        status_code: HTTP 状态码，固定为 429.
        error_code: 业务错误码，固定为 'RATE_LIMIT_ERROR'.

    """

    def __init__(self, retry_after: int = 60) -> None:
        message = f"Rate limit exceeded. Retry after {retry_after} seconds."
        super().__init__(message, status_code=429, error_code="RATE_LIMIT_ERROR")
        self.retry_after = retry_after
