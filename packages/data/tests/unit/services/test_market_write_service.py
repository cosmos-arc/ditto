"""
MarketWriteService 单元测试.

测试 Market 域服务的写入功能。
"""

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_data.errors import LateArrivalRejectedError
from ditto_data.models.ingestion import DataLateArrivalPolicy
from ditto_data.services.deps import MarketWriters
from ditto_data.services.market_write_service import MarketWriteService
from ditto_platform.foundation import FileLockManager, OnDuplicate


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
def market_write_service(
    mock_writers: dict[str, MagicMock],
    tmp_path: Path,
) -> MarketWriteService:
    """创建 MarketWriteService 实例."""
    lock_dir = tmp_path / "locks"
    lock_dir.mkdir(parents=True, exist_ok=True)

    write_ports = MarketWriters(
        stock_bars=mock_writers["stock_bars"],
        stock_status=mock_writers["stock_status"],
        stock_adj=mock_writers["stock_adj"],
        etf_bars=mock_writers["etf_bars"],
        etf_status=mock_writers["etf_status"],
    )

    return MarketWriteService(
        write_ports=write_ports,
        file_lock=FileLockManager(lock_dir),
    )


class TestMarketWriteServiceSaveBars:
    """测试 save_bars() 方法."""

    def test_save_stock_daily(
        self,
        market_write_service: MarketWriteService,
        mock_writers: dict[str, MagicMock],
    ) -> None:
        """测试保存股票日线数据."""
        # Arrange - 使用正确的 Stock ID 范围 (1,000,000 - 1,999,999)
        df = pl.DataFrame(
            {
                "instrument_id": [1_000_001, 1_000_002],
                "trade_date": ["2024-01-01", "2024-01-01"],
                "open": [10.0, 20.0],
                "close": [10.5, 20.5],
            }
        )
        mock_write_result = MagicMock()
        mock_write_result.added = 2
        mock_write_result.updated = 0
        mock_writers["stock_bars"].write.return_value = mock_write_result

        # Act
        rows_written = market_write_service.save_bars(
            dataset="stock_daily",
            df=df,
            year=2024,
            on_duplicate=OnDuplicate.ERROR,
        )

        # Assert
        assert rows_written == 2
        mock_writers["stock_bars"].write.assert_called_once()

    def test_save_etf_daily(
        self,
        market_write_service: MarketWriteService,
        mock_writers: dict[str, MagicMock],
    ) -> None:
        """测试保存 ETF 日线数据."""
        # Arrange - 使用正确的 ETF ID 范围 (2,000,000 - 2,999,999)
        df = pl.DataFrame(
            {
                "instrument_id": [2_000_001],
                "trade_date": ["2024-01-01"],
                "open": [1.0],
                "close": [1.05],
            }
        )
        mock_write_result = MagicMock()
        mock_write_result.added = 1
        mock_write_result.updated = 0
        mock_writers["etf_bars"].write.return_value = mock_write_result

        # Act
        rows_written = market_write_service.save_bars(
            dataset="etf_daily",
            df=df,
            year=2024,
        )

        # Assert
        assert rows_written == 1
        mock_writers["etf_bars"].write.assert_called_once()


class TestMarketWriteServiceSaveAdjFactor:
    """测试 save_adj_factor() 方法."""

    def test_save_adj_factor(
        self,
        market_write_service: MarketWriteService,
        mock_writers: dict[str, MagicMock],
    ) -> None:
        """测试保存复权因子数据."""
        # Arrange - 使用正确的 Stock ID 范围 (1,000,000 - 1,999,999)
        df = pl.DataFrame(
            {
                "instrument_id": [1_000_001],
                "trade_date": ["2024-01-01"],
                "adj_factor": [1.2],
            }
        )
        mock_write_result = MagicMock()
        mock_write_result.added = 1
        mock_write_result.updated = 0
        mock_writers["stock_adj"].write.return_value = mock_write_result

        # Act
        rows_written = market_write_service.save_adj_factor(
            df=df,
            year=2024,
            on_duplicate=OnDuplicate.ERROR,
        )

        # Assert
        assert rows_written == 1
        mock_writers["stock_adj"].write.assert_called_once()


class TestMarketWriteServiceSaveStockStatus:
    """测试 save_stock_status() 方法."""

    def test_save_stock_status(
        self,
        market_write_service: MarketWriteService,
        mock_writers: dict[str, MagicMock],
    ) -> None:
        """测试保存股票状态数据."""
        # Arrange - 使用正确的 Stock ID 范围 (1,000,000 - 1,999,999)
        df = pl.DataFrame(
            {
                "instrument_id": [1_000_001],
                "trade_date": ["2024-01-01"],
                "is_suspended": [False],
                "is_st": [False],
            }
        )

        # Act
        rows_written = market_write_service.save_stock_status(
            df=df,
            year=2024,
        )

        # Assert
        assert rows_written == 1
        mock_writers["stock_status"].write.assert_called_once_with(df, 2024)


class TestMarketWriteServiceCheckLateArrival:
    """测试 check_late_arrival_on_write() 集成钩子."""

    def test_accept_passes_through(self) -> None:
        """ACCEPT 策略委托给 check_late_arrival."""
        result = MarketWriteService.check_late_arrival_on_write(
            knowledge_date=date(2024, 1, 10),
            trade_date=date(2024, 1, 1),
            policy=DataLateArrivalPolicy.ACCEPT,
        )
        assert result.accepted is True
        assert result.needs_rebuild is False

    def test_reject_raises(self) -> None:
        """REJECT 策略超出阈值时抛出 LateArrivalRejectedError."""
        with pytest.raises(LateArrivalRejectedError):
            MarketWriteService.check_late_arrival_on_write(
                knowledge_date=date(2024, 1, 10),
                trade_date=date(2024, 1, 1),
                policy=DataLateArrivalPolicy.REJECT,
                max_delay_days=5,
            )

    def test_rebuild_flags_needs_rebuild(self) -> None:
        """REBUILD 策略在有延迟时标记需要重建."""
        result = MarketWriteService.check_late_arrival_on_write(
            knowledge_date=date(2024, 1, 10),
            trade_date=date(2024, 1, 1),
            policy=DataLateArrivalPolicy.REBUILD,
        )
        assert result.accepted is True
        assert result.needs_rebuild is True
