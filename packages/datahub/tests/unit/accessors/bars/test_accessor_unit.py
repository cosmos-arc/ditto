"""Unit tests for BarsAccessor."""

from datetime import date
from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_datahub.accessors.bars.accessor import AdjType, BarsAccessor, BarsQuery
from ditto_datahub.models import WriteResult


@pytest.mark.unit
class TestBarsQuery:
    """Tests for BarsQuery dataclass."""

    def test_create_query_with_defaults(self) -> None:
        """Test creating BarsQuery with default values."""
        query = BarsQuery(sids=[1, 2, 3])

        assert query.sids == [1, 2, 3]
        assert query.adj == AdjType.NONE
        assert query.with_symbol is False
        assert query.with_status is False
        assert query.raw is False

    def test_create_query_with_all_params(self) -> None:
        """Test creating BarsQuery with all parameters."""
        query = BarsQuery(
            sids=[1, 2, 3],
            start="2024-01-01",
            end="2024-01-31",
            adj=AdjType.QFQ,
            asof="2024-01-15",
            asset_class="stock",
            with_symbol=True,
            with_status=True,
            raw=False,
        )

        assert query.sids == [1, 2, 3]
        assert query.start == "2024-01-01"
        assert query.end == "2024-01-31"
        assert query.adj == AdjType.QFQ
        assert query.asof == "2024-01-15"
        assert query.asset_class == "stock"
        assert query.with_symbol is True
        assert query.with_status is True

    def test_create_query_for_etf(self) -> None:
        """Test creating query for ETF asset class."""
        query = BarsQuery(
            sids=[2_000_001],
            asset_class="etf",
        )

        assert query.asset_class == "etf"

    def test_adj_type_enum_values(self) -> None:
        """Test AdjType enum values."""
        assert AdjType.NONE.value == "none"
        assert AdjType.QFQ.value == "qfq"
        assert AdjType.HFQ.value == "hfq"


@pytest.mark.unit
class TestBarsAccessor:
    """Tests for BarsAccessor."""

    def test_initialization(self) -> None:
        """Test that BarsAccessor initializes with all dependencies."""
        mock_bars_store = MagicMock()
        mock_adj_store = MagicMock()
        mock_security_store = MagicMock()
        mock_status_store = MagicMock()
        mock_dq_engine = MagicMock()
        mock_file_lock = MagicMock()
        mock_quarantine_store = MagicMock()

        accessor = BarsAccessor(
            bars_store=mock_bars_store,
            adj_factor_store=mock_adj_store,
            security_store=mock_security_store,
            stock_status_store=mock_status_store,
            dq_engine=mock_dq_engine,
            file_lock=mock_file_lock,
            quarantine_store=mock_quarantine_store,
        )

        assert accessor._bars_store is mock_bars_store
        assert accessor._adj_factor_store is mock_adj_store
        assert accessor._security_store is mock_security_store

    def test_get_returns_empty_for_unresolvable_sid(self) -> None:
        """Test that get returns empty DataFrame when SID cannot be resolved."""
        mock_bars_store = MagicMock()
        mock_adj_store = MagicMock()
        mock_security_store = MagicMock()
        mock_status_store = MagicMock()
        mock_dq_engine = MagicMock()
        mock_file_lock = MagicMock()
        mock_quarantine_store = MagicMock()

        # Mock resolve_sids_batch to return empty
        mock_security_store.resolve_sids_batch.return_value = {}
        mock_security_store.resolve_by_symbol.return_value = []

        accessor = BarsAccessor(
            bars_store=mock_bars_store,
            adj_factor_store=mock_adj_store,
            security_store=mock_security_store,
            stock_status_store=mock_status_store,
            dq_engine=mock_dq_engine,
            file_lock=mock_file_lock,
            quarantine_store=mock_quarantine_store,
        )

        query = BarsQuery(src_codes=["INVALID.XYZ"])

        result = accessor.get(query)

        # Should return empty DataFrame
        assert result.is_empty()

    def test_get_with_valid_sids(self) -> None:
        """Test that get returns data for valid SIDs."""
        mock_bars_store = MagicMock()
        mock_adj_store = MagicMock()
        mock_security_store = MagicMock()
        mock_status_store = MagicMock()
        mock_dq_engine = MagicMock()
        mock_file_lock = MagicMock()
        mock_quarantine_store = MagicMock()

        # Mock returns
        mock_df = pl.DataFrame(
            {
                "sid": [1, 1],
                "trade_date": ["2024-01-01", "2024-01-02"],
                "close": [10.0, 11.0],
            }
        )
        mock_bars_store.read.return_value = mock_df

        accessor = BarsAccessor(
            bars_store=mock_bars_store,
            adj_factor_store=mock_adj_store,
            security_store=mock_security_store,
            stock_status_store=mock_status_store,
            dq_engine=mock_dq_engine,
            file_lock=mock_file_lock,
            quarantine_store=mock_quarantine_store,
        )

        query = BarsQuery(sids=[1], start="2024-01-01", end="2024-01-31")

        accessor.get(query)

        # Verify bars_store.read was called
        mock_bars_store.read.assert_called_once()

    def test_get_single_with_src_code(self) -> None:
        """Test get_single resolves src_code to SID."""
        mock_bars_store = MagicMock()
        mock_adj_store = MagicMock()
        mock_security_store = MagicMock()
        mock_status_store = MagicMock()
        mock_dq_engine = MagicMock()
        mock_file_lock = MagicMock()
        mock_quarantine_store = MagicMock()

        # Mock SID resolution
        mock_security_store.resolve_sid.return_value = 123
        mock_bars_store.read.return_value = pl.DataFrame()

        accessor = BarsAccessor(
            bars_store=mock_bars_store,
            adj_factor_store=mock_adj_store,
            security_store=mock_security_store,
            stock_status_store=mock_status_store,
            dq_engine=mock_dq_engine,
            file_lock=mock_file_lock,
            quarantine_store=mock_quarantine_store,
        )

        accessor.get_single(
            identifier="600000.SH",
            start="2024-01-01",
            end="2024-01-31",
        )

        # Verify resolve_sid was called
        mock_security_store.resolve_sid.assert_called_once()

    def test_get_single_with_symbol_fallback(self) -> None:
        """Test get_single falls back to symbol when src_code fails."""
        mock_bars_store = MagicMock()
        mock_adj_store = MagicMock()
        mock_security_store = MagicMock()
        mock_status_store = MagicMock()
        mock_dq_engine = MagicMock()
        mock_file_lock = MagicMock()
        mock_quarantine_store = MagicMock()

        # Mock src_code resolution fails, symbol succeeds
        mock_security_store.resolve_sid.return_value = None
        mock_security_store.resolve_by_symbol.return_value = [456]
        mock_bars_store.read.return_value = pl.DataFrame()

        accessor = BarsAccessor(
            bars_store=mock_bars_store,
            adj_factor_store=mock_adj_store,
            security_store=mock_security_store,
            stock_status_store=mock_status_store,
            dq_engine=mock_dq_engine,
            file_lock=mock_file_lock,
            quarantine_store=mock_quarantine_store,
        )

        accessor.get_single(
            identifier="600000",
            start="2024-01-01",
            end="2024-01-31",
        )

        # Verify symbol resolution was called as fallback
        mock_security_store.resolve_by_symbol.assert_called_once()

    def test_write_without_dq_check(self) -> None:
        """Test write without DQ check."""
        mock_bars_store = MagicMock()
        mock_adj_store = MagicMock()
        mock_security_store = MagicMock()
        mock_status_store = MagicMock()
        mock_dq_engine = MagicMock()
        mock_file_lock = MagicMock()
        mock_quarantine_store = MagicMock()

        # Mock write result
        mock_bars_store.write.return_value = WriteResult(
            file_path="/data/stock_daily/2024.parquet",
            checksum="abc123",
            rows_written=100,
            rows_total=1000,
            blocked=False,
            dq_result=None,
        )
        mock_bars_store.read.return_value = pl.DataFrame({"sid": range(1000)})

        accessor = BarsAccessor(
            bars_store=mock_bars_store,
            adj_factor_store=mock_adj_store,
            security_store=mock_security_store,
            stock_status_store=mock_status_store,
            dq_engine=mock_dq_engine,
            file_lock=mock_file_lock,
            quarantine_store=mock_quarantine_store,
        )

        df = pl.DataFrame({"sid": range(100)})
        result = accessor.write(df, year=2024, run_dq_check=False)

        # Verify write was called
        mock_bars_store.write.assert_called_once()
        assert result.blocked is False

    def test_write_with_dq_check_passed(self) -> None:
        """Test write with DQ check that passes."""
        mock_bars_store = MagicMock()
        mock_adj_store = MagicMock()
        mock_security_store = MagicMock()
        mock_status_store = MagicMock()
        mock_dq_engine = MagicMock()
        mock_file_lock = MagicMock()
        mock_quarantine_store = MagicMock()

        # Mock DQ engine - check passes
        mock_dq_result = MagicMock()
        mock_dq_result.has_errors = False
        mock_dq_result.has_warnings = False
        mock_dq_result.passed = True
        mock_dq_engine.check.return_value = mock_dq_result

        mock_bars_store.write.return_value = WriteResult(
            file_path="/data/stock_daily/2024.parquet",
            checksum="abc123",
            rows_written=100,
            rows_total=1000,
            blocked=False,
            dq_result=mock_dq_result,
        )
        mock_bars_store.read.return_value = pl.DataFrame({"sid": range(1000)})

        accessor = BarsAccessor(
            bars_store=mock_bars_store,
            adj_factor_store=mock_adj_store,
            security_store=mock_security_store,
            stock_status_store=mock_status_store,
            dq_engine=mock_dq_engine,
            file_lock=mock_file_lock,
            quarantine_store=mock_quarantine_store,
        )

        df = pl.DataFrame({"sid": range(100)})
        result = accessor.write(df, year=2024, run_dq_check=True)

        # Verify DQ check was run
        mock_dq_engine.check.assert_called_once()
        assert result.blocked is False

    def test_write_with_dq_check_blocked(self) -> None:
        """Test write with DQ check that blocks."""
        mock_bars_store = MagicMock()
        mock_adj_store = MagicMock()
        mock_security_store = MagicMock()
        mock_status_store = MagicMock()
        mock_dq_engine = MagicMock()
        mock_file_lock = MagicMock()
        mock_quarantine_store = MagicMock()

        # Mock DQ engine - check fails with errors
        mock_issue = MagicMock()
        mock_issue.rule_name = "not_null"
        mock_issue.severity.value = "error"
        mock_dq_result = MagicMock()
        mock_dq_result.has_errors = True
        mock_dq_result.error_count = 5
        mock_dq_result.issues = [mock_issue]
        mock_dq_engine.check.return_value = mock_dq_result

        accessor = BarsAccessor(
            bars_store=mock_bars_store,
            adj_factor_store=mock_adj_store,
            security_store=mock_security_store,
            stock_status_store=mock_status_store,
            dq_engine=mock_dq_engine,
            file_lock=mock_file_lock,
            quarantine_store=mock_quarantine_store,
        )

        df = pl.DataFrame({"sid": range(100)})
        result = accessor.write(df, year=2024, run_dq_check=True)

        # Verify write was blocked
        assert result.blocked is True
        assert result.rows_written == 0

    def test_detect_asset_class_from_sids_stock(self) -> None:
        """Test detecting stock asset class from SIDs."""
        mock_bars_store = MagicMock()
        mock_adj_store = MagicMock()
        mock_security_store = MagicMock()
        mock_status_store = MagicMock()
        mock_dq_engine = MagicMock()
        mock_file_lock = MagicMock()
        mock_quarantine_store = MagicMock()

        accessor = BarsAccessor(
            bars_store=mock_bars_store,
            adj_factor_store=mock_adj_store,
            security_store=mock_security_store,
            stock_status_store=mock_status_store,
            dq_engine=mock_dq_engine,
            file_lock=mock_file_lock,
            quarantine_store=mock_quarantine_store,
        )

        asset_class = accessor._detect_asset_class_from_sids([1_000_001, 1_000_002])
        assert asset_class == "stock"

    def test_detect_asset_class_from_sids_etf(self) -> None:
        """Test detecting ETF asset class from SIDs."""
        mock_bars_store = MagicMock()
        mock_adj_store = MagicMock()
        mock_security_store = MagicMock()
        mock_status_store = MagicMock()
        mock_dq_engine = MagicMock()
        mock_file_lock = MagicMock()
        mock_quarantine_store = MagicMock()

        accessor = BarsAccessor(
            bars_store=mock_bars_store,
            adj_factor_store=mock_adj_store,
            security_store=mock_security_store,
            stock_status_store=mock_status_store,
            dq_engine=mock_dq_engine,
            file_lock=mock_file_lock,
            quarantine_store=mock_quarantine_store,
        )

        asset_class = accessor._detect_asset_class_from_sids([2_000_001, 2_000_002])
        assert asset_class == "etf"

    def test_detect_asset_class_from_sids_index(self) -> None:
        """Test detecting index asset class from SIDs."""
        mock_bars_store = MagicMock()
        mock_adj_store = MagicMock()
        mock_security_store = MagicMock()
        mock_status_store = MagicMock()
        mock_dq_engine = MagicMock()
        mock_file_lock = MagicMock()
        mock_quarantine_store = MagicMock()

        accessor = BarsAccessor(
            bars_store=mock_bars_store,
            adj_factor_store=mock_adj_store,
            security_store=mock_security_store,
            stock_status_store=mock_status_store,
            dq_engine=mock_dq_engine,
            file_lock=mock_file_lock,
            quarantine_store=mock_quarantine_store,
        )

        asset_class = accessor._detect_asset_class_from_sids([3_000_001, 3_000_002])
        assert asset_class == "index"

    def test_detect_asset_class_raises_on_mixed(self) -> None:
        """Test detecting mixed asset classes raises ValueError."""
        mock_bars_store = MagicMock()
        mock_adj_store = MagicMock()
        mock_security_store = MagicMock()
        mock_status_store = MagicMock()
        mock_dq_engine = MagicMock()
        mock_file_lock = MagicMock()
        mock_quarantine_store = MagicMock()

        accessor = BarsAccessor(
            bars_store=mock_bars_store,
            adj_factor_store=mock_adj_store,
            security_store=mock_security_store,
            stock_status_store=mock_status_store,
            dq_engine=mock_dq_engine,
            file_lock=mock_file_lock,
            quarantine_store=mock_quarantine_store,
        )

        with pytest.raises(ValueError) as exc_info:
            accessor._detect_asset_class_from_sids([1_000_001, 2_000_001])

        assert "混合资产类别" in str(exc_info.value)

    def test_resolve_query_with_sids(self) -> None:
        """Test _resolve_query with SID list."""
        mock_bars_store = MagicMock()
        mock_adj_store = MagicMock()
        mock_security_store = MagicMock()
        mock_status_store = MagicMock()
        mock_dq_engine = MagicMock()
        mock_file_lock = MagicMock()
        mock_quarantine_store = MagicMock()

        accessor = BarsAccessor(
            bars_store=mock_bars_store,
            adj_factor_store=mock_adj_store,
            security_store=mock_security_store,
            stock_status_store=mock_status_store,
            dq_engine=mock_dq_engine,
            file_lock=mock_file_lock,
            quarantine_store=mock_quarantine_store,
        )

        query = BarsQuery(sids=[1, 2, 3], start="2024-01-01", end="2024-01-31")
        resolved = accessor._resolve_query(query)

        assert resolved.sids == [1, 2, 3]
        assert resolved.start == date(2024, 1, 1)
        assert resolved.end == date(2024, 1, 31)

    def test_resolve_query_with_src_codes(self) -> None:
        """Test _resolve_query with src_codes."""
        mock_bars_store = MagicMock()
        mock_adj_store = MagicMock()
        mock_security_store = MagicMock()
        mock_status_store = MagicMock()
        mock_dq_engine = MagicMock()
        mock_file_lock = MagicMock()
        mock_quarantine_store = MagicMock()

        # Mock src_code resolution
        mock_security_store.resolve_sids_batch.return_value = {
            "600000.SH": 1,
            "600001.SH": 2,
        }

        accessor = BarsAccessor(
            bars_store=mock_bars_store,
            adj_factor_store=mock_adj_store,
            security_store=mock_security_store,
            stock_status_store=mock_status_store,
            dq_engine=mock_dq_engine,
            file_lock=mock_file_lock,
            quarantine_store=mock_quarantine_store,
        )

        query = BarsQuery(src_codes=["600000.SH", "600001.SH"])
        resolved = accessor._resolve_query(query)

        assert sorted(resolved.sids) == [1, 2]
