"""
DataHub exception classes.

Following design document at docs/design/02_data_design.md
"""


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
