"""Calendar Accessor for trading calendar data access."""

from __future__ import annotations

from typing import Any, Literal

import polars as pl
from ditto_foundation import M, logger, traced

from ditto_datahub.domains.metadata.calendar import CalendarStore


class CalendarAccessor:
    """
    Trading calendar accessor.

    Provides domain-level interface for trading calendar operations,
    delegating to CalendarStore for data access.
    """

    def __init__(
        self,
        calendar_store: CalendarStore,
    ) -> None:
        """
        Initialize CalendarAccessor.

        Args:
            calendar_store: Calendar store for data access.

        """
        self._calendar_store = calendar_store

    @traced("accessor.calendar.get")
    def get(
        self,
        start: str,
        end: str,
        only_open: bool = True,
    ) -> pl.DataFrame:
        """
        Get calendar data.

        Args:
            start: Start date (YYYY-MM-DD).
            end: End date (YYYY-MM-DD).
            only_open: Only return trading days.

        Returns:
            Calendar data DataFrame.

        """
        logger.debug(
            "Fetching calendar data",
            event="calendar_get_start",
            start=start,
            end=end,
            only_open=only_open,
        )

        result: pl.DataFrame = self._calendar_store.get_range_df(start, end, only_open)

        logger.debug(
            "Calendar data fetched",
            event="calendar_get_complete",
            row_count=len(result),
        )

        # Record metrics
        M.data_records.add(len(result), {"dataset": "calendar", "operation": "get"})

        return result

    def is_trading_day(self, date: str) -> bool:
        """
        Check if date is a trading day.

        Args:
            date: Date string (YYYY-MM-DD).

        Returns:
            True if trading day.

        """
        return self._calendar_store.is_trading_day(date)

    def list_trading_days(self, start: str, end: str) -> list[str]:
        """
        List trading days.

        Args:
            start: Start date (YYYY-MM-DD).
            end: End date (YYYY-MM-DD).

        Returns:
            List of trading dates.

        """
        return self._calendar_store.get_range(start, end)

    def get_last_trading_day(self) -> str | None:
        """
        Get the last (latest) trading day in the calendar.

        Returns:
            Latest trading day as YYYY-MM-DD string, or None if calendar is empty.

        """
        return self._calendar_store.get_last_trading_day()

    def get_first_trading_day(self) -> str | None:
        """
        Get the first (earliest) trading day in the calendar.

        Returns:
            Earliest trading day as YYYY-MM-DD string, or None if calendar is empty.

        """
        return self._calendar_store.get_first_trading_day()

    def get_prev(self, date: str) -> str | None:
        """
        Get previous trading day.

        Args:
            date: Date string (YYYY-MM-DD).

        Returns:
            Previous trading date, or None if not found.

        """
        return self._calendar_store.get_prev(date)

    def get_next(self, date: str) -> str | None:
        """
        Get next trading day.

        Args:
            date: Date string (YYYY-MM-DD).

        Returns:
            Next trading date, or None if not found.

        """
        return self._calendar_store.get_next(date)

    def count_trading_days(self, start: str, end: str) -> int:
        """
        Count trading days.

        Args:
            start: Start date (YYYY-MM-DD).
            end: End date (YYYY-MM-DD).

        Returns:
            Number of trading days.

        """
        return self._calendar_store.count_trading_days(start, end)

    def get_period_ends(
        self,
        start: str,
        end: str,
        period: Literal["week", "month", "quarter"] = "month",
    ) -> list[str]:
        """
        Get period-end trading days.

        Args:
            start: Start date (YYYY-MM-DD).
            end: End date (YYYY-MM-DD).
            period: Period type.

        Returns:
            List of period-end dates.

        """
        return self._calendar_store.get_period_ends(start, end, period)

    def get_month_ends(self, start: str, end: str) -> list[str]:
        """
        Get month-end trading days.

        Args:
            start: Start date (YYYY-MM-DD).
            end: End date (YYYY-MM-DD).

        Returns:
            List of month-end dates.

        """
        return self._calendar_store.get_month_ends(start, end)

    def get_quarter_ends(self, start: str, end: str) -> list[str]:
        """
        Get quarter-end trading days.

        Args:
            start: Start date (YYYY-MM-DD).
            end: End date (YYYY-MM-DD).

        Returns:
            List of quarter-end dates.

        """
        return self._calendar_store.get_quarter_ends(start, end)

    def upsert(self, records: list[dict[str, Any]]) -> None:
        """
        Insert or update calendar records.

        Args:
            records: List of calendar record dictionaries.

        """
        self._calendar_store.upsert(records)
