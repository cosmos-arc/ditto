"""
Calendar writer for CQRS pattern.

Provides write access to trading calendar data with cache invalidation.
Following design document at docs/plans/2026-02-09-datahub-metadata-cqrs-design.md
"""

from __future__ import annotations

from typing import Any

from ditto_infra.foundation import logger, traced
from ditto_infra.foundation.cache import DataCache

from ditto_datahub.stores.metadata.calendar.calendar_reader import CalendarReader
from ditto_datahub.stores.sqlite_client import SQLiteClient


class CalendarWriter:
    """
    Trading calendar writer with cache invalidation.

    Provides write operations for calendar data and automatically
    triggers cache reload in the reader after writes.

    Attributes:
        _client: SQLite client for database operations.
        _data_cache: DataCache for cache invalidation.
        _reader: CalendarReader instance for cache reload.

    """

    def __init__(
        self,
        sqlite_client: SQLiteClient,
        data_cache: DataCache[list[str]] | None,
        reader: CalendarReader,
    ) -> None:
        """
        Initialize CalendarWriter.

        Args:
            sqlite_client: SQLite client for database operations.
            data_cache: DataCache for cache invalidation.
            reader: CalendarReader instance for cache reload.

        """
        self._client = sqlite_client
        self._data_cache = data_cache
        self._reader = reader

    @traced("data.calendar.upsert")
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
                    (trade_date, is_open, exchange, prev_trade_date, next_trade_date,
                    week_of_year, month, quarter, year,
                    is_week_end, is_month_end, is_quarter_end, is_half_day, is_special)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    [
                        record["trade_date"],
                        record.get("is_open", True),
                        record.get("exchange", "SSE"),
                        record.get("prev_trade_date"),
                        record.get("next_trade_date"),
                        record.get("week_of_year"),
                        record.get("month"),
                        record.get("quarter"),
                        record.get("year"),
                        record.get("is_week_end", False),
                        record.get("is_month_end", False),
                        record.get("is_quarter_end", False),
                        record.get("is_half_day", False),
                        record.get("is_special", False),
                    ],
                )
                count += 1

            self._client.commit()

            # Reload cache (reload() 内部已处理 DataCache invalidate)
            self._reader.reload()

            logger.info(
                "Calendar upsert completed",
                event="calendar_upsert_complete",
                affected_count=count,
            )
            return count

        except Exception as e:
            self._client.rollback()
            logger.error(
                "Calendar upsert failed",
                event="calendar_upsert_failed",
                record_count=len(records),
                error_type=type(e).__name__,
                error_message=str(e),
            )
            raise
