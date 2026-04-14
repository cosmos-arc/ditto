"""API 层错误类."""

from __future__ import annotations

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


class NotFoundError(APIError):
    """
    资源不存在错误.

    当请求的资源在系统中不存在时抛出（如策略、Universe、回测记录等）。

    Attributes:
        status_code: HTTP 状态码，固定为 404.
        error_code: 业务错误码，固定为 'NOT_FOUND'.

    """

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=404, error_code="NOT_FOUND")


class ConflictError(APIError):
    """
    状态冲突错误.

    当操作与资源当前状态冲突时抛出（如取消已完成的运行、版本冲突等）。

    Attributes:
        status_code: HTTP 状态码，固定为 409.
        error_code: 业务错误码，固定为 'CONFLICT'.

    """

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=409, error_code="CONFLICT")


class ForbiddenError(APIError):
    """
    禁止操作错误.

    当操作被系统规则禁止时抛出（如修改预设 Universe 等受保护资源）。

    Attributes:
        status_code: HTTP 状态码，固定为 403.
        error_code: 业务错误码，固定为 'FORBIDDEN'.

    """

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=403, error_code="FORBIDDEN")


class BadRequestError(APIError):
    """
    参数错误.

    当请求参数不合法或违反业务规则时抛出。

    Attributes:
        status_code: HTTP 状态码，固定为 400.
        error_code: 业务错误码，固定为 'BAD_REQUEST'.

    """

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=400, error_code="BAD_REQUEST")
