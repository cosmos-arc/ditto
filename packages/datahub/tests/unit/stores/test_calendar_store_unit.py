"""Tests for CalendarStore."""

import pytest
from ditto_datahub.runtime.sqlite_pool import SQLitePool
from ditto_datahub.stores.calendar_store import CalendarStore
from ditto_datahub.stores.sqlite_client import SQLiteClient


class TestCalendarStore:
    """Tests for CalendarStore."""

    def setup_method(self) -> None:
        """Set up test database."""
        self.pool = SQLitePool(":memory:")
        self.pool.init_schema()
        self.client = SQLiteClient(self.pool)
        self.store = CalendarStore(self.client)

        # Insert test calendar data
        self._insert_test_data()

    def _insert_test_data(self) -> None:
        """Insert test trading calendar data."""
        # Test data: 2024-01-01 (Mon, holiday) to 2024-01-10 (Wed)
        test_data = [
            # trade_date, is_open, prev, next, week, month, quarter, year,
            # is_week_end, is_month_end, is_quarter_end
            (
                "2024-01-01",
                False,
                None,
                "2024-01-02",
                1,
                1,
                1,
                2024,
                False,
                False,
                False,
            ),
            (
                "2024-01-02",
                True,
                None,
                "2024-01-03",
                1,
                1,
                1,
                2024,
                False,
                False,
                False,
            ),
            (
                "2024-01-03",
                True,
                "2024-01-02",
                "2024-01-04",
                1,
                1,
                1,
                2024,
                False,
                False,
                False,
            ),
            (
                "2024-01-04",
                True,
                "2024-01-03",
                "2024-01-05",
                1,
                1,
                1,
                2024,
                False,
                False,
                False,
            ),
            (
                "2024-01-05",
                True,
                "2024-01-04",
                "2024-01-08",
                1,
                1,
                1,
                2024,
                True,
                False,
                False,
            ),
            (
                "2024-01-06",
                False,
                "2024-01-05",
                "2024-01-08",
                1,
                1,
                1,
                2024,
                False,
                False,
                False,
            ),
            (
                "2024-01-07",
                False,
                "2024-01-05",
                "2024-01-08",
                1,
                1,
                1,
                2024,
                False,
                False,
                False,
            ),
            (
                "2024-01-08",
                True,
                "2024-01-05",
                "2024-01-09",
                2,
                1,
                1,
                2024,
                False,
                False,
                False,
            ),
            (
                "2024-01-09",
                True,
                "2024-01-08",
                "2024-01-10",
                2,
                1,
                1,
                2024,
                False,
                False,
                False,
            ),
            (
                "2024-01-10",
                True,
                "2024-01-09",
                None,
                2,
                1,
                1,
                2024,
                False,
                False,
                False,
            ),
        ]

        for row in test_data:
            self.client.execute(
                """INSERT INTO trading_calendar
                (trade_date, is_open, prev_trade_date, next_trade_date,
                 week_of_year, month, quarter, year,
                 is_week_end, is_month_end, is_quarter_end)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                row,
            )

        # Update prev/next references
        sql = "UPDATE trading_calendar SET prev_trade_date = NULL WHERE trade_date = ?"
        self.client.execute(sql, ["2024-01-02"])

        sql = "UPDATE trading_calendar SET next_trade_date = NULL WHERE trade_date = ?"
        self.client.execute(sql, ["2024-01-10"])

        self.client.commit()

        # Reload cache
        self.store._load_cache()

    def test_is_trading_day(self) -> None:
        """Test checking if a date is a trading day."""
        assert self.store.is_trading_day("2024-01-02") is True
        assert self.store.is_trading_day("2024-01-01") is False
        assert self.store.is_trading_day("2024-01-06") is False  # Saturday

    def test_get_calendar_day(self) -> None:
        """Test getting calendar day data."""
        day = self.store.get("2024-01-02")
        assert day is not None
        assert day.trade_date == "2024-01-02"
        assert day.is_open is True
        assert day.prev_trade_date is None
        assert day.next_trade_date == "2024-01-03"

    def test_get_prev_trading_day(self) -> None:
        """Test getting previous trading day."""
        assert self.store.get_prev("2024-01-03") == "2024-01-02"
        assert self.store.get_prev("2024-01-08") == "2024-01-05"  # After weekend

    def test_get_next_trading_day(self) -> None:
        """Test getting next trading day."""
        assert self.store.get_next("2024-01-02") == "2024-01-03"
        assert self.store.get_next("2024-01-05") == "2024-01-08"  # Friday to Monday

    @pytest.mark.parametrize(
        ("date", "offset", "expected"),
        [
            # Positive offsets
            ("2024-01-02", 0, "2024-01-02"),
            ("2024-01-02", 1, "2024-01-03"),
            ("2024-01-02", 2, "2024-01-04"),
            ("2024-01-05", 1, "2024-01-08"),  # Friday to Monday
            # Negative offsets
            ("2024-01-04", -1, "2024-01-03"),
            ("2024-01-04", -2, "2024-01-02"),
            ("2024-01-08", -1, "2024-01-05"),  # Monday to Friday
        ],
    )
    def test_offset(self, date: str, offset: int, expected: str) -> None:
        """Test offset with positive and negative values."""
        assert self.store.offset(date, offset) == expected

    def test_offset_out_of_range(self) -> None:
        """Test offset beyond available data."""
        # Before first trading day
        assert self.store.offset("2024-01-02", -10) is None
        # After last trading day
        assert self.store.offset("2024-01-10", 10) is None

    def test_get_range(self) -> None:
        """Test getting trading days in a range."""
        result = self.store.get_range("2024-01-02", "2024-01-05")
        assert len(result) == 4
        assert result == ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]

    def test_get_range_with_holidays(self) -> None:
        """Test getting range that includes holidays."""
        result = self.store.get_range("2024-01-01", "2024-01-10")
        # Should exclude weekends and holidays
        assert len(result) == 7
        assert "2024-01-01" not in result  # Holiday
        assert "2024-01-06" not in result  # Saturday
        assert "2024-01-07" not in result  # Sunday

    def test_get_range_df(self) -> None:
        """Test getting range as DataFrame."""
        df = self.store.get_range_df("2024-01-02", "2024-01-04", only_open=True)
        assert len(df) == 3
        assert "trade_date" in df.columns
        assert "is_open" in df.columns
        assert df["is_open"].to_list() == [True, True, True]

    def test_get_range_df_all_days(self) -> None:
        """Test getting range as DataFrame including non-trading days."""
        df = self.store.get_range_df("2024-01-01", "2024-01-03", only_open=False)
        assert len(df) == 3
        assert df["trade_date"].to_list() == ["2024-01-01", "2024-01-02", "2024-01-03"]

    def test_count_trading_days(self) -> None:
        """Test counting trading days in range."""
        count = self.store.count_trading_days("2024-01-01", "2024-01-10")
        assert count == 7

    def test_get_month_ends(self) -> None:
        """Test getting month-end trading days."""
        # Add month-end data
        self.client.execute(
            """INSERT INTO trading_calendar
            (trade_date, is_open, prev_trade_date, next_trade_date,
             week_of_year, month, quarter, year,
             is_week_end, is_month_end, is_quarter_end)
            VALUES ('2024-01-31', TRUE, '2024-01-30', '2024-02-01',
                    5, 1, 1, 2024, TRUE, TRUE, FALSE)"""
        )
        self.client.commit()
        self.store._load_cache()

        result = self.store.get_month_ends("2024-01-01", "2024-01-31")
        assert len(result) == 1
        assert result[0] == "2024-01-31"

    def test_get_first_trading_day(self) -> None:
        """Test getting first trading day."""
        first = self.store.get_first_trading_day()
        assert first == "2024-01-02"

    def test_get_last_trading_day(self) -> None:
        """Test getting last trading day."""
        last = self.store.get_last_trading_day()
        assert last == "2024-01-10"

    def test_get_latest_before(self) -> None:
        """Test getting latest trading day on or before a date."""
        # If date is a trading day, should return that day (on or before)
        assert self.store.get_latest_before("2024-01-05") == "2024-01-05"
        # Monday, should get Monday itself since it's a trading day
        assert self.store.get_latest_before("2024-01-08") == "2024-01-08"
        # Sunday, should get Friday (on or before Sunday)
        assert self.store.get_latest_before("2024-01-07") == "2024-01-05"
        # Before first day
        assert self.store.get_latest_before("2024-01-01") is None

    def test_get_earliest_after(self) -> None:
        """Test getting earliest trading day after a date."""
        # On or after includes the day itself if it's a trading day
        assert self.store.get_earliest_after("2024-01-03") == "2024-01-03"
        # Sunday, should get Monday
        assert self.store.get_earliest_after("2024-01-06") == "2024-01-08"
        # After last trading day (2024-01-10 is last trading day, so after that is None)
        # Actually 2024-01-10 is a trading day, so it should return itself
        assert self.store.get_earliest_after("2024-01-10") == "2024-01-10"
        # Strictly after last day
        assert self.store.get_earliest_after("2024-01-11") is None

    def test_upsert(self) -> None:
        """Test upserting calendar records."""
        records = [
            {
                "trade_date": "2024-01-15",
                "is_open": True,
                "prev_trade_date": "2024-01-10",
                "next_trade_date": None,
            }
        ]

        count = self.store.upsert(records)
        assert count == 1

        # Verify the record was inserted

    def test_upsert_logs_error_on_exception(self) -> None:
        """Test upsert logs error with error_type and error_message on exception."""
        from unittest.mock import patch

        records = [
            {
                "trade_date": "2024-01-15",
                "is_open": True,
            }
        ]

        # Mock client.execute to raise an exception
        with patch.object(self.client, "execute", side_effect=RuntimeError("DB error")):
            with patch("ditto_datahub.stores.calendar_store.logger") as mock_logger:
                with pytest.raises(RuntimeError):
                    self.store.upsert(records)

                # Verify logger.error was called with error_type and error_message
                mock_logger.error.assert_called_once()
                call_kwargs = mock_logger.error.call_args.kwargs
                assert "error_type" in call_kwargs
                assert "error_message" in call_kwargs
                assert call_kwargs["event"] == "calendar_upsert_failed"
                assert call_kwargs["error_type"] == "RuntimeError"

    def test_get_range_returns_immutable_copy(self) -> None:
        """Test that get_range returns a copy to prevent cache pollution."""
        # 测试方法内导入
        from ditto_foundation.cache import DataCache

        # Create store with DataCache
        data_cache = DataCache(ttl_seconds=300, max_size=1000, enable_metrics=False)
        store_with_cache = CalendarStore(self.client, data_cache=data_cache)

        # Call get_range twice
        result1 = store_with_cache.get_range("2024-01-02", "2024-01-05")
        result2 = store_with_cache.get_range("2024-01-02", "2024-01-05")

        # Each call returns a copy (different objects)
        assert result1 is not result2, "Each call should return a new copy"

        # But content should be the same
        assert result1 == result2

        # Modify result1
        result1.append("2024-01-15")
        result1.remove("2024-01-02")

        # result2 should not be affected
        assert len(result2) == 4
        assert "2024-01-02" in result2
        assert "2024-01-15" not in result2

        # Third call should return correct data
        result3 = store_with_cache.get_range("2024-01-02", "2024-01-05")
        assert len(result3) == 4
        assert "2024-01-02" in result3
        assert "2024-01-15" not in result3

    def teardown_method(self) -> None:
        """Clean up after test."""
        pass
