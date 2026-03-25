"""
DataHub exception classes.

Following design document at docs/design/02_data_design.md
"""


# ---------------------------------------------------------------------------
# Derived* error hierarchy — canonical definition (DataHub owns these
# because DataHub services raise them without depending on Core).
# Core re-exports from here via ditto_core.engine.errors.
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


class DataHubError(Exception):
    """DataHub base exception."""

    def __init__(self, message: str, details: dict[str, object] | None = None) -> None:
        """
        Initialize DataHub error.

        Args:
            message: Error message.
            details: Additional error details.

        """
        super().__init__(message)
        self.details = details or {}


class CalendarError(DataHubError):
    """Calendar-related error base class."""

    pass


class IdentifierError(DataHubError):
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


class ValidationError(DataHubError):
    """DataFrame schema validation failed."""

    pass


class DatasetNotFoundError(DataHubError):
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


class PartitionNotFoundError(DataHubError):
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


__all__ = [
    "AmbiguousTickerError",
    "CalendarError",
    "DataHubError",
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
    "PartitionNotFoundError",
    "SchemaValidationError",
    "TradingDateNotFoundError",
    "ValidationError",
]
