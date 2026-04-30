"""Tests for CalendarReader and CalendarWriter (CQRS pattern)."""

import pytest
from ditto_data.storage.metadata.calendar import CalendarReader, CalendarWriter
from ditto_data.storage.sqlite_client import SQLiteClient
from pytest_mock import MockerFixture


class TestCalendarReader:
    """Tests for CalendarReader."""

    @pytest.fixture(autouse=True)
    def setup(self, sqlite_client: SQLiteClient) -> None:
        """使用 fixture 自动注入已初始化的数据库客户端."""
        self.client = sqlite_client
        self.reader = CalendarReader(self.client)

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
        self.reader.reload()

    def test_is_trading_day(self) -> None:
        """Test checking if a date is a trading day."""
        assert self.reader.is_trading_day("2024-01-02") is True
        assert self.reader.is_trading_day("2024-01-01") is False
        assert self.reader.is_trading_day("2024-01-06") is False  # Saturday

    def test_get_calendar_day(self) -> None:
        """Test getting calendar day data."""
        day = self.reader.get("2024-01-02")
        assert day is not None
        assert day.trade_date == "2024-01-02"
        assert day.is_open is True
        assert day.prev_trade_date is None
        assert day.next_trade_date == "2024-01-03"

    def test_get_prev_trading_day(self) -> None:
        """Test getting previous trading day."""
        assert self.reader.get_prev("2024-01-03") == "2024-01-02"
        assert self.reader.get_prev("2024-01-08") == "2024-01-05"  # After weekend

    def test_get_next_trading_day(self) -> None:
        """Test getting next trading day."""
        assert self.reader.get_next("2024-01-02") == "2024-01-03"
        assert self.reader.get_next("2024-01-05") == "2024-01-08"  # Friday to Monday

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
        assert self.reader.offset(date, offset) == expected

    def test_offset_out_of_range(self) -> None:
        """Test offset beyond available data."""
        # Before first trading day
        assert self.reader.offset("2024-01-02", -10) is None
        # After last trading day
        assert self.reader.offset("2024-01-10", 10) is None

    def test_get_range(self) -> None:
        """Test getting trading days in a range."""
        result = self.reader.get_range("2024-01-02", "2024-01-05")
        assert len(result) == 4
        assert result == ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]

    def test_get_range_with_holidays(self) -> None:
        """Test getting range that includes holidays."""
        result = self.reader.get_range("2024-01-01", "2024-01-10")
        # Should exclude weekends and holidays
        assert len(result) == 7
        assert "2024-01-01" not in result  # Holiday
        assert "2024-01-06" not in result  # Saturday
        assert "2024-01-07" not in result  # Sunday

    def test_get_range_df(self) -> None:
        """Test getting range as DataFrame."""
        df = self.reader.get_range_df("2024-01-02", "2024-01-04", only_open=True)
        assert len(df) == 3
        assert "trade_date" in df.columns
        assert "is_open" in df.columns
        assert df["is_open"].to_list() == [True, True, True]

    def test_get_range_df_all_days(self) -> None:
        """Test getting range as DataFrame including non-trading days."""
        df = self.reader.get_range_df("2024-01-01", "2024-01-03", only_open=False)
        assert len(df) == 3
        assert df["trade_date"].to_list() == ["2024-01-01", "2024-01-02", "2024-01-03"]

    def test_count_trading_days(self) -> None:
        """Test counting trading days in range."""
        count = self.reader.count_trading_days("2024-01-01", "2024-01-10")
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
        self.reader.reload()

        result = self.reader.get_month_ends("2024-01-01", "2024-01-31")
        assert len(result) == 1
        assert result[0] == "2024-01-31"

    def test_get_first_trading_day(self) -> None:
        """Test getting first trading day."""
        first = self.reader.get_first_trading_day()
        assert first == "2024-01-02"

    def test_get_last_trading_day(self) -> None:
        """Test getting last trading day."""
        last = self.reader.get_last_trading_day()
        assert last == "2024-01-10"

    def test_get_latest_before(self) -> None:
        """Test getting latest trading day on or before a date."""
        # If date is a trading day, should return that day (on or before)
        assert self.reader.get_latest_before("2024-01-05") == "2024-01-05"
        # Monday, should get Monday itself since it's a trading day
        assert self.reader.get_latest_before("2024-01-08") == "2024-01-08"
        # Sunday, should get Friday (on or before Sunday)
        assert self.reader.get_latest_before("2024-01-07") == "2024-01-05"
        # Before first day
        assert self.reader.get_latest_before("2024-01-01") is None

    def test_get_earliest_after(self) -> None:
        """Test getting earliest trading day after a date."""
        # On or after includes the day itself if it's a trading day
        assert self.reader.get_earliest_after("2024-01-03") == "2024-01-03"
        # Sunday, should get Monday
        assert self.reader.get_earliest_after("2024-01-06") == "2024-01-08"
        # After last trading day (2024-01-10 is last trading day, so after that is None)
        # Actually 2024-01-10 is a trading day, so it should return itself
        assert self.reader.get_earliest_after("2024-01-10") == "2024-01-10"
        # Strictly after last day
        assert self.reader.get_earliest_after("2024-01-11") is None

    def test_get_range_returns_immutable_copy(self) -> None:
        """Test that get_range returns a copy to prevent cache pollution."""
        from ditto_platform.foundation.cache import DataCache

        # Create reader with DataCache
        data_cache = DataCache(ttl_seconds=300, max_size=1000, enable_metrics=False)
        reader_with_cache = CalendarReader(self.client, data_cache=data_cache)

        # Call get_range twice
        result1 = reader_with_cache.get_range("2024-01-02", "2024-01-05")
        result2 = reader_with_cache.get_range("2024-01-02", "2024-01-05")

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
        result3 = reader_with_cache.get_range("2024-01-02", "2024-01-05")
        assert len(result3) == 4
        assert "2024-01-02" in result3
        assert "2024-01-15" not in result3


class TestCalendarWriter:
    """Tests for CalendarWriter."""

    @pytest.fixture(autouse=True)
    def setup(self, sqlite_client: SQLiteClient) -> None:
        """使用 fixture 自动注入已初始化的数据库客户端."""
        self.client = sqlite_client
        self.reader = CalendarReader(self.client)
        self.writer = CalendarWriter(self.client, None, self.reader)

        # Insert test calendar data
        self._insert_test_data()

    def _insert_test_data(self) -> None:
        """Insert test trading calendar data."""
        test_data = [
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
                None,
                1,
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

        self.client.commit()
        self.reader.reload()

    def test_upsert(self) -> None:
        """Test upserting calendar records."""
        records = [
            {
                "trade_date": "2024-01-15",
                "is_open": True,
                "prev_trade_date": "2024-01-03",
                "next_trade_date": None,
            }
        ]

        count = self.writer.upsert(records)
        assert count == 1

        # Verify the record was inserted via reader
        day = self.reader.get("2024-01-15")
        assert day is not None
        assert day.trade_date == "2024-01-15"

    def test_upsert_logs_error_on_exception(self, mocker: MockerFixture) -> None:
        """Test upsert logs error with error_type and error_message on exception."""
        records = [
            {
                "trade_date": "2024-01-15",
                "is_open": True,
            }
        ]

        # Mock client.execute to raise an exception
        with mocker.patch.object(
            self.client, "execute", side_effect=RuntimeError("DB error")
        ):
            # Patch the logger in calendar_writer (where the actual logging happens)
            mock_logger = mocker.patch(
                "ditto_data.storage.metadata.calendar.calendar_writer.logger"
            )

            with pytest.raises(RuntimeError):
                self.writer.upsert(records)

            # Verify logger.error was called with error_type and error_message
            mock_logger.error.assert_called_once()
            call_kwargs = mock_logger.error.call_args.kwargs
            assert "error_type" in call_kwargs
            assert "error_message" in call_kwargs
            assert call_kwargs["event"] == "calendar_upsert_failed"
            assert call_kwargs["error_type"] == "RuntimeError"


class TestCalendarDayHalfDay:
    """Tests for is_half_day field in CalendarDay and store layer."""

    @pytest.fixture(autouse=True)
    def setup(self, sqlite_client: SQLiteClient) -> None:
        """使用 fixture 自动注入已初始化的数据库客户端."""
        self.client = sqlite_client
        self.reader = CalendarReader(self.client)
        self.writer = CalendarWriter(self.client, None, self.reader)

    def _insert_row(
        self,
        trade_date: str,
        is_open: bool,
        is_half_day: bool = False,
    ) -> None:
        """Insert a single calendar row with is_half_day."""
        self.client.execute(
            """INSERT INTO trading_calendar
            (trade_date, is_open, prev_trade_date, next_trade_date,
             week_of_year, month, quarter, year,
             is_week_end, is_month_end, is_quarter_end,
             is_half_day)
            VALUES (?, ?, NULL, NULL, NULL, NULL, NULL, NULL,
                    FALSE, FALSE, FALSE, ?)""",
            [trade_date, is_open, is_half_day],
        )
        self.client.commit()
        self.reader.reload()

    def test_calendar_day_has_is_half_day_field(self) -> None:
        """CalendarDay dataclass should contain is_half_day field with default False."""
        from ditto_data.models.metadata import CalendarDay

        day = CalendarDay(
            trade_date="2024-01-02",
            is_open=True,
            prev_trade_date=None,
            next_trade_date=None,
            week_of_year=1,
            month=1,
            quarter=1,
            year=2024,
            is_week_end=False,
            is_month_end=False,
            is_quarter_end=False,
        )
        assert hasattr(day, "is_half_day")
        assert day.is_half_day is False

    def test_reader_loads_is_half_day_false(self) -> None:
        """Reader should load is_half_day = FALSE from DB."""
        self._insert_row("2024-01-02", is_open=True, is_half_day=False)
        day = self.reader.get("2024-01-02")
        assert day is not None
        assert day.is_half_day is False

    def test_reader_loads_is_half_day_true(self) -> None:
        """Reader should load is_half_day = TRUE from DB."""
        self._insert_row("2024-12-31", is_open=True, is_half_day=True)
        day = self.reader.get("2024-12-31")
        assert day is not None
        assert day.is_half_day is True

    def test_writer_upsert_is_half_day(self) -> None:
        """Writer upsert should persist is_half_day field."""
        records = [
            {
                "trade_date": "2024-12-31",
                "is_open": True,
                "is_half_day": True,
            }
        ]
        self.writer.upsert(records)

        day = self.reader.get("2024-12-31")
        assert day is not None
        assert day.is_half_day is True

    def test_get_range_df_includes_is_half_day(self) -> None:
        """get_range_df should include is_half_day column."""
        self._insert_row("2024-12-31", is_open=True, is_half_day=True)
        self._insert_row("2025-01-02", is_open=True, is_half_day=False)

        df = self.reader.get_range_df("2024-12-31", "2025-01-02", only_open=True)
        assert "is_half_day" in df.columns
        assert df["is_half_day"].to_list() == [True, False]


class TestCalendarDayExchange:
    """Tests for exchange field in CalendarDay and store layer (T13)."""

    @pytest.fixture(autouse=True)
    def setup(self, sqlite_client: SQLiteClient) -> None:
        """使用 fixture 自动注入已初始化的数据库客户端."""
        self.client = sqlite_client
        self.reader = CalendarReader(self.client)
        self.writer = CalendarWriter(self.client, None, self.reader)

    def _insert_row(
        self,
        trade_date: str,
        is_open: bool,
        exchange: str = "SSE",
        is_special: bool = False,
    ) -> None:
        """Insert a single calendar row with exchange and is_special."""
        self.client.execute(
            """INSERT INTO trading_calendar
            (trade_date, is_open, exchange, prev_trade_date, next_trade_date,
             week_of_year, month, quarter, year,
             is_week_end, is_month_end, is_quarter_end,
             is_half_day, is_special)
            VALUES (?, ?, ?, NULL, NULL, NULL, NULL, NULL, NULL,
                    FALSE, FALSE, FALSE, FALSE, ?)""",
            [trade_date, is_open, exchange, is_special],
        )
        self.client.commit()
        self.reader.reload()

    def test_calendar_day_default_exchange_is_sse(self) -> None:
        """CalendarDay exchange defaults to 'SSE'."""
        from ditto_data.models.metadata import CalendarDay

        day = CalendarDay(
            trade_date="2024-01-02",
            is_open=True,
        )
        assert day.exchange == "SSE"

    def test_reader_loads_exchange_sse(self) -> None:
        """Reader should load exchange='SSE' from DB."""
        self._insert_row("2024-01-02", is_open=True, exchange="SSE")
        day = self.reader.get("2024-01-02")
        assert day is not None
        assert day.exchange == "SSE"

    def test_reader_loads_exchange_szse(self) -> None:
        """Reader should load exchange='SZSE' from DB."""
        self._insert_row("2024-01-02", is_open=True, exchange="SZSE")
        day = self.reader.get("2024-01-02")
        assert day is not None
        assert day.exchange == "SZSE"

    def test_writer_upsert_preserves_exchange(self) -> None:
        """Writer upsert should persist exchange field."""
        records = [
            {
                "trade_date": "2024-06-01",
                "is_open": True,
                "exchange": "SZSE",
            }
        ]
        self.writer.upsert(records)

        day = self.reader.get("2024-06-01")
        assert day is not None
        assert day.exchange == "SZSE"

    def test_get_range_df_includes_exchange(self) -> None:
        """get_range_df should include exchange column."""
        self._insert_row("2024-06-01", is_open=True, exchange="SSE")
        self._insert_row("2024-06-03", is_open=True, exchange="SZSE")

        df = self.reader.get_range_df("2024-06-01", "2024-06-03", only_open=True)
        assert "exchange" in df.columns
        assert df["exchange"].to_list() == ["SSE", "SZSE"]


class TestCalendarDayIsSpecial:
    """Tests for is_special field in CalendarDay and store layer (T13)."""

    @pytest.fixture(autouse=True)
    def setup(self, sqlite_client: SQLiteClient) -> None:
        """使用 fixture 自动注入已初始化的数据库客户端."""
        self.client = sqlite_client
        self.reader = CalendarReader(self.client)
        self.writer = CalendarWriter(self.client, None, self.reader)

    def _insert_row(
        self,
        trade_date: str,
        is_open: bool,
        is_special: bool = False,
    ) -> None:
        """Insert a single calendar row with is_special."""
        self.client.execute(
            """INSERT INTO trading_calendar
            (trade_date, is_open, prev_trade_date, next_trade_date,
             week_of_year, month, quarter, year,
             is_week_end, is_month_end, is_quarter_end,
             is_half_day, is_special)
            VALUES (?, ?, NULL, NULL, NULL, NULL, NULL, NULL,
                    FALSE, FALSE, FALSE, FALSE, ?)""",
            [trade_date, is_open, is_special],
        )
        self.client.commit()
        self.reader.reload()

    def test_calendar_day_default_is_special_is_false(self) -> None:
        """CalendarDay is_special defaults to False."""
        from ditto_data.models.metadata import CalendarDay

        day = CalendarDay(
            trade_date="2024-01-02",
            is_open=True,
        )
        assert day.is_special is False

    def test_reader_loads_is_special_false(self) -> None:
        """Reader should load is_special = FALSE from DB."""
        self._insert_row("2024-01-02", is_open=True, is_special=False)
        day = self.reader.get("2024-01-02")
        assert day is not None
        assert day.is_special is False

    def test_reader_loads_is_special_true(self) -> None:
        """Reader should load is_special = TRUE from DB."""
        self._insert_row("2024-09-18", is_open=True, is_special=True)
        day = self.reader.get("2024-09-18")
        assert day is not None
        assert day.is_special is True

    def test_writer_upsert_is_special(self) -> None:
        """Writer upsert should persist is_special field."""
        records = [
            {
                "trade_date": "2024-09-18",
                "is_open": True,
                "is_special": True,
            }
        ]
        self.writer.upsert(records)

        day = self.reader.get("2024-09-18")
        assert day is not None
        assert day.is_special is True

    def test_get_range_df_includes_is_special(self) -> None:
        """get_range_df should include is_special column."""
        self._insert_row("2024-09-18", is_open=True, is_special=True)
        self._insert_row("2024-09-19", is_open=True, is_special=False)

        df = self.reader.get_range_df("2024-09-18", "2024-09-19", only_open=True)
        assert "is_special" in df.columns
        assert df["is_special"].to_list() == [True, False]
