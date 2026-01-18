"""Tests for CalendarRepository."""

import pytest
from ditto_datahub.repositories.calendar import CalendarRepository
from ditto_datahub.stores.calendar_store import CalendarStore
from ditto_datahub.stores.sqlite_client import SQLiteClient
from ditto_foundation import SQLitePool


class TestCalendarRepository:
    """Tests for CalendarRepository."""

    def setup_method(self) -> None:
        """Set up test database."""
        self.pool = SQLitePool(":memory:")
        self.pool.init_schema()
        self.client = SQLiteClient(self.pool)
        self.calendar_store = CalendarStore(self.client)
        self.repo = CalendarRepository(self.calendar_store)

        # Insert test data
        self._insert_test_data()

    def _insert_test_data(self) -> None:
        """Insert test calendar data."""
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
                False,
                False,
                False,
            ),
            ("2024-01-08", True, "2024-01-05", None, 2, 1, 1, 2024, True, False, False),
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
        self.calendar_store.reload()

    def test_is_trading_day(self) -> None:
        """Test is_trading_day."""
        assert self.repo.is_trading_day("2024-01-02") is True
        assert self.repo.is_trading_day("2024-01-01") is False

    @pytest.mark.parametrize(
        ("method", "date", "expected"),
        [
            # get_prev tests
            ("prev", "2024-01-03", "2024-01-02"),
            ("prev", "2024-01-02", None),
            # get_next tests
            ("next", "2024-01-03", "2024-01-04"),
            ("next", "2024-01-08", None),
        ],
    )
    def test_get_adjacent_trading_day(
        self, method: str, date: str, expected: str | None
    ) -> None:
        """Test get_prev and get_next."""
        if method == "prev":
            result = self.repo.get_prev(date)
        else:
            result = self.repo.get_next(date)
        assert result == expected

    def test_list_trading_days(self) -> None:
        """Test list_trading_days."""
        result = self.repo.list_trading_days("2024-01-02", "2024-01-05")
        assert len(result) == 4
        assert result == ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]

    def test_count_trading_days(self) -> None:
        """Test count_trading_days."""
        count = self.repo.count_trading_days("2024-01-02", "2024-01-05")
        assert count == 4

    def test_get_week_ends(self) -> None:
        """Test get_week_ends."""
        result = self.repo.get_period_ends("2024-01-01", "2024-01-31", "week")
        assert len(result) == 1
        assert result[0] == "2024-01-08"

    def test_get_month_ends(self) -> None:
        """Test get_month_ends."""
        result = self.repo.get_month_ends("2024-01-01", "2024-01-31")
        # Test data doesn't have month end, should return empty
        assert result == []

    def test_get_quarter_ends(self) -> None:
        """Test get_quarter_ends."""
        result = self.repo.get_quarter_ends("2024-01-01", "2024-03-31")
        # Test data doesn't have quarter end
        assert result == []

    def test_get_returns_dataframe(self) -> None:
        """Test get returns DataFrame."""
        result = self.repo.get("2024-01-02", "2024-01-05", only_open=True)
        assert len(result) == 4
        assert "trade_date" in result.columns
        assert "is_open" in result.columns

    def test_get_last_trading_day(self) -> None:
        """Test get_last_trading_day."""
        result = self.repo.get_last_trading_day()
        assert result == "2024-01-08"

    def teardown_method(self) -> None:
        """Clean up after test."""
        # No cleanup needed for in-memory database
        pass
