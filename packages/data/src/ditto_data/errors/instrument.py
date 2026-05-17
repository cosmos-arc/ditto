"""Instrument and identifier-related error classes."""

from ditto_kernel.exceptions import IdentifierError as _IdentifierError


class InstrumentIdNotFoundError(_IdentifierError):
    """证券标识符（Instrument ID）未找到。"""

    def __init__(
        self,
        message: str = "Instrument ID not found",
        identifier: str | None = None,
        source: str | None = None,
    ) -> None:
        """
        Initialize InstrumentIdNotFoundError.

        Args:
            message: Error message.
            identifier: The identifier that was not found.
            source: Data source identifier.

        """
        details: dict[str, object] = {}
        if identifier:
            details["identifier"] = identifier
        if source:
            details["source"] = source
        super().__init__(message, details if details else None)


class IdentifierNotFoundError(_IdentifierError):
    """
    标识符未找到异常.

    当 ticker、standard_ticker 或 instrument_id 在系统中不存在时抛出.
    """

    def __init__(
        self,
        identifier: str,
        identifier_type: str,
        message: str | None = None,
    ) -> None:
        """
        初始化 IdentifierNotFoundError.

        Args:
            identifier: 标识符值
            identifier_type: 标识符类型（ticker, standard_ticker, instrument_id）
            message: 自定义错误消息

        """
        self.identifier = identifier
        self.identifier_type = identifier_type
        if message is None:
            message = f"未找到 {identifier_type}: '{identifier}'"
        details: dict[str, object] = {
            "identifier": identifier,
            "identifier_type": identifier_type,
        }
        super().__init__(message, details)
