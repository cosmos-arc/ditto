"""
Trading calendar storage with in-memory cache optimization.

Core optimizations:
- Load all data into memory on startup (~7500 records, ~1MB)
- All query operations O(1) or O(log n)
- No SQL query overhead after initialization

Following design document at docs/design/02_data_design.md
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass
from typing import Any, Literal

import polars as pl
from ditto_foundation import logger, span

from ditto_datahub.errors import TradingDateNotFoundError
from ditto_datahub.runtime.cache import DataCache
from ditto_datahub.stores.sqlite_client import SQLiteClient


@dataclass(frozen=True)
class CalendarDay:
    """Single trading day data."""

    trade_date: str
    is_open: bool
    prev_trade_date: str | None
    next_trade_date: str | None
    week_of_year: int | None
    month: int | None
    quarter: int | None
    year: int | None
    is_week_end: bool
    is_month_end: bool
    is_quarter_end: bool


class CalendarStore:
    """
    Trading calendar storage with in-memory cache.

    All calendar data is loaded into memory on initialization for O(1)
    or O(log n) query performance.
    """

    def __init__(
        self,
        sqlite_client: SQLiteClient,
        data_cache: DataCache | None = None,
    ) -> None:
        """
        Initialize CalendarStore.

        Args:
            sqlite_client: SQLite client for database operations.
            data_cache: Optional DataCache for range query caching.

        """
        self._client = sqlite_client
        self._data_cache = data_cache
        self._cache: dict[str, CalendarDay] = {}
        self._all_days: list[str] = []
        self._trading_days: list[str] = []
        self._week_ends: list[str] = []
        self._month_ends: list[str] = []
        self._quarter_ends: list[str] = []
        self._load_cache()

    def _load_cache(self) -> None:
        """Load all calendar data into memory."""
        with span("calendar.load") as s:
            logger.info(
                "Loading calendar data into cache",
                event="calendar_load_start",
            )

        sql = "SELECT * FROM trading_calendar ORDER BY trade_date"
        rows = self._client.fetchall(sql)

        for r in rows:
            date_str = r["trade_date"]
            day = CalendarDay(
                trade_date=date_str,
                is_open=bool(r["is_open"]),
                prev_trade_date=r["prev_trade_date"],
                next_trade_date=r["next_trade_date"],
                week_of_year=r["week_of_year"],
                month=r["month"],
                quarter=r["quarter"],
                year=r["year"],
                is_week_end=bool(r["is_week_end"]),
                is_month_end=bool(r["is_month_end"]),
                is_quarter_end=bool(r["is_quarter_end"]),
            )

            self._cache[date_str] = day
            self._all_days.append(date_str)

            if day.is_open:
                self._trading_days.append(date_str)

                if day.is_week_end:
                    self._week_ends.append(date_str)
                if day.is_month_end:
                    self._month_ends.append(date_str)
                if day.is_quarter_end:
                    self._quarter_ends.append(date_str)

        # Set span attributes
        s.set_attribute("total_days", len(self._all_days))
        s.set_attribute("trading_days", len(self._trading_days))

        logger.info(
            "Calendar cache loaded successfully",
            event="calendar_load_complete",
            total_days=len(self._all_days),
            trading_days=len(self._trading_days),
            week_ends=len(self._week_ends),
            month_ends=len(self._month_ends),
            quarter_ends=len(self._quarter_ends),
        )

    def reload(self) -> None:
        """Reload cache (call after calendar update)."""
        logger.debug(
            "Reloading calendar cache",
            event="calendar_reload_start",
        )
        self._cache.clear()
        self._trading_days.clear()
        self._all_days.clear()
        self._week_ends.clear()
        self._month_ends.clear()
        self._quarter_ends.clear()

        # 失效 DataCache 中的日历相关缓存
        if self._data_cache:
            self._data_cache.invalidate_pattern("trading_days:*")

        self._load_cache()
        logger.debug(
            "Calendar cache reloaded successfully",
            event="calendar_reload_complete",
        )

    # ============ Basic queries (O(1)) ============

    def is_trading_day(self, date: str) -> bool:
        """
        Check if date is a trading day.

        Args:
            date: Date string (YYYY-MM-DD).

        Returns:
            True if trading day.

        """
        day = self._cache.get(date)
        return day.is_open if day else False

    def get(self, date: str) -> CalendarDay | None:
        """
        Get calendar data for a single day.

        Args:
            date: Date string (YYYY-MM-DD).

        Returns:
            CalendarDay or None if not found.

        """
        return self._cache.get(date)

    def get_prev(self, date: str) -> str | None:
        """
        Get previous trading day (O(1)).

        Args:
            date: Date string (YYYY-MM-DD).

        Returns:
            Previous trading date or None.

        """
        day = self._cache.get(date)
        if day:
            return day.prev_trade_date
        return None

    def get_next(self, date: str) -> str | None:
        """
        Get next trading day (O(1)).

        Args:
            date: Date string (YYYY-MM-DD).

        Returns:
            Next trading date or None.

        """
        day = self._cache.get(date)
        if day:
            return day.next_trade_date
        return None

    # ============ Offset queries (O(log n)) ============

    def offset(self, date: str, n: int) -> str | None:
        """
        Offset by n trading days.

        Args:
            date: Start date.
            n: Offset (positive for forward, negative for backward).

        Returns:
            Target trading date, or None if out of range.

        """
        if not self._trading_days:
            return None

        # Find position in trading days list
        idx = bisect.bisect_left(self._trading_days, date)

        if n == 0:
            # Return current day if trading day, else None
            if idx < len(self._trading_days) and self._trading_days[idx] == date:
                return date
            return None

        if n > 0:
            # Forward offset
            if idx < len(self._trading_days) and self._trading_days[idx] == date:
                target_idx = idx + n
            else:
                target_idx = idx + n - 1  # Next trading day counts as 1st
        # Backward offset
        elif idx < len(self._trading_days) and self._trading_days[idx] == date:
            target_idx = idx + n  # n is negative
        else:
            target_idx = idx + n  # idx already points to "next"

        if 0 <= target_idx < len(self._trading_days):
            return self._trading_days[target_idx]
        return None

    def offset_safe(self, date: str, n: int) -> str:
        """
        Offset by n trading days (raises exception if out of range).

        Args:
            date: Start date.
            n: Offset (positive for forward, negative for backward).

        Returns:
            Target trading date.

        Raises:
            TradingDateNotFoundError: If offset goes out of range.

        """
        result = self.offset(date, n)
        if result is None:
            raise TradingDateNotFoundError(
                f"Cannot offset {n} trading days from {date}",
                date=date,
                direction="next" if n > 0 else "prev",
            )
        return result

    # ============ Range queries (O(log n)) ============

    def get_range(self, start: str, end: str) -> list[str]:
        """
        Get trading days in date range.

        Args:
            start: Start date (inclusive).
            end: End date (inclusive).

        Returns:
            List of trading dates (always a copy).

        """
        if not self._trading_days:
            return []

        # 尝试从 DataCache 获取
        if self._data_cache:
            cache_key = f"trading_days:{start}:{end}"
            cached = self._data_cache.get(cache_key)
            if cached is not None:
                # 返回副本以防止缓存污染
                return cached.copy()

        # 从内存缓存计算
        start_idx = bisect.bisect_left(self._trading_days, start)
        end_idx = bisect.bisect_right(self._trading_days, end)
        result = self._trading_days[start_idx:end_idx]

        # 缓存结果（缓存原始列表）
        if self._data_cache:
            cache_key = f"trading_days:{start}:{end}"
            self._data_cache.set(cache_key, result)

        # 返回副本以防止调用方修改内部列表
        return result.copy()

    def get_range_df(
        self,
        start: str,
        end: str,
        only_open: bool = True,
    ) -> pl.DataFrame:
        """
        Get calendar DataFrame for date range.

        Args:
            start: Start date (inclusive).
            end: End date (inclusive).
            only_open: Only return trading days.

        Returns:
            DataFrame with calendar data.

        """
        dates = (
            self.get_range(start, end) if only_open else self._get_all_range(start, end)
        )

        if not dates:
            return pl.DataFrame()

        records: list[dict[str, Any]] = []
        for date in dates:
            day = self._cache.get(date)
            if day:
                records.append(
                    {
                        "trade_date": day.trade_date,
                        "is_open": day.is_open,
                        "prev_trade_date": day.prev_trade_date,
                        "next_trade_date": day.next_trade_date,
                        "is_week_end": day.is_week_end,
                        "is_month_end": day.is_month_end,
                        "is_quarter_end": day.is_quarter_end,
                    }
                )

        return pl.DataFrame(records)

    def _get_all_range(self, start: str, end: str) -> list[str]:
        """Get all dates in range (including non-trading days)."""
        if not self._all_days:
            return []

        start_idx = bisect.bisect_left(self._all_days, start)
        end_idx = bisect.bisect_right(self._all_days, end)

        return self._all_days[start_idx:end_idx]

    def count_trading_days(self, start: str, end: str) -> int:
        """
        Count trading days in range.

        Args:
            start: Start date (inclusive).
            end: End date (inclusive).

        Returns:
            Number of trading days.

        """
        return len(self.get_range(start, end))

    # ============ Period end queries (O(log n)) ============

    def get_period_ends(
        self,
        start: str,
        end: str,
        period: Literal["week", "month", "quarter"],
    ) -> list[str]:
        """
        Get period-end trading days.

        Args:
            start: Start date (inclusive).
            end: End date (inclusive).
            period: Period type ("week" | "month" | "quarter").

        Returns:
            List of period-end dates.

        """
        period_list = {
            "week": self._week_ends,
            "month": self._month_ends,
            "quarter": self._quarter_ends,
        }.get(period, [])

        if not period_list:
            return []

        start_idx = bisect.bisect_left(period_list, start)
        end_idx = bisect.bisect_right(period_list, end)

        return period_list[start_idx:end_idx]

    def get_month_ends(self, start: str, end: str) -> list[str]:
        """Get month-end trading days."""
        return self.get_period_ends(start, end, "month")

    def get_quarter_ends(self, start: str, end: str) -> list[str]:
        """Get quarter-end trading days."""
        return self.get_period_ends(start, end, "quarter")

    # ============ Boundary queries ============

    def get_first_trading_day(self) -> str | None:
        """Get earliest trading day."""
        return self._trading_days[0] if self._trading_days else None

    def get_last_trading_day(self) -> str | None:
        """Get latest trading day."""
        return self._trading_days[-1] if self._trading_days else None

    def get_latest_before(self, date: str) -> str | None:
        """
        Get latest trading day on or before date.

        Args:
            date: Reference date.

        Returns:
            Latest trading day on or before date, or None.

        """
        if not self._trading_days:
            return None

        # bisect_right returns insertion point after any existing entries
        # For "on or before", we want elements <= date
        idx = bisect.bisect_right(self._trading_days, date)
        if idx > 0:
            return self._trading_days[idx - 1]
        return None

    def get_earliest_after(self, date: str) -> str | None:
        """
        Get earliest trading day on or after date.

        Args:
            date: Reference date.

        Returns:
            Earliest trading day on or after date, or None.

        """
        if not self._trading_days:
            return None

        # bisect_left returns insertion point to maintain sorted order
        # For "on or after", we want elements >= date
        idx = bisect.bisect_left(self._trading_days, date)
        if idx < len(self._trading_days):
            return self._trading_days[idx]
        return None

    # ============ Write operations (also update cache) ============

    def upsert(self, records: list[dict[str, Any]]) -> int:
        """
        Insert or update calendar records.

        Args:
            records: List of calendar records.

        Returns:
            Number of affected rows.

        """
        if not records:
            return 0

        logger.info(
            "Starting calendar upsert",
            event="calendar_upsert_start",
            record_count=len(records),
        )

        try:
            count = 0
            for record in records:
                self._client.execute(
                    """INSERT OR REPLACE INTO trading_calendar
                    (trade_date, is_open, prev_trade_date, next_trade_date,
                    week_of_year, month, quarter, year,
                    is_week_end, is_month_end, is_quarter_end)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    [
                        record["trade_date"],
                        record.get("is_open", True),
                        record.get("prev_trade_date"),
                        record.get("next_trade_date"),
                        record.get("week_of_year"),
                        record.get("month"),
                        record.get("quarter"),
                        record.get("year"),
                        record.get("is_week_end", False),
                        record.get("is_month_end", False),
                        record.get("is_quarter_end", False),
                    ],
                )
                count += 1

            self._client.commit()
            self.reload()  # Update cache

            logger.info(
                "Calendar upsert completed",
                event="calendar_upsert_complete",
                affected_count=count,
            )
            return count

        except Exception:
            self._client.rollback()
            logger.error(
                "Calendar upsert failed",
                event="calendar_upsert_failed",
                record_count=len(records),
            )
            raise

    def close(self) -> None:
        """Close the underlying SQLite client."""
        self._client.close()
