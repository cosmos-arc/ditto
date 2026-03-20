"""
MarketService.get_etf_bars / _apply_etf_adjustment 单元测试.

Phase 1.2 ETF 因子评估：验证 MarketService 暴露 ETF K线查询接口
及 ETF 复权调整功能。
"""

from pathlib import Path
from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_datahub.services.market_service import MarketService
from ditto_datahub.services.ports import MarketReadPorts, MarketWritePorts
from ditto_infra.foundation.concurrency import FileLockManager

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_readers() -> dict[str, MagicMock]:
    """创建 Mock Reader 实例."""
    return {
        "stock_bars": MagicMock(),
        "stock_status": MagicMock(),
        "stock_adj": MagicMock(),
        "etf_bars": MagicMock(),
        "etf_status": MagicMock(),
        "etf_adj": MagicMock(),
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
    """创建 MarketService 实例（etf_adj 端口已配置）."""
    lock_dir = tmp_path / "locks"
    lock_dir.mkdir(parents=True, exist_ok=True)

    read_ports = MarketReadPorts(
        stock_bars=mock_readers["stock_bars"],
        stock_status=mock_readers["stock_status"],
        stock_adj=mock_readers["stock_adj"],
        etf_bars=mock_readers["etf_bars"],
        etf_status=mock_readers["etf_status"],
        instrument=mock_readers["instrument"],
        etf_adj=mock_readers["etf_adj"],
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


@pytest.fixture
def market_service_no_etf_adj(
    mock_readers: dict[str, MagicMock],
    mock_writers: dict[str, MagicMock],
    tmp_path: Path,
) -> MarketService:
    """创建 MarketService 实例（etf_adj 端口为 None）."""
    lock_dir = tmp_path / "locks"
    lock_dir.mkdir(parents=True, exist_ok=True)

    read_ports = MarketReadPorts(
        stock_bars=mock_readers["stock_bars"],
        stock_status=mock_readers["stock_status"],
        stock_adj=mock_readers["stock_adj"],
        etf_bars=mock_readers["etf_bars"],
        etf_status=mock_readers["etf_status"],
        instrument=mock_readers["instrument"],
        etf_adj=None,
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


# ---------------------------------------------------------------------------
# Test data helpers
# ---------------------------------------------------------------------------

ETF_ID = 2_000_001

SAMPLE_ETF_BARS = pl.DataFrame(
    {
        "instrument_id": [ETF_ID, ETF_ID],
        "trade_date": ["2024-01-02", "2024-01-03"],
        "open": [1.0, 1.02],
        "high": [1.05, 1.07],
        "low": [0.98, 1.00],
        "close": [1.03, 1.05],
        "volume": [100_000, 110_000],
        "amount": [103_000.0, 115_500.0],
    }
)

SAMPLE_ETF_ADJ = pl.DataFrame(
    {
        "instrument_id": [ETF_ID, ETF_ID],
        "trade_date": ["2024-01-02", "2024-01-03"],
        "adj_factor": [1.0, 1.1],
    }
)


# ---------------------------------------------------------------------------
# Tests: get_etf_bars
# ---------------------------------------------------------------------------


class TestGetEtfBars:
    """测试 get_etf_bars() 公开方法."""

    def test_get_etf_bars_returns_raw_data(
        self,
        market_service: MarketService,
        mock_readers: dict[str, MagicMock],
    ) -> None:
        """get_etf_bars 应从 etf_bars read port 返回数据."""
        # Arrange
        mock_readers["etf_bars"].read.return_value = SAMPLE_ETF_BARS

        # Act
        result = market_service.get_etf_bars(start="2024-01-01", end="2024-01-31")

        # Assert
        assert isinstance(result, pl.DataFrame)
        assert len(result) == 2
        assert "instrument_id" in result.columns
        assert "trade_date" in result.columns
        assert "close" in result.columns

    def test_get_etf_bars_delegates_to_reader(
        self,
        market_service: MarketService,
        mock_readers: dict[str, MagicMock],
    ) -> None:
        """get_etf_bars 应正确传递 start/end 参数给底层 Reader."""
        # Act
        market_service.get_etf_bars(start="2024-01-01", end="2024-01-31")

        # Assert
        mock_readers["etf_bars"].read.assert_called_once_with(
            start_date="2024-01-01",
            end_date="2024-01-31",
        )

    def test_get_etf_bars_no_adjustment(
        self,
        market_service: MarketService,
        mock_readers: dict[str, MagicMock],
    ) -> None:
        """默认 adj='none' 应返回未复权数据（不调用 etf_adj）."""
        # Arrange
        mock_readers["etf_bars"].read.return_value = SAMPLE_ETF_BARS

        # Act
        result = market_service.get_etf_bars(
            start="2024-01-01", end="2024-01-31", adj="none"
        )

        # Assert
        assert len(result) == 2
        # adj='none' 不应读取复权因子
        mock_readers["etf_adj"].read.assert_not_called()

    def test_get_etf_bars_with_qfq_adjustment(
        self,
        market_service: MarketService,
        mock_readers: dict[str, MagicMock],
    ) -> None:
        """adj='qfq' 应在 etf_adj 端口可用时应用前复权."""
        # Arrange
        mock_readers["etf_bars"].read.return_value = SAMPLE_ETF_BARS
        mock_readers["etf_adj"].read.return_value = SAMPLE_ETF_ADJ

        # Act
        result = market_service.get_etf_bars(
            start="2024-01-01", end="2024-01-31", adj="qfq"
        )

        # Assert
        assert isinstance(result, pl.DataFrame)
        assert len(result) == 2
        # QFQ 调整后不应保留 adj_factor 列
        assert "adj_factor" not in result.columns
        # etf_adj.read 应被调用
        mock_readers["etf_adj"].read.assert_called_once()

    def test_get_etf_bars_qfq_no_adj_data(
        self,
        market_service: MarketService,
        mock_readers: dict[str, MagicMock],
    ) -> None:
        """adj='qfq' 但没有 ETF 复权因子数据时应优雅回退返回原始数据."""
        # Arrange
        mock_readers["etf_bars"].read.return_value = SAMPLE_ETF_BARS
        mock_readers["etf_adj"].read.return_value = pl.DataFrame()

        # Act
        result = market_service.get_etf_bars(
            start="2024-01-01", end="2024-01-31", adj="qfq"
        )

        # Assert
        assert len(result) == 2
        # 应返回原始数据（close 未变）
        assert result["close"].to_list() == [1.03, 1.05]

    def test_get_etf_bars_qfq_no_etf_adj_port(
        self,
        market_service_no_etf_adj: MarketService,
        mock_readers: dict[str, MagicMock],
    ) -> None:
        """adj='qfq' 但 etf_adj 端口为 None 时应返回未复权数据."""
        # Arrange
        mock_readers["etf_bars"].read.return_value = SAMPLE_ETF_BARS

        # Act
        result = market_service_no_etf_adj.get_etf_bars(
            start="2024-01-01", end="2024-01-31", adj="qfq"
        )

        # Assert
        assert len(result) == 2
        assert result["close"].to_list() == [1.03, 1.05]

    def test_get_etf_bars_hfq_adjustment(
        self,
        market_service: MarketService,
        mock_readers: dict[str, MagicMock],
    ) -> None:
        """adj='hfq' 应应用后复权."""
        # Arrange
        mock_readers["etf_bars"].read.return_value = SAMPLE_ETF_BARS
        mock_readers["etf_adj"].read.return_value = SAMPLE_ETF_ADJ

        # Act
        result = market_service.get_etf_bars(
            start="2024-01-01", end="2024-01-31", adj="hfq"
        )

        # Assert
        assert isinstance(result, pl.DataFrame)
        assert len(result) == 2
        # HFQ 调整后不应保留 adj_factor 列
        assert "adj_factor" not in result.columns

    def test_get_etf_bars_hfq_adjusted_values(
        self,
        market_service: MarketService,
        mock_readers: dict[str, MagicMock],
    ) -> None:
        """adj='hfq' 应正确计算后复权价格: adj_price = orig_price * adj_factor."""
        # Arrange
        mock_readers["etf_bars"].read.return_value = SAMPLE_ETF_BARS
        mock_readers["etf_adj"].read.return_value = SAMPLE_ETF_ADJ

        # Act
        result = market_service.get_etf_bars(
            start="2024-01-01", end="2024-01-31", adj="hfq"
        )

        # Assert: HFQ: close * adj_factor
        # Row 0: 1.03 * 1.0 = 1.03
        # Row 1: 1.05 * 1.1 = 1.155
        assert result["close"].to_list() == pytest.approx([1.03, 1.155])
        # open: 1.0 * 1.0 = 1.0, 1.02 * 1.1 = 1.122
        assert result["open"].to_list() == pytest.approx([1.0, 1.122])

    def test_get_etf_bars_passes_through_empty_result(
        self,
        market_service: MarketService,
        mock_readers: dict[str, MagicMock],
    ) -> None:
        """get_etf_bars 应透传空 DataFrame."""
        # Arrange
        mock_readers["etf_bars"].read.return_value = pl.DataFrame()

        # Act
        result = market_service.get_etf_bars(start="2020-01-01", end="2020-01-31")

        # Assert
        assert result.is_empty()

    def test_get_etf_bars_adj_type_from_string(
        self,
        market_service: MarketService,
        mock_readers: dict[str, MagicMock],
    ) -> None:
        """get_etf_bars 应正确解析各种 adj 字符串."""
        # Arrange
        mock_readers["etf_bars"].read.return_value = SAMPLE_ETF_BARS

        # Act & Assert: 'NONE' (uppercase) 也应被正确解析
        result = market_service.get_etf_bars(
            start="2024-01-01", end="2024-01-31", adj="NONE"
        )
        assert len(result) == 2
        mock_readers["etf_adj"].read.assert_not_called()
