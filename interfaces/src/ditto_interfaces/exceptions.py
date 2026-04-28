"""Interfaces 层自定义异常."""

from __future__ import annotations

from ditto_kernel.exceptions import DittoError

__all__ = ["RouteValidationError"]


class RouteValidationError(DittoError):
    """路由数据验证异常."""

    def __init__(self, field: str, value: str, constraint: str) -> None:
        self.field = field
        self.value = value
        self.constraint = constraint
        self.error_code: str = "VALIDATION_ERROR"
        super().__init__(f"Validation failed for {field}='{value}': {constraint}")
