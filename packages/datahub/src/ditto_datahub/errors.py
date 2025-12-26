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


class SidNotFoundError(IdentifierError):
    """Security identifier (SID) not found."""

    def __init__(
        self,
        message: str = "SID not found",
        identifier: str | None = None,
        source: str | None = None,
    ) -> None:
        """
        Initialize SidNotFoundError.

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
