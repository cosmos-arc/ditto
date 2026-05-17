"""Calendar-related error classes."""

from ditto_kernel.exceptions import DataError as _DataError


class CalendarError(_DataError):
    """Calendar-related error base class."""


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
