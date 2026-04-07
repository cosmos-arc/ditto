"""
Data layer exception classes.

Following design document at docs/design/02_data_design.md
"""

import httpx

# ---------------------------------------------------------------------------
# Derived* error hierarchy — canonical definition (Data layer owns these
# because Data services raise them without depending on Core).
# Core re-exports from here via ditto_engine.errors.
# ---------------------------------------------------------------------------


class DerivedError(Exception):
    """Base exception for all derived-related errors."""

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


class DerivedMaterializationError(DerivedError):
    """Raised when materialization fails."""

    def __init__(self, *, derived_id: str, version: int, reason: str) -> None:
        self.version = version
        self.reason = reason
        super().__init__(
            f"Materialization failed for derived_id={derived_id} "
            + f"version={version}: {reason}",
            derived_id=derived_id,
        )


class DerivedDependencyError(DerivedError):
    """Raised when a dependency is missing or invalid."""

    def __init__(
        self, *, derived_id: str, missing: list[str], available: list[str]
    ) -> None:
        self.missing = missing
        self.available = available
        super().__init__(
            f"Missing dependencies for derived_id={derived_id}: "
            + f"{missing}. Available: {available}",
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


class DataError(Exception):
    """Data base exception."""

    def __init__(self, message: str, details: dict[str, object] | None = None) -> None:
        """
        Initialize Data error.

        Args:
            message: Error message.
            details: Additional error details.

        """
        super().__init__(message)
        self.details = details or {}


class CalendarError(DataError):
    """Calendar-related error base class."""

    pass


class IdentifierError(DataError):
    """Identifier-related error base class."""

    pass


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


class NoIdentifierProvidedError(IdentifierError):
    """
    未提供任何标识符异常.

    当 resolve_instrument_identifier() 未收到任何有效标识符时抛出.
    """

    pass


class AmbiguousTickerError(IdentifierError):
    """
    Ticker 不唯一异常.

    当裸代码（如 "000001"）匹配多个标的时抛出.
    """

    def __init__(
        self,
        ticker: str,
        matches: list[dict[str, object]],
    ) -> None:
        """
        初始化 AmbiguousTickerError.

        Args:
            ticker: 裸代码
            matches: 匹配项列表，每项包含 source_ticker, instrument_id, name

        """
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
#
# These errors were originally defined in ditto_interfaces.errors (inheriting from
# DittoPortError).  They are re-homed here under DataError so that the app
# layer can reference them without depending on port/interfaces.
# The constructor API is fully compatible with the port-side originals.


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
    if not isinstance(error, (httpx.NetworkError, httpx.TimeoutException)):
        raise ValueError(
            "Expected httpx.NetworkError or httpx.TimeoutException, "
            + f"got {type(error).__name__}"
        )

    return NetworkError.from_httpx(error, source, context)


__all__ = [
    "AmbiguousTickerError",
    "AuthError",
    "CalendarError",
    "DataError",
    "DataSourceError",
    "DataValidationError",
    "DatasetNotFoundError",
    "DerivedDependencyError",
    "DerivedError",
    "DerivedMaterializationError",
    "DerivedNotFoundError",
    "DerivedNotImplementedError",
    "DerivedValidationError",
    "DerivedVersionError",
    "IdentifierError",
    "IdentifierNotFoundError",
    "InstrumentIdNotFoundError",
    "NetworkError",
    "NoIdentifierProvidedError",
    "PartitionNotFoundError",
    "PersistenceError",
    "SchemaValidationError",
    "SourceFetchError",
    "TradingDateNotFoundError",
    "ValidationError",
    "WriteError",
    "convert_httpx_to_network_error",
]
