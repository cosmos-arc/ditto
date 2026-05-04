"""
Data layer exception classes.

Following design document at docs/design/02_data_design.md

Note: DataError, DittoError, IdentifierError are defined in ditto_kernel.exceptions
and imported here because Data-layer subclasses inherit from them.

Derived* errors have been moved to their canonical owner (ditto_kernel.exceptions).
Import them directly from ditto_kernel.exceptions instead of this module.
"""

# ---------------------------------------------------------------------------
# Base error classes — imported from kernel for subclassing.
# Data-layer errors inherit from DataError / IdentifierError.
# ---------------------------------------------------------------------------
from ditto_kernel.exceptions import (
    DataError,
    IdentifierError,
)

# ---------------------------------------------------------------------------
# Calendar / Identifier hierarchy
# ---------------------------------------------------------------------------


class CalendarError(DataError):
    """Calendar-related error base class."""


class InstrumentIdNotFoundError(IdentifierError):
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


class IdentifierNotFoundError(IdentifierError):
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


# NoIdentifierProvidedError and AmbiguousTickerError are now in ditto_kernel.exceptions
# and re-exported via the top-level import.


class TradingDateNotFoundError(CalendarError):
    """Trading date not found (outside calendar range)."""

    def __init__(
        self,
        message: str = "Trading date not found",
        date: str | None = None,
        direction: str | None = None,
    ) -> None:
        """
        Initialize TradingDateNotFoundError.

        Args:
            message: Error message.
            date: The date that was not found.
            direction: Direction of search ("prev" | "next").

        """
        details: dict[str, object] = {}
        if date:
            details["date"] = date
        if direction:
            details["direction"] = direction
        super().__init__(message, details if details else None)


class NotTradingDayError(CalendarError):
    """非交易日异常。"""

    def __init__(self, trade_date: str) -> None:
        self.trade_date = trade_date
        super().__init__(f"{trade_date} is not a trading day")


class DataChangedError(DataError):
    """数据已变更异常（checksum 变更，force=False 时抛出）。"""

    def __init__(
        self,
        trade_date: str,
        old_checksum: str,
        new_checksum: str,
    ) -> None:
        self.trade_date = trade_date
        self.old_checksum = old_checksum
        self.new_checksum = new_checksum
        super().__init__(
            f"Data changed for {trade_date}: checksum {old_checksum} → {new_checksum}. "
            + "Use force=True to overwrite."
        )


class LateArrivalRejectedError(DataError):
    """延迟到达数据被拒绝异常。"""

    def __init__(
        self,
        delay_days: int,
        max_delay_days: int,
        trade_date: str,
        knowledge_date: str,
    ) -> None:
        self.delay_days = delay_days
        self.max_delay_days = max_delay_days
        self.trade_date = trade_date
        self.knowledge_date = knowledge_date
        super().__init__(
            f"数据延迟到达被拒绝: trade_date={trade_date}, "
            + f"knowledge_date={knowledge_date}, "
            + f"延迟 {delay_days} 天超过阈值 {max_delay_days} 天"
        )


class ValidationError(DataError):
    """DataFrame schema validation failed."""

    pass


class DatasetNotFoundError(DataError):
    """Dataset directory or files do not exist."""

    def __init__(
        self,
        message: str = "Dataset not found",
        dataset: str | None = None,
    ) -> None:
        """
        Initialize DatasetNotFoundError.

        Args:
            message: Error message.
            dataset: The dataset name that was not found.

        """
        details: dict[str, object] = {}
        if dataset:
            details["dataset"] = dataset
        super().__init__(message, details if details else None)


class PartitionNotFoundError(DataError):
    """Year partition file does not exist."""

    def __init__(
        self,
        message: str = "Partition not found",
        dataset: str | None = None,
        year: int | None = None,
    ) -> None:
        """
        Initialize PartitionNotFoundError.

        Args:
            message: Error message.
            dataset: The dataset name.
            year: The year partition that was not found.

        """
        details: dict[str, object] = {}
        if dataset:
            details["dataset"] = dataset
        if year:
            details["year"] = year
        super().__init__(message, details if details else None)


class SchemaValidationError(ValidationError):
    """SourceSchema validation failed."""

    pass


# ---------------------------------------------------------------------------
# DataSource / Persistence error hierarchy
# ---------------------------------------------------------------------------


class DataSourceError(DataError):
    """
    数据源错误基类。

    所有与外部数据源交互相关的异常基类。

    Attributes:
        source: 数据源名称（如 "tushare", "fred"）.

    """

    def __init__(
        self,
        message: str,
        source: str,
        details: dict[str, object] | None = None,
    ) -> None:
        _details: dict[str, object] = {"source": source}
        if details:
            _details.update(details)
        super().__init__(message, _details)
        self.source = source


class NetworkError(DataSourceError):
    """
    网络错误。

    当网络超时、连接失败或传输错误时抛出。

    Attributes:
        timeout: 是否为超时错误.
        cause: 原始异常（用于链式异常追踪）.

    """

    def __init__(
        self,
        message: str,
        source: str,
        *,
        timeout: bool = False,
        cause: Exception | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        _details: dict[str, object] = {"timeout": timeout}
        if details:
            _details.update(details)
        super().__init__(message, source, _details)
        self.timeout = timeout
        self.__cause__ = cause

    @classmethod
    def from_httpx(
        cls,
        error: Exception,
        source: str,
        context: str | None = None,
    ) -> "NetworkError":
        """
        从 httpx 异常创建 NetworkError。

        Args:
            error: httpx 异常实例.
            source: 数据源名称.
            context: 额外上下文信息（如数据集名称）.

        Returns:
            NetworkError 实例.

        """
        import httpx  # noqa: PLC0415 — 仅错误处理时使用

        is_timeout = isinstance(error, httpx.TimeoutException)
        error_type = type(error).__name__
        msg = f"Network error ({error_type})"
        if context:
            msg = f"{msg} during {context}"
        msg = f"{msg}: {error}"

        return cls(
            message=msg,
            source=source,
            timeout=is_timeout,
            cause=error,
        )


class AuthError(DataSourceError):
    """
    认证错误。

    当数据源认证失败（如 API Key 无效、过期）时抛出。

    Attributes:
        auth_type: 认证类型（如 "api_key", "oauth"）.

    """

    def __init__(
        self,
        message: str,
        source: str,
        *,
        auth_type: str = "api_key",
        details: dict[str, object] | None = None,
    ) -> None:
        _details: dict[str, object] = {"auth_type": auth_type}
        if details:
            _details.update(details)
        super().__init__(message, source, _details)
        self.auth_type = auth_type


class DataValidationError(DataSourceError):
    """
    数据校验错误。

    当从数据源获取的数据不符合预期格式或约束时抛出。

    Attributes:
        dataset: 数据集名称.
        field: 校验失败的字段名（可选）.

    """

    def __init__(
        self,
        message: str,
        source: str,
        *,
        dataset: str | None = None,
        field: str | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        _details: dict[str, object] = {}
        if dataset:
            _details["dataset"] = dataset
        if field:
            _details["field"] = field
        if details:
            _details.update(details)
        super().__init__(message, source, _details)
        self.dataset = dataset
        self.field = field


class SourceFetchError(DataSourceError):
    """
    数据获取错误。

    当从数据源获取数据失败时抛出（非网络、非认证原因）。
    """

    def __init__(
        self,
        message: str,
        source: str,
        *,
        cause: Exception | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message, source, details)
        self.__cause__ = cause


class SourceConfigurationError(DataSourceError):
    """数据源配置错误（缺少环境变量、无效配置）。"""

    def __init__(
        self,
        message: str = "Source configuration error",
        *,
        env_var: str | None = None,
        config_key: str | None = None,
    ) -> None:
        details: dict[str, object] = {}
        if env_var:
            details["env_var"] = env_var
        if config_key:
            details["config_key"] = config_key
        super().__init__(message, "unknown", details if details else None)


class SourceAuthenticationError(DataSourceError):
    """数据源认证失败（无效 token、凭证）。"""

    def __init__(
        self,
        message: str = "Authentication failed",
        *,
        source: str | None = None,
    ) -> None:
        super().__init__(message, source=source or "unknown")


class SourceRateLimitError(DataSourceError):
    """数据源限流错误。"""

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        *,
        source: str | None = None,
        limit: int | None = None,
        window: int | None = None,
    ) -> None:
        details: dict[str, object] = {}
        if limit:
            details["limit"] = limit
        if window:
            details["window"] = window
        super().__init__(message, source or "unknown", details if details else None)


class SourceTransformationError(DataSourceError):
    """数据转换错误（schema 不匹配、转换失败）。"""

    def __init__(
        self,
        message: str = "Data transformation failed",
        *,
        source: str | None = None,
        dataset: str | None = None,
        expected_columns: list[str] | None = None,
        actual_columns: list[str] | None = None,
    ) -> None:
        details: dict[str, object] = {}
        if dataset:
            details["dataset"] = dataset
        if expected_columns:
            details["expected_columns"] = expected_columns
        if actual_columns:
            details["actual_columns"] = actual_columns
        super().__init__(message, source or "unknown", details if details else None)


class PersistenceError(DataError):
    """
    持久化错误基类。

    所有与数据持久化相关的异常基类。

    Attributes:
        dataset: 数据集名称（可选）.

    """

    def __init__(
        self,
        message: str,
        *,
        dataset: str | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        _details: dict[str, object] = {}
        if dataset:
            _details["dataset"] = dataset
        if details:
            _details.update(details)
        super().__init__(message, _details)
        self.dataset = dataset


class WriteError(PersistenceError):
    """
    写入错误。

    当数据写入失败时抛出。

    Attributes:
        cause: 原始异常（用于链式异常追踪）.

    """

    def __init__(
        self,
        message: str,
        *,
        dataset: str | None = None,
        cause: Exception | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message, dataset=dataset, details=details)
        self.__cause__ = cause

    @classmethod
    def from_exception(
        cls,
        error: Exception,
        dataset: str | None = None,
        context: str | None = None,
    ) -> "WriteError":
        """
        从异常创建 WriteError。

        Args:
            error: 原始异常.
            dataset: 数据集名称.
            context: 额外上下文信息.

        Returns:
            WriteError 实例.

        """
        error_type = type(error).__name__
        msg = f"Write error ({error_type})"
        if context:
            msg = f"{msg} during {context}"
        msg = f"{msg}: {error}"

        return cls(
            message=msg,
            dataset=dataset,
            cause=error,
        )


def convert_httpx_to_network_error(
    error: Exception,
    source: str,
    context: str | None = None,
) -> NetworkError:
    """
    将 httpx 异常转换为 NetworkError。

    用于在边界层统一处理 httpx 异常，避免外部异常类型外泄。

    Args:
        error: 原始异常（期望是 httpx 异常）.
        source: 数据源名称.
        context: 额外上下文信息.

    Returns:
        NetworkError 实例.

    Raises:
        ValueError: 如果 error 不是 httpx 异常.

    """
    import httpx  # noqa: PLC0415 — 仅错误处理时使用

    if not isinstance(error, (httpx.NetworkError, httpx.TimeoutException)):
        raise ValueError(
            "Expected httpx.NetworkError or httpx.TimeoutException, "
            + f"got {type(error).__name__}"
        )

    return NetworkError.from_httpx(error, source, context)


__all__ = [
    "AuthError",
    "CalendarError",
    "DataChangedError",
    "DataError",
    "DataSourceError",
    "DataValidationError",
    "DatasetNotFoundError",
    "IdentifierError",
    "IdentifierNotFoundError",
    "InstrumentIdNotFoundError",
    "LateArrivalRejectedError",
    "NetworkError",
    "NotTradingDayError",
    "PartitionNotFoundError",
    "PersistenceError",
    "SchemaValidationError",
    "SourceAuthenticationError",
    "SourceConfigurationError",
    "SourceFetchError",
    "SourceRateLimitError",
    "SourceTransformationError",
    "TradingDateNotFoundError",
    "ValidationError",
    "WriteError",
    "convert_httpx_to_network_error",
]
