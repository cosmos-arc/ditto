"""
MarketService.get_adj_factors / get_stock_status 单元测试.

P3-2 层边界修复：验证 MarketService 暴露 adj_factor 和 stock_status
的公开查询接口，供 RuntimeDerivedInputProvider 使用。
"""

from pathlib import Path
from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_datahub.services.market_service import MarketService
from ditto_datahub.services.ports import MarketReadPorts, MarketWritePorts
from ditto_infra.foundation.concurrency import FileLockManager


@pytest.fixture
def mock_readers() -> dict[str, MagicMock]:
    """创建 Mock Reader 实例."""
    return {
        "stock_bars": MagicMock(),
        "stock_status": MagicMock(),
        "stock_adj": MagicMock(),
        "etf_bars": MagicMock(),
        "etf_status": MagicMock(),
        "instrument": MagicMock(),
    }


@pytest.fixture
def mock_writers() -> dict[str, MagicMock]:
    """创建 Mock Writer 实例."""
    return {
        "stock_bars": MagicMock(),
        "stock_status": MagicMock(),
        "stock_adj": MagicMock(),
        "etf_bars": MagicMock(),
        "etf_status": MagicMock(),
    }


@pytest.fixture
def market_service(
    mock_readers: dict[str, MagicMock],
    mock_writers: dict[str, MagicMock],
    tmp_path: Path,
) -> MarketService:
    """创建 MarketService 实例."""
    lock_dir = tmp_path / "locks"
    lock_dir.mkdir(parents=True, exist_ok=True)

    read_ports = MarketReadPorts(
        stock_bars=mock_readers["stock_bars"],
        stock_status=mock_readers["stock_status"],
        stock_adj=mock_readers["stock_adj"],
        etf_bars=mock_readers["etf_bars"],
        etf_status=mock_readers["etf_status"],
        instrument=mock_readers["instrument"],
    )

    write_ports = MarketWritePorts(
        stock_bars=mock_writers["stock_bars"],
        stock_status=mock_writers["stock_status"],
        stock_adj=mock_writers["stock_adj"],
        etf_bars=mock_writers["etf_bars"],
        etf_status=mock_writers["etf_status"],
    )

    return MarketService(
        read_ports=read_ports,
        write_ports=write_ports,
        file_lock=FileLockManager(lock_dir),
    )


class TestGetAdjFactors:
    """测试 get_adj_factors() 公开方法."""

    def test_get_adj_factors_returns_dataframe(
        self,
        market_service: MarketService,
        mock_readers: dict[str, MagicMock],
    ) -> None:
        """get_adj_factors 应返回 adj_factor 数据的 pl.DataFrame."""
        # Arrange
        mock_df = pl.DataFrame(
            {
                "instrument_id": [1_000_001, 1_000_001, 1_000_002],
                "trade_date": ["2024-01-01", "2024-01-02", "2024-01-01"],
                "adj_factor": [1.0, 1.0, 1.0],
            }
        )
        mock_readers["stock_adj"].read.return_value = mock_df

        # Act
        result = market_service.get_adj_factors(start="2024-01-01", end="2024-01-02")

        # Assert
        assert isinstance(result, pl.DataFrame)
        assert "adj_factor" in result.columns
        assert len(result) == 3

    def test_get_adj_factors_delegates_to_reader(
        self,
        market_service: MarketService,
        mock_readers: dict[str, MagicMock],
    ) -> None:
        """get_adj_factors 应正确传递 start/end 参数给底层 Reader."""
        # Act
        market_service.get_adj_factors(start="2024-01-01", end="2024-12-31")

        # Assert
        mock_readers["stock_adj"].read.assert_called_once_with(
            start_date="2024-01-01",
            end_date="2024-12-31",
        )

    def test_get_adj_factors_passes_through_empty_result(
        self,
        market_service: MarketService,
        mock_readers: dict[str, MagicMock],
    ) -> None:
        """get_adj_factors 应透传空 DataFrame."""
        # Arrange
        mock_readers["stock_adj"].read.return_value = pl.DataFrame()

        # Act
        result = market_service.get_adj_factors(start="2020-01-01", end="2020-01-31")

        # Assert
        assert result.is_empty()


class TestGetStockStatus:
    """测试 get_stock_status() 公开方法."""

    def test_get_stock_status_returns_dataframe(
        self,
        market_service: MarketService,
        mock_readers: dict[str, MagicMock],
    ) -> None:
        """get_stock_status 应返回 stock_status 数据的 pl.DataFrame."""
        # Arrange
        mock_df = pl.DataFrame(
            {
                "instrument_id": [1_000_001, 1_000_001],
                "trade_date": ["2024-01-01", "2024-01-02"],
                "is_suspended": [False, True],
                "is_st": [False, False],
                "list_status": ["L", "L"],
            }
        )
        mock_readers["stock_status"].read.return_value = mock_df

        # Act
        result = market_service.get_stock_status(start="2024-01-01", end="2024-01-02")

        # Assert
        assert isinstance(result, pl.DataFrame)
        assert "is_suspended" in result.columns
        assert "is_st" in result.columns
        assert "list_status" in result.columns
        assert len(result) == 2

    def test_get_stock_status_delegates_to_reader(
        self,
        market_service: MarketService,
        mock_readers: dict[str, MagicMock],
    ) -> None:
        """get_stock_status 应正确传递 start/end 参数给底层 Reader."""
        # Act
        market_service.get_stock_status(start="2024-01-01", end="2024-12-31")

        # Assert
        mock_readers["stock_status"].read.assert_called_once_with(
            start_date="2024-01-01",
            end_date="2024-12-31",
        )

    def test_get_stock_status_passes_through_empty_result(
        self,
        market_service: MarketService,
        mock_readers: dict[str, MagicMock],
    ) -> None:
        """get_stock_status 应透传空 DataFrame."""
        # Arrange
        mock_readers["stock_status"].read.return_value = pl.DataFrame()

        # Act
        result = market_service.get_stock_status(start="2020-01-01", end="2020-01-31")

        # Assert
        assert result.is_empty()
