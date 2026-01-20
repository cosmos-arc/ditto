"""
Tests for observability features in datahub module.

Tests verify that:
1. Spans are created for key operations (data.read, data.write,
   data.sid_resolve, calendar.load)
2. Metrics are recorded (data_records, data_update_duration)
"""

from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

import polars as pl
import pytest
from ditto_datahub.stores.adj_factor_store import AdjFactorStore
from ditto_datahub.stores.bars_store import BarsStore
from ditto_datahub.stores.calendar_store import CalendarStore
from ditto_datahub.stores.security_store import SecurityRegistration, SecurityStore
from ditto_datahub.stores.sqlite_client import SQLiteClient
from ditto_foundation import (
    get_recorded_metrics,
    get_recorded_spans,
    init,
)


class TestObservabilityBarsStore:
    """Test observability features in BarsStore."""

    def setup_method(self) -> None:
        """Set up test environment with assertions mode."""
        init(
            pytest_running=True,
            assertions_enabled=True,
            verbose_logging=False,
            force=True,
        )
        self.temp_dir = TemporaryDirectory()
        self.store = BarsStore(Path(self.temp_dir.name))

    def teardown_method(self) -> None:
        """Clean up test environment."""
        self.temp_dir.cleanup()

    def test_read_creates_span(self) -> None:
        """Test that read operation creates a span."""
        # Create test data first
        test_df = pl.DataFrame(
            {
                "sid": [1000001],
                "trade_date": [date(2024, 1, 1)],
                "open": [10.0],
                "high": [12.0],
                "low": [9.0],
                "close": [11.0],
                "volume": [1000],
            }
        )
        self.store.write("stock_daily", test_df, 2024)

        # Clear previous spans
        _ = get_recorded_spans()

        # Perform read operation
        self.store.read("stock_daily", start_date="2024-01-01", end_date="2024-01-31")

        # Verify span was created
        spans = get_recorded_spans()
        assert len(spans) > 0
        # Find the data.read span
        read_spans = [s for s in spans if s.name == "data.read"]
        assert len(read_spans) > 0

    def test_write_creates_span(self) -> None:
        """Test that write operation creates a span."""
        # Clear previous spans
        _ = get_recorded_spans()

        # Perform write operation
        test_df = pl.DataFrame(
            {
                "sid": [1000001],
                "trade_date": [date(2024, 1, 1)],
                "open": [10.0],
                "high": [12.0],
                "low": [9.0],
                "close": [11.0],
                "volume": [1000],
            }
        )
        self.store.write("stock_daily", test_df, 2024)

        # Verify span was created
        spans = get_recorded_spans()
        assert len(spans) > 0
        # Find the data.write span
        write_spans = [s for s in spans if s.name == "data.write"]
        assert len(write_spans) > 0

    def test_read_records_metrics(self) -> None:
        """Test that read operation records metrics."""
        # Create test data first
        test_df = pl.DataFrame(
            {
                "sid": [1000001, 1000002],
                "trade_date": [date(2024, 1, 1), date(2024, 1, 2)],
                "open": [10.0, 11.0],
                "high": [12.0, 13.0],
                "low": [9.0, 10.0],
                "close": [11.0, 12.0],
                "volume": [1000, 2000],
            }
        )
        self.store.write("stock_daily", test_df, 2024)

        # Clear previous metrics
        _ = get_recorded_metrics()

        # Perform read operation
        self.store.read("stock_daily", start_date="2024-01-01", end_date="2024-01-31")

        # Verify metrics were recorded
        metrics = get_recorded_metrics()
        assert metrics.get("metrics_recorded") is True

    def test_write_records_metrics(self) -> None:
        """Test that write operation records metrics."""
        # Clear previous metrics
        _ = get_recorded_metrics()

        # Perform write operation
        test_df = pl.DataFrame(
            {
                "sid": [1000001, 1000002],
                "trade_date": [date(2024, 1, 1), date(2024, 1, 2)],
                "open": [10.0, 11.0],
                "high": [12.0, 13.0],
                "low": [9.0, 10.0],
                "close": [11.0, 12.0],
                "volume": [1000, 2000],
            }
        )
        self.store.write("stock_daily", test_df, 2024)

        # Verify metrics were recorded
        metrics = get_recorded_metrics()
        assert metrics.get("metrics_recorded") is True


class TestObservabilityAdjFactorStore:
    """Test observability features in AdjFactorStore."""

    def setup_method(self) -> None:
        """Set up test environment with assertions mode."""
        init(
            pytest_running=True,
            assertions_enabled=True,
            verbose_logging=False,
            force=True,
        )
        self.temp_dir = TemporaryDirectory()
        self.store = AdjFactorStore(Path(self.temp_dir.name))

    def teardown_method(self) -> None:
        """Clean up test environment."""
        self.temp_dir.cleanup()

    def test_read_creates_span(self) -> None:
        """Test that read operation creates a span."""
        # Create test data first
        test_df = pl.DataFrame(
            {
                "sid": [1000001],
                "trade_date": [date(2024, 1, 1)],
                "adj_factor": [1.5],
            }
        )
        self.store.write("adj_factor", test_df, 2024)

        # Clear previous spans
        _ = get_recorded_spans()

        # Perform read operation
        self.store.read("adj_factor", start_date="2024-01-01", end_date="2024-01-31")

        # Verify span was created
        spans = get_recorded_spans()
        read_spans = [s for s in spans if s.name == "data.read"]
        assert len(read_spans) > 0

    def test_write_creates_span(self) -> None:
        """Test that write operation creates a span."""
        # Clear previous spans
        _ = get_recorded_spans()

        # Perform write operation
        test_df = pl.DataFrame(
            {
                "sid": [1000001],
                "trade_date": [date(2024, 1, 1)],
                "adj_factor": [1.5],
            }
        )
        self.store.write("adj_factor", test_df, 2024)

        # Verify span was created
        spans = get_recorded_spans()
        write_spans = [s for s in spans if s.name == "data.write"]
        assert len(write_spans) > 0


class TestObservabilitySecurityStore:
    """Test observability features in SecurityStore."""

    @pytest.fixture(autouse=True)
    def setup(self, sqlite_client: SQLiteClient) -> None:
        """使用 fixture 自动注入已初始化的数据库客户端."""
        init(
            pytest_running=True,
            assertions_enabled=True,
            verbose_logging=False,
            force=True,
        )
        self.client = sqlite_client
        self.store = SecurityStore(self.client)

    def teardown_method(self) -> None:
        """Clean up after test."""
        pass

    def test_resolve_sid_creates_span(self) -> None:
        """Test that resolve_sid operation creates a span."""
        # Register a security first
        self.store.register(
            sid=1000001,
            registration=SecurityRegistration(
                src_code="510300.SZ",
                symbol="510300",
                name="CSI 300 ETF",
                exchange="SZSE",
                asset_class="etf",
                list_date="2012-04-25",
            ),
        )

        # Clear previous spans
        _ = get_recorded_spans()

        # Perform resolve_sid operation
        self.store.resolve_sid("510300.SZ", "tushare", asof=None)

        # Verify span was created
        spans = get_recorded_spans()
        resolve_spans = [s for s in spans if s.name == "data.sid_resolve"]
        assert len(resolve_spans) > 0

    def test_resolve_sid_records_metrics(self) -> None:
        """Test that resolve_sid operation records metrics."""
        # Register a security first
        self.store.register(
            sid=1000001,
            registration=SecurityRegistration(
                src_code="510300.SZ",
                symbol="510300",
                name="CSI 300 ETF",
                exchange="SZSE",
                asset_class="etf",
                list_date="2012-04-25",
            ),
        )

        # Clear previous metrics
        _ = get_recorded_metrics()

        # Perform resolve_sid operation
        self.store.resolve_sid("510300.SZ", "tushare", asof=None)

        # Verify metrics were recorded
        metrics = get_recorded_metrics()
        assert metrics.get("metrics_recorded") is True

    def test_resolve_sid_not_found_records_metrics(self) -> None:
        """Test that resolve_sid for non-existent security records metrics."""
        # Clear previous metrics
        _ = get_recorded_metrics()

        # Perform resolve_sid operation for non-existent security
        self.store.resolve_sid("NONEXISTENT", "tushare", asof=None)

        # Verify metrics were recorded
        metrics = get_recorded_metrics()
        assert metrics.get("metrics_recorded") is True


class TestObservabilityCalendarStore:
    """Test observability features in CalendarStore."""

    @pytest.fixture(autouse=True)
    def setup(self, sqlite_client: SQLiteClient) -> None:
        """使用 fixture 自动注入已初始化的数据库客户端."""
        init(
            pytest_running=True,
            assertions_enabled=True,
            verbose_logging=False,
            force=True,
        )
        self.client = sqlite_client
        self.store = CalendarStore(self.client)

    def teardown_method(self) -> None:
        """Clean up after test."""
        pass

    def test_calendar_load_creates_span(self) -> None:
        """Test that calendar loading creates a span."""
        # Insert test calendar data
        self.client.execute(
            """INSERT INTO trading_calendar
            (trade_date, is_open, prev_trade_date, next_trade_date,
             week_of_year, month, quarter, year,
             is_week_end, is_month_end, is_quarter_end)
            VALUES ('2024-01-02', TRUE, NULL, '2024-01-03',
                    1, 1, 1, 2024, FALSE, FALSE, FALSE)"""
        )
        self.client.commit()

        # Clear previous spans
        _ = get_recorded_spans()

        # Reload cache to trigger calendar.load span
        self.store._load_cache()

        # Verify span was created
        spans = get_recorded_spans()
        load_spans = [s for s in spans if s.name == "calendar.load"]
        assert len(load_spans) > 0

    def test_calendar_load_span_has_attributes(self) -> None:
        """Test that calendar load span has proper attributes."""
        # Insert test calendar data with multiple days
        for i in range(3):
            trade_date = f"2024-01-{i + 2:02d}"
            self.client.execute(
                f"""INSERT INTO trading_calendar
                (trade_date, is_open, prev_trade_date, next_trade_date,
                 week_of_year, month, quarter, year,
                 is_week_end, is_month_end, is_quarter_end)
                VALUES ('{trade_date}', TRUE, NULL, NULL,
                        1, 1, 1, 2024, FALSE, FALSE, FALSE)"""
            )
        self.client.commit()

        # Clear previous spans
        _ = get_recorded_spans()

        # Reload cache to trigger calendar.load span
        self.store._load_cache()

        # Verify span has attributes
        spans = get_recorded_spans()
        load_spans = [s for s in spans if s.name == "calendar.load"]
        assert len(load_spans) > 0

        # Check span attributes
        span = load_spans[0]
        # The span should have attributes set during calendar loading
        assert span.attributes is not None


class TestObservabilityIntegration:
    """Integration tests for observability across datahub."""

    @pytest.fixture(autouse=True)
    def setup(self, sqlite_client: SQLiteClient) -> None:
        """使用 fixture 自动注入已初始化的数据库客户端."""
        init(
            pytest_running=True,
            assertions_enabled=True,
            verbose_logging=False,
            force=True,
        )
        self.temp_dir = TemporaryDirectory()
        self.client = sqlite_client

    def teardown_method(self) -> None:
        """Clean up test environment."""
        self.temp_dir.cleanup()

    def test_end_to_end_observability(self) -> None:
        """Test observability through a complete data workflow."""
        # Clear previous data
        _ = get_recorded_spans()
        _ = get_recorded_metrics()

        # Create stores
        bars_store = BarsStore(Path(self.temp_dir.name))
        security_store = SecurityStore(self.client)

        # Register security
        security_store.register(
            sid=1000001,
            registration=SecurityRegistration(
                src_code="510300.SZ",
                symbol="510300",
                name="CSI 300 ETF",
                exchange="SZSE",
                asset_class="etf",
                list_date="2012-04-25",
            ),
        )

        # Resolve SID to trigger data.sid_resolve span
        security_store.resolve_sid("510300.SZ", "tushare", asof=None)

        # Write bars data
        test_df = pl.DataFrame(
            {
                "sid": [1000001, 1000001],
                "trade_date": [date(2024, 1, 1), date(2024, 1, 2)],
                "open": [10.0, 11.0],
                "high": [12.0, 13.0],
                "low": [9.0, 10.0],
                "close": [11.0, 12.0],
                "volume": [1000, 2000],
            }
        )
        bars_store.write("stock_daily", test_df, 2024)

        # Read bars data
        result = bars_store.read(
            "stock_daily", start_date="2024-01-01", end_date="2024-01-31"
        )

        # Verify operations completed
        assert len(result) == 2

        # Verify spans were created
        spans = get_recorded_spans()
        assert len(spans) > 0

        # Check for expected span names
        span_names = {s.name for s in spans}
        assert "data.write" in span_names
        assert "data.read" in span_names
        assert "data.sid_resolve" in span_names

        # Verify metrics were recorded
        metrics = get_recorded_metrics()
        assert metrics.get("metrics_recorded") is True
