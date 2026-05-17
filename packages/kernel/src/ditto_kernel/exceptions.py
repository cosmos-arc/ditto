"""
共享异常层级 — 跨层使用的基类异常.

提供 DittoError（全局根）、DataError（数据层基础异常）和
IdentifierError（标识符异常），供所有业务包使用。

准入依据:
- DittoError / DataError / IdentifierError 至少被 2 个业务包直接导入
- 零外部依赖，纯异常定义
- 稳定性高，不随子域迭代变更
"""

from collections.abc import Mapping

__all__ = [
    "AmbiguousTickerError",
    "DataError",
    "DittoError",
    "IdentifierError",
    "NoIdentifierProvidedError",
]


class DittoError(Exception):
    """
    Ditto 全局异常根.

    所有业务域异常的统一祖先，供中间件统一捕获和映射。
    """

    def __init__(
        self,
        message: str,
        details: Mapping[str, object] | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(message)
        self.details: dict[str, object] = dict(details or {})
        self.details.update(kwargs)


class DataError(DittoError):
    """数据域基础异常."""


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
