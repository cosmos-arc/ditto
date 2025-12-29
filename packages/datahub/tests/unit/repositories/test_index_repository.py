"""Tests for IndexRepository."""

from unittest.mock import Mock

import polars as pl
import pytest
from ditto_datahub.repositories.index import IndexRepository
from ditto_datahub.stores.bars_store import BarsStore
from ditto_datahub.stores.index_weight_store import IndexWeightStore
from ditto_datahub.stores.security_store import SecurityStore


class TestIndexRepositoryWithMocks:
    """Tests for IndexRepository with mocked dependencies."""

    def setup_method(self) -> None:
        """Set up mocked stores for testing."""
        self.mock_bars_store = Mock(spec=BarsStore)
        self.mock_index_weight_store = Mock(spec=IndexWeightStore)
        self.mock_security_store = Mock(spec=SecurityStore)
        self.repo = IndexRepository(
            self.mock_bars_store,
            self.mock_index_weight_store,
            self.mock_security_store,
        )

    def test_repository_init(self) -> None:
        """Test IndexRepository initialization."""
        assert self.repo._bars_store is not None
        assert self.repo._index_weight_store is not None
        assert self.repo._security_store is not None

    def test_get_bars_by_sids(self) -> None:
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
        self.mock_bars_store.read.return_value = mock_df

        # Act
        result = self.repo.get_bars(
            sids=[1, 2],
            symbols=None,
            start="2024-01-01",
            end="2024-01-31",
            asof=None,
        )

        # Assert
        assert len(result) == 3
        self.mock_bars_store.read.assert_called_once_with(
            dataset="index_daily",
            sids=[1, 2],
            start_date="2024-01-01",
            end_date="2024-01-31",
        )

    def test_get_bars_by_symbols(self) -> None:
        """Test getting index bars by symbols (requires SID resolution)."""
        # Arrange
        mock_df = pl.DataFrame(
            {
                "sid": [1, 1],
                "trade_date": ["2024-01-02", "2024-01-03"],
                "close": [3020.0, 3120.0],
            }
        )
        self.mock_bars_store.read.return_value = mock_df
        self.mock_security_store.resolve_sid.return_value = 1

        # Act
        result = self.repo.get_bars(
            sids=None,
            symbols=["000300.SH"],
            start="2024-01-01",
            end="2024-01-31",
            asof=None,
        )

        # Assert
        assert len(result) == 2
        self.mock_security_store.resolve_sid.assert_called_once_with(
            "000300.SH", "tushare", None
        )
        self.mock_bars_store.read.assert_called_once_with(
            dataset="index_daily",
            sids=[1],
            start_date="2024-01-01",
            end_date="2024-01-31",
        )

    def test_get_bars_with_asof(self) -> None:
        """Test getting index bars with asof parameter."""
        # Arrange
        mock_df = pl.DataFrame(
            {
                "sid": [1],
                "trade_date": ["2024-01-02"],
                "close": [3020.0],
            }
        )
        self.mock_bars_store.read.return_value = mock_df
        self.mock_security_store.resolve_sid.return_value = 1

        # Act
        result = self.repo.get_bars(
            sids=None,
            symbols=["000300.SH"],
            start="2024-01-01",
            end="2024-01-31",
            asof="2024-01-15",
        )

        # Assert
        assert len(result) == 1
        self.mock_security_store.resolve_sid.assert_called_once_with(
            "000300.SH", "tushare", "2024-01-15"
        )

    def test_get_bars_raises_error_when_no_sids_or_symbols(self) -> None:
        """Test that get_bars raises error when both sids and symbols are None."""
        # Act & Assert
        with pytest.raises(ValueError, match="Either sids or symbols"):
            self.repo.get_bars(
                sids=None,
                symbols=None,
                start="2024-01-01",
                end="2024-01-31",
                asof=None,
            )

    def test_get_constituents_basic(self) -> None:
        """Test getting index constituents without symbol."""
        # Arrange
        mock_df = pl.DataFrame(
            {
                "index_id": ["000300.SH", "000300.SH"],
                "sid": [100000001, 100000002],
                "effective_from": ["2024-01-01", "2024-01-01"],
                "weight": [0.5, 0.5],
            }
        )
        self.mock_index_weight_store.get_constituents.return_value = mock_df

        # Act
        result = self.repo.get_constituents(
            index_id="000300.SH",
            asof=None,
            with_symbol=False,
            min_weight=None,
        )

        # Assert
        assert len(result) == 2
        assert "sid" in result.columns
        assert "symbol" not in result.columns
        self.mock_index_weight_store.get_constituents.assert_called_once_with(
            index_id="000300.SH", asof=None
        )

    def test_get_constituents_with_symbol(self) -> None:
        """Test getting index constituents with symbol join."""
        # Arrange
        mock_df = pl.DataFrame(
            {
                "index_id": ["000300.SH", "000300.SH"],
                "sid": [100000001, 100000002],
                "effective_from": ["2024-01-01", "2024-01-01"],
                "weight": [0.5, 0.5],
            }
        )
        self.mock_index_weight_store.get_constituents.return_value = mock_df

        mock_security_df = pl.DataFrame(
            {
                "sid": [100000001, 100000002],
                "symbol": ["SID001", "SID002"],
            }
        )
        self.mock_security_store.find_securities.return_value = mock_security_df

        # Act
        result = self.repo.get_constituents(
            index_id="000300.SH",
            asof=None,
            with_symbol=True,
            min_weight=None,
        )

        # Assert
        assert len(result) == 2
        assert "symbol" in result.columns
        self.mock_security_store.find_securities.assert_called_once()

    def test_get_constituents_with_min_weight(self) -> None:
        """Test getting index constituents with minimum weight filter."""
        # Arrange
        mock_df = pl.DataFrame(
            {
                "index_id": ["000300.SH", "000300.SH", "000300.SH"],
                "sid": [100000001, 100000002, 100000003],
                "effective_from": ["2024-01-01", "2024-01-01", "2024-01-01"],
                "weight": [0.6, 0.3, 0.1],
            }
        )
        self.mock_index_weight_store.get_constituents.return_value = mock_df

        # Act
        result = self.repo.get_constituents(
            index_id="000300.SH",
            asof=None,
            with_symbol=False,
            min_weight=0.2,
        )

        # Assert
        assert len(result) == 2
        assert 100000001 in result["sid"].to_list()
        assert 100000002 in result["sid"].to_list()
        assert 100000003 not in result["sid"].to_list()

    def test_get_constituents_with_asof(self) -> None:
        """Test getting index constituents with PIT asof query."""
        # Arrange
        mock_df = pl.DataFrame(
            {
                "index_id": ["000300.SH"],
                "sid": [100000001],
                "effective_from": ["2024-01-01"],
                "weight": [1.0],
            }
        )
        self.mock_index_weight_store.get_constituents.return_value = mock_df

        # Act
        result = self.repo.get_constituents(
            index_id="000300.SH",
            asof="2024-06-01",
            with_symbol=False,
            min_weight=None,
        )

        # Assert
        assert len(result) == 1
        self.mock_index_weight_store.get_constituents.assert_called_once_with(
            index_id="000300.SH", asof="2024-06-01"
        )

    def test_get_index_constituents_sids(self) -> None:
        """Test getting index constituent SIDs as a list."""
        # Arrange
        self.mock_index_weight_store.get_constituents_sids.return_value = [
            100000001,
            100000002,
            100000003,
        ]

        # Act
        sids = self.repo.get_index_constituents_sids(
            index_id="000300.SH",
            asof=None,
        )

        # Assert
        assert len(sids) == 3
        assert 100000001 in sids
        assert 100000002 in sids
        assert 100000003 in sids
        self.mock_index_weight_store.get_constituents_sids.assert_called_once_with(
            index_id="000300.SH", asof=None
        )

    def test_get_csi300_bars(self) -> None:
        """Test get_csi300_bars predefined shortcut."""
        # Arrange
        mock_df = pl.DataFrame(
            {
                "sid": [300],
                "trade_date": ["2024-01-02"],
                "close": [3500.0],
            }
        )
        self.mock_bars_store.read.return_value = mock_df
        self.mock_security_store.resolve_sid.return_value = 300

        # Act
        result = self.repo.get_csi300_bars(
            start="2024-01-01",
            end="2024-01-31",
            asof=None,
        )

        # Assert
        assert len(result) == 1
        self.mock_security_store.resolve_sid.assert_called_once_with(
            "000300.SH", "tushare", None
        )
        self.mock_bars_store.read.assert_called_once()

    def test_get_csi300_constituents(self) -> None:
        """Test get_csi300_constituents predefined shortcut."""
        # Arrange
        self.mock_index_weight_store.get_constituents_sids.return_value = [
            100000001,
            100000002,
        ]

        # Act
        sids = self.repo.get_csi300_constituents(asof=None)

        # Assert
        assert len(sids) == 2
        self.mock_index_weight_store.get_constituents_sids.assert_called_once_with(
            index_id="000300.SH", asof=None
        )

    def test_get_csi500_constituents(self) -> None:
        """Test get_csi500_constituents predefined shortcut."""
        # Arrange
        self.mock_index_weight_store.get_constituents_sids.return_value = [
            200000001,
            200000002,
        ]

        # Act
        sids = self.repo.get_csi500_constituents(asof=None)

        # Assert
        assert len(sids) == 2
        self.mock_index_weight_store.get_constituents_sids.assert_called_once_with(
            index_id="000905.SH", asof=None
        )
