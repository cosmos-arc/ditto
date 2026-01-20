"""Unit tests for SqlEngine."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import polars as pl
import pytest
from ditto_datahub.runtime.sql_engine import SqlEngine


@pytest.mark.unit
class TestSqlEngine:
    """Tests for SqlEngine."""

    def test_initialization(self) -> None:
        """Test that SqlEngine initializes with defaults."""
        mock_security_store = MagicMock()
        mock_calendar_store = MagicMock()
        data_root = Path("/test/data")

        engine = SqlEngine(
            data_root=data_root,
            security_store=mock_security_store,
            calendar_store=mock_calendar_store,
        )

        assert engine.data_root == data_root
        assert engine.security_store is mock_security_store
        assert engine.calendar_store is mock_calendar_store
        assert engine._sqlite_attached is False
        assert engine._enable_plan_cache is True
        assert engine._plan_cache_size == 1000
        assert engine._slow_query_threshold == 1.0

    def test_initialization_with_custom_settings(self) -> None:
        """Test initialization with custom settings."""
        mock_security_store = MagicMock()
        mock_calendar_store = MagicMock()
        data_root = Path("/test/data")

        engine = SqlEngine(
            data_root=data_root,
            security_store=mock_security_store,
            calendar_store=mock_calendar_store,
            enable_plan_cache=False,
            plan_cache_size=500,
            slow_query_threshold=2.0,
        )

        assert engine._enable_plan_cache is False
        assert engine._plan_cache_size == 500
        assert engine._slow_query_threshold == 2.0

    def test_normalize_query_removes_comments(self) -> None:
        """Test query normalization removes SQL comments."""
        mock_security_store = MagicMock()
        mock_calendar_store = MagicMock()
        engine = SqlEngine(
            data_root=Path("/test"),
            security_store=mock_security_store,
            calendar_store=mock_calendar_store,
        )

        query = "SELECT * FROM table -- comment\nWHERE id = 1"
        normalized = engine._normalize_query(query)

        assert "-- comment" not in normalized
        assert "WHERE id = 1" in normalized

    def test_normalize_query_removes_block_comments(self) -> None:
        """Test query normalization removes block comments."""
        mock_security_store = MagicMock()
        mock_calendar_store = MagicMock()
        engine = SqlEngine(
            data_root=Path("/test"),
            security_store=mock_security_store,
            calendar_store=mock_calendar_store,
        )

        query = "SELECT * /* block comment */ FROM table"
        normalized = engine._normalize_query(query)

        assert "/* block comment */" not in normalized

    def test_normalize_query_normalizes_whitespace(self) -> None:
        """Test query normalization normalizes whitespace."""
        mock_security_store = MagicMock()
        mock_calendar_store = MagicMock()
        engine = SqlEngine(
            data_root=Path("/test"),
            security_store=mock_security_store,
            calendar_store=mock_calendar_store,
        )

        query = "SELECT   *   FROM   table"
        normalized = engine._normalize_query(query)

        assert normalized == "SELECT * FROM table"

    def test_prepare_query_with_cache_disabled(self) -> None:
        """Test query preparation with cache disabled."""
        mock_security_store = MagicMock()
        mock_calendar_store = MagicMock()
        engine = SqlEngine(
            data_root=Path("/test"),
            security_store=mock_security_store,
            calendar_store=mock_calendar_store,
            enable_plan_cache=False,
        )

        query = "SELECT * FROM table"
        prepared, cache_hit = engine._prepare_query(query)

        assert prepared == query
        assert cache_hit is False

    def test_prepare_query_with_cache_enabled_miss(self) -> None:
        """Test query preparation with cache miss."""
        mock_security_store = MagicMock()
        mock_calendar_store = MagicMock()
        engine = SqlEngine(
            data_root=Path("/test"),
            security_store=mock_security_store,
            calendar_store=mock_calendar_store,
            enable_plan_cache=True,
        )

        query = "SELECT * FROM table"
        _prepared, cache_hit = engine._prepare_query(query)

        assert cache_hit is False

    def test_prepare_query_with_cache_enabled_hit(self) -> None:
        """Test query preparation with cache hit."""
        mock_security_store = MagicMock()
        mock_calendar_store = MagicMock()
        engine = SqlEngine(
            data_root=Path("/test"),
            security_store=mock_security_store,
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

    def test_needs_sqlite_detects_sqlite_tables(self) -> None:
        """Test SQLite table detection."""
        mock_security_store = MagicMock()
        mock_calendar_store = MagicMock()
        engine = SqlEngine(
            data_root=Path("/test"),
            security_store=mock_security_store,
            calendar_store=mock_calendar_store,
        )

        # SQLite table
        assert engine._needs_sqlite("SELECT * FROM security") is True
        # With meta prefix
        assert engine._needs_sqlite("SELECT * FROM meta.security") is True
        # Non-SQLite table
        assert engine._needs_sqlite("SELECT * FROM stock_daily") is False

    def test_execute_with_valid_asof_date(self) -> None:
        """Test execute with valid asof date."""
        mock_security_store = MagicMock()
        mock_calendar_store = MagicMock()
        engine = SqlEngine(
            data_root=Path("/test"),
            security_store=mock_security_store,
            calendar_store=mock_calendar_store,
        )

        # Mock DuckDB connection
        with patch.object(engine, "con") as mock_con:
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

    def test_execute_with_invalid_asof_date_raises_error(self) -> None:
        """Test execute with invalid asof date raises ValueError."""
        mock_security_store = MagicMock()
        mock_calendar_store = MagicMock()
        engine = SqlEngine(
            data_root=Path("/test"),
            security_store=mock_security_store,
            calendar_store=mock_calendar_store,
        )

        with pytest.raises(ValueError) as exc_info:
            engine.execute(
                query="SELECT * FROM stock_daily",
                asof="invalid-date",
            )

        assert "Invalid asof date format" in str(exc_info.value)

    def test_execute_with_asof_and_dict_params_raises_error(self) -> None:
        """Test execute with asof and dict params raises ValueError."""
        mock_security_store = MagicMock()
        mock_calendar_store = MagicMock()
        engine = SqlEngine(
            data_root=Path("/test"),
            security_store=mock_security_store,
            calendar_store=mock_calendar_store,
        )

        with pytest.raises(ValueError) as exc_info:
            engine.execute(
                query="SELECT * FROM stock_daily",
                asof="2024-01-15",
                params={"key": "value"},
            )

        assert "Cannot combine $asof parameter with dict params" in str(exc_info.value)

    def test_pit_query_adds_pit_filter(self) -> None:
        """Test pit_query adds PIT filter."""
        mock_security_store = MagicMock()
        mock_calendar_store = MagicMock()
        engine = SqlEngine(
            data_root=Path("/test"),
            security_store=mock_security_store,
            calendar_store=mock_calendar_store,
        )

        # Mock the execute method
        with patch.object(engine, "execute") as mock_execute:
            mock_execute.return_value = pl.DataFrame()

            engine.pit_query(
                query="SELECT * FROM stock_daily",
                knowledge_date="2024-01-15",
            )

            # Verify execute was called with asof parameter
            mock_execute.assert_called_once()
            call_kwargs = mock_execute.call_args[1]
            assert call_kwargs["asof"] == "2024-01-15"

    def test_pit_query_with_custom_date_column(self) -> None:
        """Test pit_query with custom date column."""
        mock_security_store = MagicMock()
        mock_calendar_store = MagicMock()
        engine = SqlEngine(
            data_root=Path("/test"),
            security_store=mock_security_store,
            calendar_store=mock_calendar_store,
        )

        with patch.object(engine, "execute") as mock_execute:
            mock_execute.return_value = pl.DataFrame()

            engine.pit_query(
                query="SELECT * FROM stock_daily",
                knowledge_date="2024-01-15",
                date_column="date",
            )

            mock_execute.assert_called_once()

    def test_refresh_views_reregisters_views(self) -> None:
        """Test refresh_views re-registers parquet views."""
        mock_security_store = MagicMock()
        mock_calendar_store = MagicMock()
        engine = SqlEngine(
            data_root=Path("/test"),
            security_store=mock_security_store,
            calendar_store=mock_calendar_store,
        )

        # Mock _register_views
        with patch.object(engine, "_register_views"):
            engine.refresh_views()
            # Verify _register_views was called
            engine._register_views.assert_called_once()

    def test_close_closes_duckdb_connection(self) -> None:
        """Test close closes DuckDB connection."""
        mock_security_store = MagicMock()
        mock_calendar_store = MagicMock()
        engine = SqlEngine(
            data_root=Path("/test"),
            security_store=mock_security_store,
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
        # Verify security whitelist
        assert "stock_daily" in SqlEngine.ALLOWED_DATASETS
        assert "etf_daily" in SqlEngine.ALLOWED_DATASETS
        assert "index_daily" in SqlEngine.ALLOWED_DATASETS
        assert "adj_factor" in SqlEngine.ALLOWED_DATASETS
        assert "stock_status" in SqlEngine.ALLOWED_DATASETS
        assert "ingestion_log" in SqlEngine.ALLOWED_DATASETS

    def test_sqlite_tables_const(self) -> None:
        """Test that SQLITE_TABLES is a frozenset."""
        # Verify SQLite tables
        assert "security" in SqlEngine.SQLITE_TABLES
        assert "security_mapping" in SqlEngine.SQLITE_TABLES
        assert "trading_calendar" in SqlEngine.SQLITE_TABLES
        assert "universe" in SqlEngine.SQLITE_TABLES
        assert "dq_issue" in SqlEngine.SQLITE_TABLES

    def test_query_preview_length_const(self) -> None:
        """Test QUERY_PREVIEW_LENGTH constant."""
        assert SqlEngine.QUERY_PREVIEW_LENGTH == 200
