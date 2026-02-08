"""Unit tests for MarketService."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_datahub.domains.market.market_service import (
    AdjType,
    MarketBarsQuery,
    MarketConstituentsQuery,
    MarketService,
    MarketWriteCommand,
)
from ditto_datahub.models import InstrumentIdRange


@pytest.fixture
def mock_stock_bars_store() -> MagicMock:
    """Create mock StockBarsStore."""
    return MagicMock()


@pytest.fixture
def mock_stock_status_store() -> MagicMock:
    """Create mock StockStatusStore."""
    return MagicMock()


@pytest.fixture
def mock_stock_adj_store() -> MagicMock:
    """Create mock StockAdjFactorStore."""
    return MagicMock()


@pytest.fixture
def mock_etf_bars_store() -> MagicMock:
    """Create mock EtfBarsStore."""
    return MagicMock()


@pytest.fixture
def mock_etf_status_store() -> MagicMock:
    """Create mock EtfStatusStore."""
    return MagicMock()


@pytest.fixture
def mock_etf_nav_store() -> MagicMock:
    """Create mock EtfNavStore."""
    return MagicMock()


@pytest.fixture
def mock_etf_adj_store() -> MagicMock:
    """Create mock EtfAdjFactorStore."""
    return MagicMock()


@pytest.fixture
def mock_index_bars_store() -> MagicMock:
    """Create mock IndexBarsStore."""
    return MagicMock()


@pytest.fixture
def mock_index_constituent_store() -> MagicMock:
    """Create mock IndexConstituentStore."""
    return MagicMock()


@pytest.fixture
def mock_instrument_store() -> MagicMock:
    """Create mock InstrumentStore."""
    return MagicMock()


@pytest.fixture
def mock_file_lock() -> MagicMock:
    """Create mock FileLockManager."""
    return MagicMock()


@pytest.fixture
def market_service(
    mock_stock_bars_store: MagicMock,
    mock_stock_status_store: MagicMock,
    mock_stock_adj_store: MagicMock,
    mock_etf_bars_store: MagicMock,
    mock_etf_status_store: MagicMock,
    mock_index_constituent_store: MagicMock,
    mock_instrument_store: MagicMock,
    mock_file_lock: MagicMock,
) -> MarketService:
    """Create MarketService instance with mocked dependencies."""
    return MarketService(
        stock_bars_store=mock_stock_bars_store,
        stock_status_store=mock_stock_status_store,
        stock_adj_store=mock_stock_adj_store,
        etf_bars_store=mock_etf_bars_store,
        etf_status_store=mock_etf_status_store,
        instrument_store=mock_instrument_store,
        file_lock=mock_file_lock,
        etf_nav_store=None,
        etf_adj_store=None,
        index_bars_store=None,
        index_constituent_store=mock_index_constituent_store,
    )


@pytest.fixture
def market_service_without_optionals(
    mock_stock_bars_store: MagicMock,
    mock_stock_status_store: MagicMock,
    mock_stock_adj_store: MagicMock,
    mock_etf_bars_store: MagicMock,
    mock_etf_status_store: MagicMock,
    mock_instrument_store: MagicMock,
    mock_file_lock: MagicMock,
) -> MarketService:
    """Create MarketService instance without optional stores."""
    return MarketService(
        stock_bars_store=mock_stock_bars_store,
        stock_status_store=mock_stock_status_store,
        stock_adj_store=mock_stock_adj_store,
        etf_bars_store=mock_etf_bars_store,
        etf_status_store=mock_etf_status_store,
        instrument_store=mock_instrument_store,
        file_lock=mock_file_lock,
        etf_nav_store=None,
        etf_adj_store=None,
        index_bars_store=None,
        index_constituent_store=None,
    )


@pytest.fixture
def sample_stock_bars_df() -> pl.DataFrame:
    """Create sample stock bars DataFrame."""
    return pl.DataFrame(
        {
            "instrument_id": [1, 1, 2, 2],
            "trade_date": [
                date(2024, 1, 2),
                date(2024, 1, 3),
                date(2024, 1, 2),
                date(2024, 1, 3),
            ],
            "open": [10.0, 10.5, 20.0, 20.5],
            "high": [10.5, 11.0, 20.5, 21.0],
            "low": [9.5, 10.0, 19.5, 20.0],
            "close": [10.0, 10.5, 20.0, 20.5],
            "volume": [1000, 1100, 2000, 2100],
            "amount": [10000.0, 11550.0, 40000.0, 43050.0],
        }
    )


@pytest.fixture
def sample_adj_factor_df() -> pl.DataFrame:
    """Create sample adjustment factor DataFrame."""
    return pl.DataFrame(
        {
            "instrument_id": [1, 1, 2, 2],
            "trade_date": [
                date(2024, 1, 2),
                date(2024, 1, 3),
                date(2024, 1, 2),
                date(2024, 1, 3),
            ],
            "adj_factor": [1.0, 1.0, 1.0, 1.0],
            "knowledge_date": [
                date(2024, 1, 3),
                date(2024, 1, 4),
                date(2024, 1, 3),
                date(2024, 1, 4),
            ],
        }
    )


@pytest.fixture
def sample_status_df() -> pl.DataFrame:
    """Create sample stock status DataFrame."""
    return pl.DataFrame(
        {
            "instrument_id": [1, 1, 2, 2],
            "trade_date": [
                date(2024, 1, 2),
                date(2024, 1, 3),
                date(2024, 1, 2),
                date(2024, 1, 3),
            ],
            "is_suspended": [False, False, False, False],
            "suspend_timing": ["", "", "", ""],
            "is_st": [False, False, False, False],
            "st_type": ["", "", "", ""],
            "list_status": ["L", "L", "L", "L"],
        }
    )


class TestMarketBarsQuery:
    """Test suite for MarketBarsQuery."""

    def test_query_creation_with_default_values(self) -> None:
        """Test query creation with default values."""
        query = MarketBarsQuery(instrument_ids=[1, 2, 3])
        assert query.instrument_ids == [1, 2, 3]
        assert query.start is None
        assert query.end is None
        assert query.adj == AdjType.NONE
        assert query.asof is None
        assert query.asset_class is None
        assert query.with_symbol is False
        assert query.with_status is False
        assert query.raw is False

    def test_query_creation_with_values(self) -> None:
        """Test query creation with specified values."""
        query = MarketBarsQuery(
            instrument_ids=[1, 2],
            start="2024-01-01",
            end="2024-12-31",
            adj=AdjType.QFQ,
            asof="2024-06-30",
            asset_class="stock",
            with_symbol=True,
            with_status=True,
            raw=True,
        )
        assert query.instrument_ids == [1, 2]
        assert query.start == "2024-01-01"
        assert query.end == "2024-12-31"
        assert query.adj == AdjType.QFQ
        assert query.asof == "2024-06-30"
        assert query.asset_class == "stock"
        assert query.with_symbol is True
        assert query.with_status is True
        assert query.raw is True

    def test_query_is_frozen(self) -> None:
        """Test that query is frozen (immutable)."""
        from dataclasses import FrozenInstanceError

        query = MarketBarsQuery(instrument_ids=[1, 2])
        with pytest.raises(FrozenInstanceError):
            query.instrument_ids = [3, 4]  # type: ignore


class TestMarketServiceInit:
    """Test suite for MarketService initialization."""

    def test_init_with_all_stores(
        self,
        mock_stock_bars_store: MagicMock,
        mock_stock_status_store: MagicMock,
        mock_stock_adj_store: MagicMock,
        mock_etf_bars_store: MagicMock,
        mock_etf_status_store: MagicMock,
        mock_instrument_store: MagicMock,
        mock_file_lock: MagicMock,
    ) -> None:
        """Test initialization with all required stores."""
        service = MarketService(
            stock_bars_store=mock_stock_bars_store,
            stock_status_store=mock_stock_status_store,
            stock_adj_store=mock_stock_adj_store,
            etf_bars_store=mock_etf_bars_store,
            etf_status_store=mock_etf_status_store,
            instrument_store=mock_instrument_store,
            file_lock=mock_file_lock,
        )
        assert service._stock_bars_store is mock_stock_bars_store
        assert service._stock_status_store is mock_stock_status_store
        assert service._stock_adj_store is mock_stock_adj_store
        assert service._etf_bars_store is mock_etf_bars_store
        assert service._etf_status_store is mock_etf_status_store
        assert service._instrument_store is mock_instrument_store
        assert service._file_lock is mock_file_lock
        assert service._etf_nav_store is None
        assert service._etf_adj_store is None
        assert service._index_bars_store is None
        assert service._index_constituent_store is None

    def test_init_with_optional_stores(
        self,
        mock_stock_bars_store: MagicMock,
        mock_stock_status_store: MagicMock,
        mock_stock_adj_store: MagicMock,
        mock_etf_bars_store: MagicMock,
        mock_etf_status_store: MagicMock,
        mock_instrument_store: MagicMock,
        mock_etf_nav_store: MagicMock,
        mock_etf_adj_store: MagicMock,
        mock_index_bars_store: MagicMock,
        mock_index_constituent_store: MagicMock,
        mock_file_lock: MagicMock,
    ) -> None:
        """Test initialization with optional stores."""
        service = MarketService(
            stock_bars_store=mock_stock_bars_store,
            stock_status_store=mock_stock_status_store,
            stock_adj_store=mock_stock_adj_store,
            etf_bars_store=mock_etf_bars_store,
            etf_status_store=mock_etf_status_store,
            instrument_store=mock_instrument_store,
            file_lock=mock_file_lock,
            etf_nav_store=mock_etf_nav_store,
            etf_adj_store=mock_etf_adj_store,
            index_bars_store=mock_index_bars_store,
            index_constituent_store=mock_index_constituent_store,
        )
        assert service._etf_nav_store is mock_etf_nav_store
        assert service._etf_adj_store is mock_etf_adj_store
        assert service._index_bars_store is mock_index_bars_store
        assert service._index_constituent_store is mock_index_constituent_store


class TestMarketServiceGetBars:
    """Test suite for MarketService.get_bars()."""

    def test_get_bars_empty_sid_list(self, market_service: MarketService) -> None:
        """Test get_bars with empty Instrument ID list."""
        query = MarketBarsQuery(instrument_ids=[])
        result = market_service.get_bars(query)
        assert result.is_empty()

    def test_get_bars_stock_basic(
        self,
        market_service: MarketService,
        mock_stock_bars_store: MagicMock,
        sample_stock_bars_df: pl.DataFrame,
    ) -> None:
        """Test get_bars for stock data."""
        mock_stock_bars_store.read.return_value = sample_stock_bars_df

        query = MarketBarsQuery(
            instrument_ids=[1, 2], start="2024-01-01", end="2024-12-31"
        )
        result = market_service.get_bars(query)

        assert not result.is_empty()
        assert len(result) == 4
        mock_stock_bars_store.read.assert_called_once()

    def test_get_bars_stock_with_status(
        self,
        market_service: MarketService,
        mock_stock_bars_store: MagicMock,
        mock_stock_status_store: MagicMock,
        sample_stock_bars_df: pl.DataFrame,
        sample_status_df: pl.DataFrame,
    ) -> None:
        """Test get_bars with status enrichment."""
        mock_stock_bars_store.read.return_value = sample_stock_bars_df
        mock_stock_status_store.read.return_value = sample_status_df

        query = MarketBarsQuery(
            instrument_ids=[1, 2],
            with_status=True,
            start="2024-01-01",
            end="2024-12-31",
        )
        result = market_service.get_bars(query)

        assert not result.is_empty()
        mock_stock_status_store.read.assert_called_once()

    def test_get_bars_raw_mode_skips_enrichment(
        self,
        market_service: MarketService,
        mock_stock_bars_store: MagicMock,
        mock_stock_status_store: MagicMock,
        mock_stock_adj_store: MagicMock,
        sample_stock_bars_df: pl.DataFrame,
    ) -> None:
        """Test that raw mode skips adjustment and status enrichment."""
        mock_stock_bars_store.read.return_value = sample_stock_bars_df

        query = MarketBarsQuery(
            instrument_ids=[1, 2], with_status=True, adj=AdjType.QFQ, raw=True
        )
        result = market_service.get_bars(query)

        assert not result.is_empty()
        # In raw mode, adj and status stores should not be called
        mock_stock_adj_store.read.assert_not_called()
        mock_stock_status_store.read.assert_not_called()

    def test_get_bars_etf(
        self,
        market_service: MarketService,
        mock_etf_bars_store: MagicMock,
        sample_stock_bars_df: pl.DataFrame,
    ) -> None:
        """Test get_bars for ETF data."""
        mock_etf_bars_store.read.return_value = sample_stock_bars_df

        # 使用 ETF Instrument ID 范围 (2M+)
        etf_range = InstrumentIdRange.get_range("etf")
        query = MarketBarsQuery(
            instrument_ids=[etf_range.min_id, etf_range.min_id + 1],
            asset_class="etf",
        )
        result = market_service.get_bars(query)

        assert not result.is_empty()
        mock_etf_bars_store.read.assert_called_once()

    def test_get_bars_index_when_store_is_none(
        self, market_service: MarketService
    ) -> None:
        """Test get_bars for index when index store is None."""
        # 使用 Index Instrument ID 范围 (3M+)
        index_range = InstrumentIdRange.get_range("index")
        query = MarketBarsQuery(
            instrument_ids=[index_range.min_id], asset_class="index"
        )
        result = market_service.get_bars(query)

        # Should return empty DataFrame when store is None
        assert result.is_empty()


class TestMarketServiceAssetClassDetection:
    """Test suite for asset class detection."""

    def test_detect_asset_class_from_stock_sids(
        self, market_service: MarketService
    ) -> None:
        """Test detecting stock asset class from SIDs."""
        # Use valid stock SIDs (assuming range 1-999999)
        stock_range = InstrumentIdRange.get_range("stock")
        query = MarketBarsQuery(instrument_ids=[stock_range.min_id, stock_range.max_id])
        instrument_ids, asset_class = (
            market_service._resolve_instrument_ids_and_asset_class(query)
        )

        assert asset_class == "stock"
        assert len(instrument_ids) == 2

    def test_detect_asset_class_from_etf_sids(
        self, market_service: MarketService
    ) -> None:
        """Test detecting ETF asset class from SIDs."""
        etf_range = InstrumentIdRange.get_range("etf")
        query = MarketBarsQuery(instrument_ids=[etf_range.min_id, etf_range.max_id])
        instrument_ids, asset_class = (
            market_service._resolve_instrument_ids_and_asset_class(query)
        )

        assert asset_class == "etf"
        assert len(instrument_ids) == 2

    def test_detect_asset_class_from_index_sids(
        self, market_service: MarketService
    ) -> None:
        """Test detecting index asset class from SIDs."""
        index_range = InstrumentIdRange.get_range("index")
        query = MarketBarsQuery(instrument_ids=[index_range.min_id, index_range.max_id])
        instrument_ids, asset_class = (
            market_service._resolve_instrument_ids_and_asset_class(query)
        )

        assert asset_class == "index"
        assert len(instrument_ids) == 2

    def test_detect_mixed_asset_class_raises_error(
        self, market_service: MarketService
    ) -> None:
        """Test that mixed asset class query raises ValueError."""
        stock_range = InstrumentIdRange.get_range("stock")
        etf_range = InstrumentIdRange.get_range("etf")

        query = MarketBarsQuery(instrument_ids=[stock_range.min_id, etf_range.min_id])

        with pytest.raises(ValueError, match="检测到混合资产类别查询"):
            market_service._resolve_instrument_ids_and_asset_class(query)

    def test_explicit_asset_class_mismatch_raises_error(
        self, market_service: MarketService
    ) -> None:
        """Test that explicit asset_class mismatch with detected raises ValueError."""
        stock_range = InstrumentIdRange.get_range("stock")
        # Stock Instrument ID with explicit ETF asset_class should raise error
        query = MarketBarsQuery(instrument_ids=[stock_range.min_id], asset_class="etf")

        with pytest.raises(ValueError, match="显式指定的资产类别"):
            market_service._resolve_instrument_ids_and_asset_class(query)


class TestMarketServiceDateParsing:
    """Test suite for date parsing."""

    def test_parse_dates_with_all_params(self, market_service: MarketService) -> None:
        """Test parsing dates with all parameters."""
        query = MarketBarsQuery(
            instrument_ids=[1, 2],
            start="2024-01-01",
            end="2024-12-31",
            asof="2024-06-30",
        )
        start, end, asof = market_service._parse_dates(query)

        assert start == date(2024, 1, 1)
        assert end == date(2024, 12, 31)
        assert asof == date(2024, 6, 30)

    def test_parse_dates_with_none_params(self, market_service: MarketService) -> None:
        """Test parsing dates with None parameters."""
        query = MarketBarsQuery(instrument_ids=[1, 2])
        start, end, asof = market_service._parse_dates(query)

        assert start is None
        assert end is None
        assert asof is None


class TestMarketServiceLoadBarsCore:
    """Test suite for _load_bars_core method."""

    def test_load_bars_core_stock(
        self,
        market_service: MarketService,
        mock_stock_bars_store: MagicMock,
        sample_stock_bars_df: pl.DataFrame,
    ) -> None:
        """Test loading stock bars."""
        mock_stock_bars_store.read.return_value = sample_stock_bars_df

        result = market_service._load_bars_core(
            instrument_ids=[1, 2],
            start=date(2024, 1, 1),
            end=date(2024, 12, 31),
            asset_class="stock",
        )

        assert not result.is_empty()
        mock_stock_bars_store.read.assert_called_once()

    def test_load_bars_core_etf(
        self,
        market_service: MarketService,
        mock_etf_bars_store: MagicMock,
        sample_stock_bars_df: pl.DataFrame,
    ) -> None:
        """Test loading ETF bars."""
        mock_etf_bars_store.read.return_value = sample_stock_bars_df

        result = market_service._load_bars_core(
            instrument_ids=[1500001],
            start=date(2024, 1, 1),
            end=date(2024, 12, 31),
            asset_class="etf",
        )

        assert not result.is_empty()
        mock_etf_bars_store.read.assert_called_once()

    def test_load_bars_core_index_when_none(
        self, market_service: MarketService
    ) -> None:
        """Test loading index bars when store is None."""
        result = market_service._load_bars_core(
            instrument_ids=[1],
            start=date(2024, 1, 1),
            end=date(2024, 12, 31),
            asset_class="index",
        )

        assert result.is_empty()


class TestMarketServiceApplyAdjustment:
    """Test suite for _apply_adjustment method."""

    def test_apply_adjustment_no_adj_data(
        self,
        market_service: MarketService,
        mock_stock_adj_store: MagicMock,
        sample_stock_bars_df: pl.DataFrame,
    ) -> None:
        """Test adjustment when no adj factor data available."""
        mock_stock_adj_store.read.return_value = pl.DataFrame()

        result = market_service._apply_adjustment(
            df=sample_stock_bars_df,
            adj=AdjType.QFQ,
            instrument_ids=[1, 2],
            start=date(2024, 1, 1),
            end=date(2024, 12, 31),
            asof=None,
        )

        # Should return original DataFrame when no adj data
        assert len(result) == len(sample_stock_bars_df)

    def test_apply_adjustment_with_adj_data(
        self,
        market_service: MarketService,
        mock_stock_adj_store: MagicMock,
        sample_stock_bars_df: pl.DataFrame,
        sample_adj_factor_df: pl.DataFrame,
    ) -> None:
        """Test adjustment with adj factor data."""
        mock_stock_adj_store.read.return_value = sample_adj_factor_df

        result = market_service._apply_adjustment(
            df=sample_stock_bars_df,
            adj=AdjType.QFQ,
            instrument_ids=[1, 2],
            start=date(2024, 1, 1),
            end=date(2024, 12, 31),
            asof=None,
        )

        # The adjustment functions return modified DataFrame
        # Just verify it was called and returns data
        assert len(result) > 0
        mock_stock_adj_store.read.assert_called_once()


class TestMarketServiceEnrichWithStatus:
    """Test suite for _enrich_with_status method."""

    def test_enrich_with_status(
        self,
        market_service: MarketService,
        mock_stock_status_store: MagicMock,
        sample_stock_bars_df: pl.DataFrame,
        sample_status_df: pl.DataFrame,
    ) -> None:
        """Test status enrichment."""
        mock_stock_status_store.read.return_value = sample_status_df

        result = market_service._enrich_with_status(
            df=sample_stock_bars_df,
            instrument_ids=[1, 2],
            start="2024-01-01",
            end="2024-12-31",
        )

        # Should join status columns
        assert "is_suspended" in result.columns
        assert "is_st" in result.columns
        mock_stock_status_store.read.assert_called_once()

    def test_enrich_with_status_date_objects(
        self,
        market_service: MarketService,
        mock_stock_status_store: MagicMock,
        sample_stock_bars_df: pl.DataFrame,
        sample_status_df: pl.DataFrame,
    ) -> None:
        """Test status enrichment with date objects instead of strings."""
        mock_stock_status_store.read.return_value = sample_status_df

        result = market_service._enrich_with_status(
            df=sample_stock_bars_df,
            instrument_ids=[1, 2],
            start=date(2024, 1, 1),
            end=date(2024, 12, 31),
        )

        assert "is_suspended" in result.columns
        # Store should be called with string dates
        mock_stock_status_store.read.assert_called_once()
        call_args = mock_stock_status_store.read.call_args
        assert call_args.kwargs["start_date"] == "2024-01-01"


class TestMarketServiceGetConstituents:
    """Tests for MarketService.get_constituents() method."""

    def test_get_constituents_success(
        self,
        market_service: MarketService,
        mock_index_constituent_store: MagicMock,
    ) -> None:
        """Test successful constituents query."""
        # Mock the store's get method
        mock_index_constituent_store.get.return_value = pl.DataFrame(
            {
                "index_instrument_id": [1, 1, 1],
                "constituent_instrument_id": [100, 101, 102],
                "effective_date": ["2024-01-01", "2024-01-01", "2024-01-01"],
                "weight": [0.4, 0.35, 0.25],
            }
        )

        result = market_service.get_constituents(
            index_instrument_id=1, asof="2024-01-01"
        )

        # Should return the constituents
        assert len(result) == 3
        assert "index_instrument_id" in result.columns
        assert "constituent_instrument_id" in result.columns
        assert "effective_date" in result.columns
        assert "weight" in result.columns

        # Store should be called with correct parameters
        mock_index_constituent_store.get.assert_called_once_with(1, "2024-01-01")

    def test_get_constituents_default_asof(
        self,
        market_service: MarketService,
        mock_index_constituent_store: MagicMock,
    ) -> None:
        """Test constituents query with default asof date (today)."""
        mock_index_constituent_store.get.return_value = pl.DataFrame(
            {
                "index_instrument_id": [1],
                "constituent_instrument_id": [100],
                "effective_date": ["2024-01-01"],
                "weight": [1.0],
            }
        )

        result = market_service.get_constituents(index_instrument_id=1)

        # Should return data with today's date
        assert len(result) == 1
        mock_index_constituent_store.get.assert_called_once()
        call_args = mock_index_constituent_store.get.call_args
        # The second argument should be today's date
        asof_arg = call_args[0][1] if call_args[0] else call_args[1]["asof"]
        assert asof_arg == date.today().isoformat()

    def test_get_constituents_store_not_configured(
        self,
        market_service_without_optionals: MarketService,
    ) -> None:
        """Test constituents query when IndexConstituentStore is not configured."""
        with pytest.raises(
            NotImplementedError,
            match="IndexConstituentStore not configured",
        ):
            market_service_without_optionals.get_constituents(index_instrument_id=1)

    def test_get_constituents_empty_result(
        self,
        market_service: MarketService,
        mock_index_constituent_store: MagicMock,
    ) -> None:
        """Test constituents query returns empty DataFrame."""
        mock_index_constituent_store.get.return_value = pl.DataFrame()

        result = market_service.get_constituents(index_instrument_id=999)

        assert result.is_empty()
        today = date.today().isoformat()
        mock_index_constituent_store.get.assert_called_once_with(999, today)


class TestMarketServiceUnifiedContract:
    """Tests for unified query()/write() contract."""

    def test_query_dispatches_to_constituents(
        self,
        market_service: MarketService,
        mock_index_constituent_store: MagicMock,
    ) -> None:
        """query() should route MarketConstituentsQuery correctly."""
        mock_index_constituent_store.get.return_value = pl.DataFrame(
            {
                "index_instrument_id": [1],
                "constituent_instrument_id": [100],
                "effective_date": ["2024-01-01"],
                "weight": [1.0],
            }
        )
        query = MarketConstituentsQuery(index_instrument_id=1, asof="2024-01-01")

        result = market_service.query(query)

        assert len(result) == 1
        mock_index_constituent_store.get.assert_called_once_with(1, "2024-01-01")

    def test_write_stock_daily(self, market_service: MarketService) -> None:
        """write() should route stock_daily to bars store."""
        market_service._file_lock.acquire.return_value.__enter__.return_value = None
        market_service._stock_bars_store.write.return_value = MagicMock(
            added=2,
            updated=1,
        )
        command = MarketWriteCommand(
            dataset="stock_daily",
            df=pl.DataFrame({"instrument_id": [1], "trade_date": [date(2024, 1, 2)]}),
            year=2024,
        )

        result = market_service.write(command)

        assert result.dataset == "stock_daily"
        assert result.rows == 3
        assert result.files == 1
        market_service._stock_bars_store.write.assert_called_once()

    def test_write_adj_factor(self, market_service: MarketService) -> None:
        """write() should route adj_factor to adj store."""
        market_service._file_lock.acquire.return_value.__enter__.return_value = None
        market_service._stock_adj_store.write.return_value = MagicMock(
            added=1,
            updated=0,
        )
        command = MarketWriteCommand(
            dataset="adj_factor",
            df=pl.DataFrame({"instrument_id": [1], "trade_date": [date(2024, 1, 2)]}),
            year=2024,
        )

        result = market_service.write(command)

        assert result.dataset == "adj_factor"
        assert result.rows == 1
        assert result.files == 1
        market_service._stock_adj_store.write.assert_called_once()

    def test_write_stock_status(self, market_service: MarketService) -> None:
        """write() should route stock_status to status store."""
        market_service._file_lock.acquire.return_value.__enter__.return_value = None
        market_service._stock_status_store.write.return_value = (
            "market/stock/status/2024.parquet",
            "checksum",
        )
        command = MarketWriteCommand(
            dataset="stock_status",
            df=pl.DataFrame(
                {
                    "instrument_id": [1],
                    "trade_date": [date(2024, 1, 2)],
                    "is_suspended": [False],
                    "is_st": [False],
                    "list_status": ["L"],
                }
            ),
            year=2024,
        )

        result = market_service.write(command)

        assert result.dataset == "stock_status"
        assert result.rows == 1
        assert result.files == 1
        market_service._stock_status_store.write.assert_called_once()
