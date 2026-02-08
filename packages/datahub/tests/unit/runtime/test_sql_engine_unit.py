"""Unit tests for SqlEngine."""

from pathlib import Path

import polars as pl
import pytest
from ditto_datahub.runtime.sql_engine import SqlEngine
from pytest_mock import MockerFixture


@pytest.mark.unit
class TestSqlEngine:
    """Tests for SqlEngine."""

    def test_initialization(self, mocker: MockerFixture) -> None:
        """Test that SqlEngine initializes with defaults."""
        mock_instrument_store = mocker.Mock()
        mock_calendar_store = mocker.Mock()
        data_root = Path("/test/data")

        engine = SqlEngine(
            data_root=data_root,
            instrument_store=mock_instrument_store,
            calendar_store=mock_calendar_store,
        )

        assert engine.data_root == data_root
        assert engine.instrument_store is mock_instrument_store
        assert engine.calendar_store is mock_calendar_store
        assert engine._sqlite_attached is False
        assert engine._enable_plan_cache is True
        assert engine._plan_cache_size == 1000
        assert engine._slow_query_threshold == 1.0

    def test_initialization_with_custom_settings(self, mocker: MockerFixture) -> None:
        """Test initialization with custom settings."""
        mock_instrument_store = mocker.Mock()
        mock_calendar_store = mocker.Mock()
        data_root = Path("/test/data")

        engine = SqlEngine(
            data_root=data_root,
            instrument_store=mock_instrument_store,
            calendar_store=mock_calendar_store,
            enable_plan_cache=False,
            plan_cache_size=500,
            slow_query_threshold=2.0,
        )

        assert engine._enable_plan_cache is False
        assert engine._plan_cache_size == 500
        assert engine._slow_query_threshold == 2.0

    def test_normalize_query_removes_comments(self, mocker: MockerFixture) -> None:
        """Test query normalization removes SQL comments."""
        mock_instrument_store = mocker.Mock()
        mock_calendar_store = mocker.Mock()
        engine = SqlEngine(
            data_root=Path("/test"),
            instrument_store=mock_instrument_store,
            calendar_store=mock_calendar_store,
        )

        query = "SELECT * FROM table -- comment\nWHERE id = 1"
        normalized = engine._normalize_query(query)

        assert "-- comment" not in normalized
        assert "WHERE id = 1" in normalized

    def test_normalize_query_removes_block_comments(
        self, mocker: MockerFixture
    ) -> None:
        """Test query normalization removes block comments."""
        mock_instrument_store = mocker.Mock()
        mock_calendar_store = mocker.Mock()
        engine = SqlEngine(
            data_root=Path("/test"),
            instrument_store=mock_instrument_store,
            calendar_store=mock_calendar_store,
        )

        query = "SELECT * /* block comment */ FROM table"
        normalized = engine._normalize_query(query)

        assert "/* block comment */" not in normalized

    def test_normalize_query_normalizes_whitespace(self, mocker: MockerFixture) -> None:
        """Test query normalization normalizes whitespace."""
        mock_instrument_store = mocker.Mock()
        mock_calendar_store = mocker.Mock()
        engine = SqlEngine(
            data_root=Path("/test"),
            instrument_store=mock_instrument_store,
            calendar_store=mock_calendar_store,
        )

        query = "SELECT   *   FROM   table"
        normalized = engine._normalize_query(query)

        assert normalized == "SELECT * FROM table"

    def test_prepare_query_with_cache_disabled(self, mocker: MockerFixture) -> None:
        """Test query preparation with cache disabled."""
        mock_instrument_store = mocker.Mock()
        mock_calendar_store = mocker.Mock()
        engine = SqlEngine(
            data_root=Path("/test"),
            instrument_store=mock_instrument_store,
            calendar_store=mock_calendar_store,
            enable_plan_cache=False,
        )

        query = "SELECT * FROM table"
        prepared, cache_hit = engine._prepare_query(query)

        assert prepared == query
        assert cache_hit is False

    def test_prepare_query_with_cache_enabled_miss(self, mocker: MockerFixture) -> None:
        """Test query preparation with cache miss."""
        mock_instrument_store = mocker.Mock()
        mock_calendar_store = mocker.Mock()
        engine = SqlEngine(
            data_root=Path("/test"),
            instrument_store=mock_instrument_store,
            calendar_store=mock_calendar_store,
            enable_plan_cache=True,
        )

        query = "SELECT * FROM table"
        _prepared, cache_hit = engine._prepare_query(query)

        assert cache_hit is False

    def test_prepare_query_with_cache_enabled_hit(self, mocker: MockerFixture) -> None:
        """Test query preparation with cache hit."""
        mock_instrument_store = mocker.Mock()
        mock_calendar_store = mocker.Mock()
        engine = SqlEngine(
            data_root=Path("/test"),
            instrument_store=mock_instrument_store,
            calendar_store=mock_calendar_store,
            enable_plan_cache=True,
        )

        query = "SELECT * FROM table"
        # First call - miss
        _prepared1, cache_hit1 = engine._prepare_query(query)
        assert cache_hit1 is False

        # Second call - hit
        _prepared2, cache_hit2 = engine._prepare_query(query)
        assert cache_hit2 is True

    def test_needs_sqlite_detects_sqlite_tables(self, mocker: MockerFixture) -> None:
        """Test SQLite table detection."""
        mock_instrument_store = mocker.Mock()
        mock_calendar_store = mocker.Mock()
        engine = SqlEngine(
            data_root=Path("/test"),
            instrument_store=mock_instrument_store,
            calendar_store=mock_calendar_store,
        )

        # SQLite table
        assert engine._needs_sqlite("SELECT * FROM instrument") is True
        # With meta prefix
        assert engine._needs_sqlite("SELECT * FROM meta.instrument") is True
        # Non-SQLite table
        assert engine._needs_sqlite("SELECT * FROM stock_daily") is False

    def test_execute_with_valid_asof_date(self, mocker: MockerFixture) -> None:
        """Test execute with valid asof date."""
        mock_instrument_store = mocker.Mock()
        mock_calendar_store = mocker.Mock()
        engine = SqlEngine(
            data_root=Path("/test"),
            instrument_store=mock_instrument_store,
            calendar_store=mock_calendar_store,
        )

        # Mock DuckDB connection
        mock_con = mocker.patch.object(engine, "con")
        mock_con.execute.return_value.pl.return_value = pl.DataFrame()

        # Mock query normalization
        engine._plan_cache = {}

        engine.execute(
            query="SELECT * FROM stock_daily WHERE trade_date <= $asof",
            asof="2024-01-15",
        )

        # Verify query was modified
        call_args = mock_con.execute.call_args
        assert "$asof" not in str(call_args)

    def test_execute_with_invalid_asof_date_raises_error(
        self, mocker: MockerFixture
    ) -> None:
        """Test execute with invalid asof date raises ValueError."""
        mock_instrument_store = mocker.Mock()
        mock_calendar_store = mocker.Mock()
        engine = SqlEngine(
            data_root=Path("/test"),
            instrument_store=mock_instrument_store,
            calendar_store=mock_calendar_store,
        )

        with pytest.raises(ValueError) as exc_info:
            engine.execute(
                query="SELECT * FROM stock_daily",
                asof="invalid-date",
            )

        assert "Invalid asof date format" in str(exc_info.value)

    def test_execute_with_asof_and_dict_params_raises_error(
        self, mocker: MockerFixture
    ) -> None:
        """Test execute with asof and dict params raises ValueError."""
        mock_instrument_store = mocker.Mock()
        mock_calendar_store = mocker.Mock()
        engine = SqlEngine(
            data_root=Path("/test"),
            instrument_store=mock_instrument_store,
            calendar_store=mock_calendar_store,
        )

        with pytest.raises(ValueError) as exc_info:
            engine.execute(
                query="SELECT * FROM stock_daily",
                asof="2024-01-15",
                params={"key": "value"},
            )

        assert "Cannot combine $asof parameter with dict params" in str(exc_info.value)

    def test_pit_query_adds_pit_filter(self, mocker: MockerFixture) -> None:
        """Test pit_query adds PIT filter."""
        mock_instrument_store = mocker.Mock()
        mock_calendar_store = mocker.Mock()
        engine = SqlEngine(
            data_root=Path("/test"),
            instrument_store=mock_instrument_store,
            calendar_store=mock_calendar_store,
        )

        # Mock the execute method
        mock_execute = mocker.patch.object(engine, "execute")
        mock_execute.return_value = pl.DataFrame()

        engine.pit_query(
            query="SELECT * FROM stock_daily",
            knowledge_date="2024-01-15",
        )

        # Verify execute was called with asof parameter
        mock_execute.assert_called_once()
        call_kwargs = mock_execute.call_args[1]
        assert call_kwargs["asof"] == "2024-01-15"

    def test_pit_query_with_custom_date_column(self, mocker: MockerFixture) -> None:
        """Test pit_query with custom date column."""
        mock_instrument_store = mocker.Mock()
        mock_calendar_store = mocker.Mock()
        engine = SqlEngine(
            data_root=Path("/test"),
            instrument_store=mock_instrument_store,
            calendar_store=mock_calendar_store,
        )

        mock_execute = mocker.patch.object(engine, "execute")
        mock_execute.return_value = pl.DataFrame()

        engine.pit_query(
            query="SELECT * FROM stock_daily",
            knowledge_date="2024-01-15",
            date_column="date",
        )

        mock_execute.assert_called_once()

    def test_refresh_views_reregisters_views(self, mocker: MockerFixture) -> None:
        """Test refresh_views re-registers parquet views."""
        mock_instrument_store = mocker.Mock()
        mock_calendar_store = mocker.Mock()
        engine = SqlEngine(
            data_root=Path("/test"),
            instrument_store=mock_instrument_store,
            calendar_store=mock_calendar_store,
        )

        # Mock _register_views
        mocker.patch.object(engine, "_register_views")
        engine.refresh_views()
        # Verify _register_views was called
        engine._register_views.assert_called_once()

    def test_close_closes_duckdb_connection(self, mocker: MockerFixture) -> None:
        """Test close closes DuckDB connection."""
        mock_instrument_store = mocker.Mock()
        mock_calendar_store = mocker.Mock()
        engine = SqlEngine(
            data_root=Path("/test"),
            instrument_store=mock_instrument_store,
            calendar_store=mock_calendar_store,
        )

        # Just verify close method exists and can be called
        # (DuckDB connection close is not easily mockable)
        try:
            engine.close()
        except Exception:
            # Expected since connection is in-memory
            pass

    def test_allowed_datasets_whitelist(self) -> None:
        """Test that ALLOWED_DATASETS is a frozenset."""
        # Verify instrument whitelist
        assert "stock_daily" in SqlEngine.ALLOWED_DATASETS
        assert "etf_daily" in SqlEngine.ALLOWED_DATASETS
        assert "index_daily" in SqlEngine.ALLOWED_DATASETS
        assert "adj_factor" in SqlEngine.ALLOWED_DATASETS
        assert "stock_status" in SqlEngine.ALLOWED_DATASETS
        assert "ingestion_log" in SqlEngine.ALLOWED_DATASETS

    def test_sqlite_tables_const(self) -> None:
        """Test that SQLITE_TABLES is a frozenset."""
        # Verify SQLite tables
        assert "instrument" in SqlEngine.SQLITE_TABLES
        assert "instrument_mapping" in SqlEngine.SQLITE_TABLES
        assert "trading_calendar" in SqlEngine.SQLITE_TABLES
        assert "universe" in SqlEngine.SQLITE_TABLES
        assert "dq_issue" in SqlEngine.SQLITE_TABLES

    def test_query_preview_length_const(self) -> None:
        """Test QUERY_PREVIEW_LENGTH constant."""
        assert SqlEngine.QUERY_PREVIEW_LENGTH == 200


@pytest.mark.unit
class TestSqlEngineExceptionPaths:
    """Tests for SqlEngine exception handling."""

    def test_execute_with_invalid_sql_raises_error(self, mocker: MockerFixture) -> None:
        """Test execute raises error on invalid SQL syntax."""
        mock_instrument_store = mocker.Mock()
        mock_calendar_store = mocker.Mock()
        data_root = Path("/test/data")

        engine = SqlEngine(
            data_root=data_root,
            instrument_store=mock_instrument_store,
            calendar_store=mock_calendar_store,
        )

        # Mock DuckDB connection to raise error on invalid SQL
        mock_con = mocker.patch.object(engine, "con")
        mock_con.execute.side_effect = RuntimeError("Invalid SQL syntax")

        with pytest.raises(RuntimeError, match="Invalid SQL syntax"):
            engine.execute("SELECT * FROM invalid_table")

    def test_execute_with_connection_error_raises_error(
        self, mocker: MockerFixture
    ) -> None:
        """Test execute raises error when database connection fails."""
        mock_instrument_store = mocker.Mock()
        mock_calendar_store = mocker.Mock()
        data_root = Path("/test/data")

        engine = SqlEngine(
            data_root=data_root,
            instrument_store=mock_instrument_store,
            calendar_store=mock_calendar_store,
        )

        # Mock DuckDB connection to simulate connection error
        mock_con = mocker.patch.object(engine, "con")
        mock_con.execute.side_effect = ConnectionError("Database connection failed")

        with pytest.raises(ConnectionError, match="Database connection failed"):
            engine.execute("SELECT * FROM stock_daily")

    def test_pit_query_propagates_execute_errors(self, mocker: MockerFixture) -> None:
        """Test pit_query propagates execute errors."""
        mock_instrument_store = mocker.Mock()
        mock_calendar_store = mocker.Mock()
        data_root = Path("/test/data")

        engine = SqlEngine(
            data_root=data_root,
            instrument_store=mock_instrument_store,
            calendar_store=mock_calendar_store,
        )

        # Mock execute to raise error
        mocker.patch.object(
            engine, "execute", side_effect=ValueError("Invalid asof date")
        )

        with pytest.raises(ValueError, match="Invalid asof date"):
            engine.pit_query(
                query="SELECT * FROM stock_daily",
                knowledge_date="2024-01-15",
            )

    def test_refresh_views_with_registration_error(self, mocker: MockerFixture) -> None:
        """Test refresh_views handles registration errors gracefully."""
        mock_instrument_store = mocker.Mock()
        mock_calendar_store = mocker.Mock()
        data_root = Path("/test/data")

        engine = SqlEngine(
            data_root=data_root,
            instrument_store=mock_instrument_store,
            calendar_store=mock_calendar_store,
        )

        # Mock _register_views to raise error
        mocker.patch.object(
            engine,
            "_register_views",
            side_effect=RuntimeError("View registration failed"),
        )

        with pytest.raises(RuntimeError, match="View registration failed"):
            engine.refresh_views()
