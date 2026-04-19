"""自定义异常类."""

from __future__ import annotations

from ditto_kernel.exceptions import DittoError


class DittoException(DittoError):
    """Ditto系统基础异常类."""

    def __init__(self, message: str, error_code: str | None = None) -> None:
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class DataNotFoundError(DittoException):
    """数据未找到异常."""

    def __init__(self, resource: str, identifier: str) -> None:
        super().__init__(
            f"{resource} not found: {identifier}", error_code="DATA_NOT_FOUND"
        )
        self.resource = resource
        self.identifier = identifier


class InvalidDateError(DittoException):
    """无效日期异常."""

    def __init__(self, date_str: str, format_hint: str = "YYYY-MM-DD") -> None:
        super().__init__(
            f"Invalid date format: {date_str}. Expected format: {format_hint}",
            error_code="INVALID_DATE_FORMAT",
        )
        self.date_str = date_str
        self.format_hint = format_hint


class DatabaseError(DittoException):
    """数据库操作异常."""

    def __init__(self, operation: str, detail: str) -> None:
        super().__init__(
            f"Database operation failed: {operation}. Detail: {detail}",
            error_code="DATABASE_ERROR",
        )
        self.operation = operation
        self.detail = detail


class RouteValidationError(DittoException):
    """路由数据验证异常."""

    def __init__(self, field: str, value: str, constraint: str) -> None:
        super().__init__(
            f"Validation failed for {field}='{value}': {constraint}",
            error_code="VALIDATION_ERROR",
        )
        self.field = field
        self.value = value
        self.constraint = constraint


class ExternalServiceError(DittoException):
    """外部服务异常."""

    def __init__(self, service: str, detail: str) -> None:
        super().__init__(
            f"External service {service} error: {detail}",
            error_code="EXTERNAL_SERVICE_ERROR",
        )
        self.service = service
        self.detail = detail
