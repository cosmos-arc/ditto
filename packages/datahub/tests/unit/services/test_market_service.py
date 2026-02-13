"""
MarketService 单元测试.

测试 Market 域服务的查询和写入功能。
"""

from pathlib import Path
from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_datahub.models import OnDuplicate
from ditto_datahub.services.market_service import (
    AdjType,
    MarketBarsQuery,
    MarketService,
)
from ditto_infra.foundation.concurrency import FileLockManager


@pytest.fixture
def mock_stores() -> dict[str, MagicMock]:
    """创建 Mock Store 实例."""
    return {
        "stock_bars_reader": MagicMock(),
        "stock_bars_writer": MagicMock(),
        "stock_status_reader": MagicMock(),
        "stock_status_writer": MagicMock(),
        "stock_adj_reader": MagicMock(),
        "stock_adj_writer": MagicMock(),
        "etf_bars_reader": MagicMock(),
        "etf_bars_writer": MagicMock(),
        "etf_status_reader": MagicMock(),
        "etf_status_writer": MagicMock(),
        "instrument_reader": MagicMock(),
    }


@pytest.fixture
def market_service(mock_stores: dict[str, MagicMock], tmp_path: Path) -> MarketService:
    """创建 MarketService 实例."""
    lock_dir = tmp_path / "locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    return MarketService(
        stock_bars_reader=mock_stores["stock_bars_reader"],
        stock_bars_writer=mock_stores["stock_bars_writer"],
        stock_status_reader=mock_stores["stock_status_reader"],
        stock_status_writer=mock_stores["stock_status_writer"],
        stock_adj_reader=mock_stores["stock_adj_reader"],
        stock_adj_writer=mock_stores["stock_adj_writer"],
        etf_bars_reader=mock_stores["etf_bars_reader"],
        etf_bars_writer=mock_stores["etf_bars_writer"],
        etf_status_reader=mock_stores["etf_status_reader"],
        etf_status_writer=mock_stores["etf_status_writer"],
        instrument_reader=mock_stores["instrument_reader"],
        file_lock=FileLockManager(lock_dir),
    )


class TestMarketServiceFindBars:
    """测试 find_bars() 方法."""

    def test_find_bars_stock(
        self, market_service: MarketService, mock_stores: dict[str, MagicMock]
    ) -> None:
        """测试查询股票K线数据."""
        # Arrange
        query = MarketBarsQuery(
            instrument_ids=[1, 2, 3],
            start="2024-01-01",
            end="2024-01-05",
            adj=AdjType.NONE,
        )
        mock_df = pl.DataFrame(
            {
                "instrument_id": [1, 1, 2],
                "trade_date": ["2024-01-01", "2024-01-02", "2024-01-01"],
                "open": [10.0, 11.0, 20.0],
                "close": [10.5, 11.5, 20.5],
            }
        )
        mock_stores["stock_bars_reader"].read.return_value = mock_df
        mock_stores["instrument_reader"].list_instrument_ids.return_value = [1, 2, 3]

        # Act
        result = market_service.find_bars(query)

        # Assert
        assert len(result) == 3
        mock_stores["stock_bars_reader"].read.assert_called_once()

    def test_find_bars_etf(
        self, market_service: MarketService, mock_stores: dict[str, MagicMock]
    ) -> None:
        """测试查询 ETF K线数据."""
        # Arrange - 使用正确的 ETF ID 范围 (2,000,000 - 2,999,999)
        query = MarketBarsQuery(
            instrument_ids=[2_000_001, 2_000_002],
            start="2024-01-01",
            end="2024-01-05",
            asset_class="etf",
        )
        mock_df = pl.DataFrame(
            {
                "instrument_id": [2_000_001],
                "trade_date": ["2024-01-01"],
                "open": [1.0],
                "close": [1.05],
            }
        )
        mock_stores["etf_bars_reader"].read.return_value = mock_df

        # Act
        result = market_service.find_bars(query)

        # Assert
        assert len(result) == 1
        mock_stores["etf_bars_reader"].read.assert_called_once()


class TestMarketServiceListBars:
    """测试 list_bars() 便利方法."""

    def test_list_bars(
        self, market_service: MarketService, mock_stores: dict[str, MagicMock]
    ) -> None:
        """测试 list_bars() 便利方法."""
        # Arrange
        mock_df = pl.DataFrame(
            {
                "instrument_id": [1, 2],
                "trade_date": ["2024-01-01", "2024-01-01"],
                "close": [10.5, 20.5],
            }
        )
        mock_stores["stock_bars_reader"].read.return_value = mock_df

        # Act
        result = market_service.list_bars(
            instrument_ids=[1, 2],
            start="2024-01-01",
            end="2024-01-05",
        )

        # Assert
        assert len(result) == 2
        mock_stores["stock_bars_reader"].read.assert_called_once()

    def test_list_bars_with_adj(
        self, market_service: MarketService, mock_stores: dict[str, MagicMock]
    ) -> None:
        """测试 list_bars() 带复权参数."""
        # Arrange - 需要包含复权所需的所有列
        bars_df = pl.DataFrame(
            {
                "instrument_id": [1, 1],
                "trade_date": ["2024-01-01", "2024-01-02"],
                "open": [10.0, 11.0],
                "high": [10.5, 11.5],
                "low": [9.5, 10.5],
                "close": [10.0, 11.0],
                "volume": [1000, 1100],
                "amount": [10000, 11000],
            }
        )
        adj_df = pl.DataFrame(
            {
                "instrument_id": [1, 1],
                "trade_date": ["2024-01-01", "2024-01-02"],
                "adj_factor": [1.2, 1.2],
            }
        )
        mock_stores["stock_bars_reader"].read.return_value = bars_df
        mock_stores["stock_adj_reader"].read.return_value = adj_df

        # Act
        result = market_service.list_bars(
            instrument_ids=[1],
            start="2024-01-01",
            end="2024-01-05",
            adj=AdjType.QFQ,
        )

        # Assert
        assert len(result) == 2


class TestMarketServiceGetConstituents:
    """测试 get_constituents() 方法."""

    def test_get_constituents_not_implemented(
        self, market_service: MarketService
    ) -> None:
        """测试未配置 IndexConstituentReader 时抛出异常."""
        # Act & Assert
        with pytest.raises(
            NotImplementedError, match="IndexConstituentReader not configured"
        ):
            market_service.get_constituents(1)


class TestMarketServiceSaveBars:
    """测试 save_bars() 方法."""

    def test_save_stock_daily(
        self, market_service: MarketService, mock_stores: dict[str, MagicMock]
    ) -> None:
        """测试保存股票日线数据."""
        # Arrange
        df = pl.DataFrame(
            {
                "instrument_id": [1, 2],
                "trade_date": ["2024-01-01", "2024-01-01"],
                "open": [10.0, 20.0],
                "close": [10.5, 20.5],
            }
        )
        mock_write_result = MagicMock()
        mock_write_result.added = 2
        mock_write_result.updated = 0
        mock_stores["stock_bars_writer"].write.return_value = mock_write_result

        # Act
        rows_written = market_service.save_bars(
            dataset="stock_daily",
            df=df,
            year=2024,
            on_duplicate=OnDuplicate.ERROR,
        )

        # Assert
        assert rows_written == 2
        mock_stores["stock_bars_writer"].write.assert_called_once()

    def test_save_etf_daily(
        self, market_service: MarketService, mock_stores: dict[str, MagicMock]
    ) -> None:
        """测试保存 ETF 日线数据."""
        # Arrange
        df = pl.DataFrame(
            {
                "instrument_id": [500001],
                "trade_date": ["2024-01-01"],
                "open": [1.0],
                "close": [1.05],
            }
        )
        mock_write_result = MagicMock()
        mock_write_result.added = 1
        mock_write_result.updated = 0
        mock_stores["etf_bars_writer"].write.return_value = mock_write_result

        # Act
        rows_written = market_service.save_bars(
            dataset="etf_daily",
            df=df,
            year=2024,
        )

        # Assert
        assert rows_written == 1
        mock_stores["etf_bars_writer"].write.assert_called_once()


class TestMarketServiceSaveAdjFactor:
    """测试 save_adj_factor() 方法."""

    def test_save_adj_factor(
        self, market_service: MarketService, mock_stores: dict[str, MagicMock]
    ) -> None:
        """测试保存复权因子数据."""
        # Arrange
        df = pl.DataFrame(
            {
                "instrument_id": [1],
                "trade_date": ["2024-01-01"],
                "adj_factor": [1.2],
            }
        )
        mock_write_result = MagicMock()
        mock_write_result.added = 1
        mock_write_result.updated = 0
        mock_stores["stock_adj_writer"].write.return_value = mock_write_result

        # Act
        rows_written = market_service.save_adj_factor(
            df=df,
            year=2024,
            on_duplicate=OnDuplicate.ERROR,
        )

        # Assert
        assert rows_written == 1
        mock_stores["stock_adj_writer"].write.assert_called_once()


class TestMarketServiceSaveStockStatus:
    """测试 save_stock_status() 方法."""

    def test_save_stock_status(
        self, market_service: MarketService, mock_stores: dict[str, MagicMock]
    ) -> None:
        """测试保存股票状态数据."""
        # Arrange
        df = pl.DataFrame(
            {
                "instrument_id": [1],
                "trade_date": ["2024-01-01"],
                "is_suspended": [False],
                "is_st": [False],
            }
        )

        # Act
        rows_written = market_service.save_stock_status(
            df=df,
            year=2024,
        )

        # Assert
        assert rows_written == 1
        mock_stores["stock_status_writer"].write.assert_called_once_with(df, 2024)
