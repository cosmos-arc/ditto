"""
共享异常层级 — 跨层使用的基类异常.

提供 DataError（数据层基础异常）和 IdentifierError（标识符异常），
供 ditto_data、ditto_app、ditto_interfaces 等多层使用。

准入依据:
- DataError / IdentifierError 至少被 3 个业务包直接导入
- 零外部依赖，纯异常定义
- 稳定性高，不随子域迭代变更
"""

__all__ = [
    "AmbiguousTickerError",
    "DataError",
    "IdentifierError",
    "NoIdentifierProvidedError",
]


class DataError(Exception):
    """Data base exception."""

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


class AmbiguousTickerError(IdentifierError):
    """
    Ticker 不唯一异常.

    当裸代码（如 "000001"）匹配多个标的时抛出.
    """

    def __init__(self, ticker: str, matches: list[dict[str, object]]) -> None:
        self.ticker = ticker
        self.matches = matches

        def format_match(m: dict[str, object]) -> str:
            return (
                f"{m.get('source_ticker', '')} (ID: {m.get('instrument_id', '')}, "
                f"名称: {m.get('name', '')})"
            )

        match_list = "\n  - ".join(format_match(m) for m in matches)
        message = (
            f"Ticker '{ticker}' 存在歧义, "
            f"匹配到 {len(matches)} 个标的:\n  - {match_list}"
        )
        details: dict[str, object] = {"ticker": ticker, "matches": matches}
        super().__init__(message, details)
