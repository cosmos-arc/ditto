"""Tests for IndexAccessor."""

import polars as pl
import pytest
from ditto_datahub.accessors.index_accessor import IndexAccessor
from ditto_datahub.domains.market.index.weight.weight_store import (
    IndexWeightStore,
)
from ditto_datahub.domains.metadata.instrument import (
    InstrumentStore,
)
from ditto_datahub.stores.bars_store import BarsStore
from pytest_mock import MockerFixture


@pytest.fixture
def mock_bars_store(mocker: MockerFixture) -> BarsStore:
    """Create a mock BarsStore."""
    return mocker.Mock(spec=BarsStore)


@pytest.fixture
def mock_index_weight_store(mocker: MockerFixture) -> IndexWeightStore:
    """Create a mock IndexWeightStore."""
    return mocker.Mock(spec=IndexWeightStore)


@pytest.fixture
def mock_instrument_store(mocker: MockerFixture) -> InstrumentStore:
    """Create a mock InstrumentStore."""
    return mocker.Mock(spec=InstrumentStore)


@pytest.fixture
def index_accessor(
    mock_bars_store: BarsStore,
    mock_index_weight_store: IndexWeightStore,
    mock_instrument_store: InstrumentStore,
) -> IndexAccessor:
    """Create an IndexAccessor with mocked dependencies."""
    return IndexAccessor(
        mock_bars_store,
        mock_index_weight_store,
        mock_instrument_store,
    )


@pytest.mark.integration
class TestIndexAccessorWithMocks:
    """
    Tests for IndexAccessor with mocked dependencies.

    PIT (Pipeline Integration Tests) - tests complete data ingestion flow.
    These tests require more resources and time than unit tests.
    """

    def test_accessor_init(self, index_accessor: IndexAccessor) -> None:
        """Test IndexAccessor initialization."""
        assert index_accessor._bars_store is not None
        assert index_accessor._index_weight_store is not None
        assert index_accessor._instrument_store is not None

    def test_get_bars_by_sids(
        self,
        index_accessor: IndexAccessor,
        mock_bars_store: BarsStore,
    ) -> None:
        """Test getting index bars by SIDs."""
        # Arrange
        mock_df = pl.DataFrame(
            {
                "sid": [1, 1, 2],
                "trade_date": ["2024-01-02", "2024-01-03", "2024-01-02"],
                "open": [3000.0, 3100.0, 2000.0],
                "high": [3050.0, 3150.0, 2050.0],
                "low": [2950.0, 3050.0, 1950.0],
                "close": [3020.0, 3120.0, 2020.0],
                "volume": [1000000, 1100000, 900000],
                "amount": [1000000000, 1100000000, 900000000],
            }
        )
        mock_bars_store.read.return_value = mock_df

        # Act
        result = index_accessor.get_bars(
            sids=[1, 2],
            start="2024-01-01",
            end="2024-01-31",
        )

        # Assert
        assert len(result) == 3
        mock_bars_store.read.assert_called_once_with(
            dataset="index_daily",
            sids=[1, 2],
            start_date="2024-01-01",
            end_date="2024-01-31",
        )

    def test_get_bars_raises_error_when_no_sids_or_symbols(
        self, index_accessor: IndexAccessor
    ) -> None:
        """Test that get_bars raises error when sids is None."""
        # Act & Assert
        with pytest.raises(ValueError, match="sids must be provided"):
            index_accessor.get_bars(
                sids=None,
                start="2024-01-01",
                end="2024-01-31",
            )

    def test_get_constituents_basic(
        self,
        index_accessor: IndexAccessor,
        mock_index_weight_store: IndexWeightStore,
    ) -> None:
        """Test getting index constituents without symbol."""
        # Arrange
        mock_df = pl.DataFrame(
            {
                "index_id": ["000300.SH", "000300.SH"],
                "sid": [1000001, 1000002],
                "effective_from": ["2024-01-01", "2024-01-01"],
                "weight": [0.5, 0.5],
            }
        )
        mock_index_weight_store.get_constituents.return_value = mock_df

        # Act
        result = index_accessor.get_constituents(
            index_id="000300.SH",
            asof=None,
            with_symbol=False,
            min_weight=None,
        )

        # Assert
        assert len(result) == 2
        assert "sid" in result.columns
        assert "symbol" not in result.columns
        mock_index_weight_store.get_constituents.assert_called_once_with(
            index_id="000300.SH", asof=None
        )

    def test_get_constituents_with_symbol(
        self,
        index_accessor: IndexAccessor,
        mock_index_weight_store: IndexWeightStore,
        mock_instrument_store: InstrumentStore,
    ) -> None:
        """Test getting index constituents with symbol join."""
        # Arrange
        mock_df = pl.DataFrame(
            {
                "index_id": ["000300.SH", "000300.SH"],
                "sid": [1000001, 1000002],
                "effective_from": ["2024-01-01", "2024-01-01"],
                "weight": [0.5, 0.5],
            }
        )
        mock_index_weight_store.get_constituents.return_value = mock_df

        # Mock enrich_with_symbol 方法
        mock_enriched_df = pl.DataFrame(
            {
                "index_id": ["000300.SH", "000300.SH"],
                "sid": [1000001, 1000002],
                "effective_from": ["2024-01-01", "2024-01-01"],
                "weight": [0.5, 0.5],
                "symbol": ["SID001", "SID002"],
            }
        )
        mock_instrument_store.enrich_with_symbol.return_value = mock_enriched_df

        # Act
        result = index_accessor.get_constituents(
            index_id="000300.SH",
            asof=None,
            with_symbol=True,
            min_weight=None,
        )

        # Assert
        assert len(result) == 2
        assert "symbol" in result.columns
        mock_instrument_store.enrich_with_symbol.assert_called_once()

    def test_get_constituents_with_min_weight(
        self,
        index_accessor: IndexAccessor,
        mock_index_weight_store: IndexWeightStore,
    ) -> None:
        """Test getting index constituents with minimum weight filter."""
        # Arrange
        mock_df = pl.DataFrame(
            {
                "index_id": ["000300.SH", "000300.SH", "000300.SH"],
                "sid": [1000001, 1000002, 1000003],
                "effective_from": ["2024-01-01", "2024-01-01", "2024-01-01"],
                "weight": [0.6, 0.3, 0.1],
            }
        )
        mock_index_weight_store.get_constituents.return_value = mock_df

        # Act
        result = index_accessor.get_constituents(
            index_id="000300.SH",
            asof=None,
            with_symbol=False,
            min_weight=0.2,
        )

        # Assert
        assert len(result) == 2
        assert 1000001 in result["sid"].to_list()
        assert 1000002 in result["sid"].to_list()
        assert 1000003 not in result["sid"].to_list()

    def test_get_constituents_with_asof(
        self,
        index_accessor: IndexAccessor,
        mock_index_weight_store: IndexWeightStore,
    ) -> None:
        """Test getting index constituents with PIT asof query."""
        # Arrange
        mock_df = pl.DataFrame(
            {
                "index_id": ["000300.SH"],
                "sid": [1000001],
                "effective_from": ["2024-01-01"],
                "weight": [1.0],
            }
        )
        mock_index_weight_store.get_constituents.return_value = mock_df

        # Act
        result = index_accessor.get_constituents(
            index_id="000300.SH",
            asof="2024-06-01",
            with_symbol=False,
            min_weight=None,
        )

        # Assert
        assert len(result) == 1
        mock_index_weight_store.get_constituents.assert_called_once_with(
            index_id="000300.SH", asof="2024-06-01"
        )

    def test_get_index_constituents_sids(
        self,
        index_accessor: IndexAccessor,
        mock_index_weight_store: IndexWeightStore,
    ) -> None:
        """Test getting index constituent SIDs as a list."""
        # Arrange
        mock_index_weight_store.get_constituents_sids.return_value = [
            1000001,
            1000002,
            1000003,
        ]

        # Act
        sids = index_accessor.get_index_constituents_sids(
            index_id="000300.SH",
            asof=None,
        )

        # Assert
        assert len(sids) == 3
        assert 1000001 in sids
        assert 1000002 in sids
        assert 1000003 in sids
        mock_index_weight_store.get_constituents_sids.assert_called_once_with(
            index_id="000300.SH", asof=None
        )

    def test_get_csi300_bars(
        self,
        index_accessor: IndexAccessor,
        mock_bars_store: BarsStore,
        mock_instrument_store: InstrumentStore,
    ) -> None:
        """Test get_csi300_bars predefined shortcut."""
        # Arrange
        mock_df = pl.DataFrame(
            {
                "sid": [300],
                "trade_date": ["2024-01-02"],
                "close": [3500.0],
            }
        )
        mock_bars_store.read.return_value = mock_df
        mock_instrument_store.resolve_sid.return_value = 300

        # Act
        result = index_accessor.get_csi300_bars(
            start="2024-01-01",
            end="2024-01-31",
            asof=None,
        )

        # Assert
        assert len(result) == 1
        mock_instrument_store.resolve_sid.assert_called_once_with(
            "000300.SH", "tushare", None
        )
        mock_bars_store.read.assert_called_once()

    def test_get_csi300_constituents(
        self,
        index_accessor: IndexAccessor,
        mock_index_weight_store: IndexWeightStore,
    ) -> None:
        """Test get_csi300_constituents predefined shortcut."""
        # Arrange
        mock_index_weight_store.get_constituents_sids.return_value = [
            1000001,
            1000002,
        ]

        # Act
        sids = index_accessor.get_csi300_constituents(asof=None)

        # Assert
        assert len(sids) == 2
        mock_index_weight_store.get_constituents_sids.assert_called_once_with(
            index_id="000300.SH", asof=None
        )

    def test_get_csi500_constituents(
        self,
        index_accessor: IndexAccessor,
        mock_index_weight_store: IndexWeightStore,
    ) -> None:
        """Test get_csi500_constituents predefined shortcut."""
        # Arrange
        mock_index_weight_store.get_constituents_sids.return_value = [
            2000001,
            2000002,
        ]

        # Act
        sids = index_accessor.get_csi500_constituents(asof=None)

        # Assert
        assert len(sids) == 2
        mock_index_weight_store.get_constituents_sids.assert_called_once_with(
            index_id="000905.SH", asof=None
        )
