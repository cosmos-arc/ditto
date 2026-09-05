"""Compatibility exports and route-local API error mapping."""

from typing import Never

from ditto_apps.errors import (
    APIError,
    BadRequestError,
    ConflictError,
    DateRangeError,
    ForbiddenError,
    FutureDateError,
    NotFoundError,
    RateLimitError,
    UnprocessableEntityError,
)


def raise_business_error(
    exc: Exception,
    *,
    conflict_keywords: tuple[str, ...] = (),
    default_conflict: bool = False,
) -> Never:
    """
    将业务边界异常映射为 APIError 并抛出.

    Args:
        exc: 原始业务异常.
        conflict_keywords: 消息中匹配这些关键词时抛出 ConflictError.
        default_conflict: 为 True 时，兜底异常使用 ConflictError 而非 BadRequestError.

    """
    msg = str(exc)
    msg_lower = msg.lower()
    if "not found" in msg_lower:
        raise NotFoundError(msg) from exc
    if any(kw in msg_lower for kw in conflict_keywords):
        raise ConflictError(msg) from exc
    if default_conflict:
        raise ConflictError(msg) from exc
    raise BadRequestError(msg) from exc


__all__ = [
    "APIError",
    "BadRequestError",
    "ConflictError",
    "DateRangeError",
    "ForbiddenError",
    "FutureDateError",
    "NotFoundError",
    "RateLimitError",
    "UnprocessableEntityError",
    "raise_business_error",
]
