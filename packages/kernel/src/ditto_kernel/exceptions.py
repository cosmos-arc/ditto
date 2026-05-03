"""
共享异常层级 — 跨层使用的基类异常.

提供 DittoError（全局根）、DataError（数据层基础异常）和
IdentifierError（标识符异常），供所有业务包使用。

准入依据:
- DittoError / DataError / IdentifierError 至少被 2 个业务包直接导入
- 零外部依赖，纯异常定义
- 稳定性高，不随子域迭代变更
"""

__all__ = [
    "AmbiguousTickerError",
    "DataError",
    "DerivedError",
    "DerivedNotFoundError",
    "DerivedNotImplementedError",
    "DerivedValidationError",
    "DerivedVersionError",
    "DittoError",
    "IdentifierError",
    "NoIdentifierProvidedError",
]


class DittoError(Exception):
    """
    Ditto 全局异常根.

    所有业务域异常的统一祖先，供中间件统一捕获和映射。
    """


class DataError(DittoError):
    """数据域基础异常."""

    def __init__(self, message: str, details: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.details = details or {}


class IdentifierError(DataError):
    """Identifier-related error base class."""


class NoIdentifierProvidedError(IdentifierError):
    """
    未提供任何标识符异常.

    当 resolve_instrument_identifier() 未收到任何有效标识符时抛出.
    """


def _format_match(m: dict[str, object]) -> str:
    """格式化单条匹配记录为可读字符串."""
    return (
        f"{m.get('source_ticker', '')} (ID: {m.get('instrument_id', '')}, "
        f"名称: {m.get('name', '')})"
    )


class AmbiguousTickerError(IdentifierError):
    """
    Ticker 不唯一异常.

    当裸代码（如 "000001"）匹配多个标的时抛出.
    """

    def __init__(self, ticker: str, matches: list[dict[str, object]]) -> None:
        self.ticker = ticker
        self.matches = matches

        match_list = "\n  - ".join(_format_match(m) for m in matches)
        message = (
            f"Ticker '{ticker}' 存在歧义, "
            f"匹配到 {len(matches)} 个标的:\n  - {match_list}"
        )
        details: dict[str, object] = {"ticker": ticker, "matches": matches}
        super().__init__(message, details)


# ---------------------------------------------------------------------------
# Derived* error hierarchy — shared by data and features packages.
# Both packages raise these without creating circular dependencies.
# ---------------------------------------------------------------------------


class DerivedError(DittoError):
    """衍生数据域基础异常."""

    def __init__(self, message: str, *, derived_id: str | None = None) -> None:
        self.derived_id = derived_id
        super().__init__(message)


class DerivedNotFoundError(DerivedError):
    """Raised when a derived entity is not found."""

    def __init__(self, *, derived_id: str, version: int | None = None) -> None:
        self.version = version
        msg = f"Derived not found: derived_id={derived_id}"
        if version is not None:
            msg += f" version={version}"
        super().__init__(msg, derived_id=derived_id)


class DerivedVersionError(DerivedError):
    """Raised when version resolution fails."""

    def __init__(self, *, derived_id: str, reason: str) -> None:
        self.reason = reason
        super().__init__(
            f"Version resolution failed for derived_id={derived_id}: {reason}",
            derived_id=derived_id,
        )


class DerivedNotImplementedError(DerivedError):
    """Raised when a feature is not yet implemented."""

    def __init__(self, *, feature: str, derived_id: str | None = None) -> None:
        self.feature = feature
        super().__init__(
            f"Feature not implemented: {feature}",
            derived_id=derived_id,
        )


class DerivedValidationError(DerivedError):
    """Raised when validation fails."""

    def __init__(
        self,
        message: str | None = None,
        *,
        derived_id: str | None = None,
        field: str | None = None,
        value: str | None = None,
        reason: str | None = None,
    ) -> None:
        self.field = field
        self.value = value
        self.reason = reason
        if message is not None:
            super().__init__(message, derived_id=derived_id)
        elif field is not None and value is not None and reason is not None:
            super().__init__(
                f"Validation failed for field={field} value={value}: {reason}",
                derived_id=derived_id,
            )
        else:
            raise TypeError(
                (
                    "DerivedValidationError requires either a positional message "
                    "or all of field, value, reason keyword arguments"
                ),
            )
