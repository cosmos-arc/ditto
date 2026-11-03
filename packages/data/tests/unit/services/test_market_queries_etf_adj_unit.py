"""通用 K线入口（query_bars/find_bars）的 ETF 复权与不支持组合语义（#658 批次1D）.

此前通用入口仅对 stock 应用复权：ETF 的 qfq/hfq 被静默忽略返回 raw，
index/fx/commodity 的复权请求同样被静默忽略（#653 已证实缺陷）。
"""

from __future__ import annotations

from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_data.errors.integrity import AdjustmentFactorMissingError
from ditto_data.services.deps import MarketReaders
from ditto_data.services.market_queries import MarketBarsQuery
from ditto_data.services.market_service import MarketService
from ditto_data.services.market_types import AdjType

ETF_ID = 2_000_001
INDEX_ID = 3_000_001

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

SAMPLE_INDEX_BARS = pl.DataFrame(
    {
        "instrument_id": [INDEX_ID, INDEX_ID],
        "trade_date": ["2024-01-02", "2024-01-03"],
        "open": [3000.0, 3010.0],
        "high": [3050.0, 3060.0],
        "low": [2980.0, 2990.0],
        "close": [3040.0, 3050.0],
        "volume": [1_000_000, 1_100_000],
        "amount": [1.0e11, 1.1e11],
    }
)


def _readers(**overrides: MagicMock | None) -> MarketReaders:
    return MarketReaders(
        stock_bars=MagicMock(),
        stock_status=MagicMock(),
        stock_adj=MagicMock(),
        etf_bars=overrides.get("etf_bars") or MagicMock(),
        etf_status=MagicMock(),
        instrument=MagicMock(),
        etf_adj=overrides.get("etf_adj"),
        index_bars=overrides.get("index_bars"),
    )


class TestGenericEtfAdjustment:
    """通用入口按资产类别分派复权（#658 批次1D）."""

    def test_etf_qfq_applies_fund_adj(self) -> None:
        """ETF + qfq 经通用入口真实复权——不再是静默 raw.

        QFQ: adj_price = orig * cur_factor / latest_factor.
        close: [1.03*1.0/1.1, 1.05*1.1/1.1] = [0.936..., 1.05]
        """
        etf_adj = MagicMock()
        etf_adj.read.return_value = SAMPLE_ETF_ADJ
        etf_bars = MagicMock()
        etf_bars.read.return_value = SAMPLE_ETF_BARS
        service = MarketService(read_ports=_readers(etf_adj=etf_adj, etf_bars=etf_bars))

        result = service.find_bars(
            MarketBarsQuery(
                instrument_ids=[ETF_ID],
                start="2024-01-02",
                end="2024-01-03",
                adj=AdjType.QFQ,
            )
        )

        assert result["close"].to_list() == pytest.approx(
            [round(1.03 / 1.1, 10), 1.05], abs=1e-9
        )
        # 因子读取按标的范围（与股票路径同构），不是全市场盲读
        assert etf_adj.read.call_args.kwargs["instrument_ids"] == [ETF_ID]

    def test_etf_hfq_applies_fund_adj(self) -> None:
        """ETF + hfq 经通用入口真实复权: close * adj_factor."""
        etf_adj = MagicMock()
        etf_adj.read.return_value = SAMPLE_ETF_ADJ
        etf_bars = MagicMock()
        etf_bars.read.return_value = SAMPLE_ETF_BARS
        service = MarketService(read_ports=_readers(etf_adj=etf_adj, etf_bars=etf_bars))

        result = service.find_bars(
            MarketBarsQuery(
                instrument_ids=[ETF_ID],
                start="2024-01-02",
                end="2024-01-03",
                adj=AdjType.HFQ,
            )
        )

        assert result["close"].to_list() == pytest.approx([1.03, 1.155])

    def test_etf_adj_none_returns_raw(self) -> None:
        """显式 adj=none 维持原价（显式选择原价才返回原价）."""
        etf_adj = MagicMock()
        etf_bars = MagicMock()
        etf_bars.read.return_value = SAMPLE_ETF_BARS
        service = MarketService(read_ports=_readers(etf_adj=etf_adj, etf_bars=etf_bars))

        result = service.find_bars(
            MarketBarsQuery(
                instrument_ids=[ETF_ID],
                start="2024-01-02",
                end="2024-01-03",
                adj=AdjType.NONE,
            )
        )

        assert result["close"].to_list() == [1.03, 1.05]
        etf_adj.read.assert_not_called()

    def test_etf_qfq_missing_factor_fails_closed(self) -> None:
        """ETF + qfq 但窗口无任何 fund_adj 行 → 拒绝（不静默退 raw）."""
        etf_adj = MagicMock()
        etf_adj.read.return_value = pl.DataFrame(
            schema={
                "instrument_id": pl.Int64,
                "trade_date": pl.String,
                "adj_factor": pl.Float64,
            }
        )
        etf_bars = MagicMock()
        etf_bars.read.return_value = SAMPLE_ETF_BARS
        service = MarketService(read_ports=_readers(etf_adj=etf_adj, etf_bars=etf_bars))

        with pytest.raises(AdjustmentFactorMissingError):
            service.find_bars(
                MarketBarsQuery(
                    instrument_ids=[ETF_ID],
                    start="2024-01-02",
                    end="2024-01-03",
                    adj=AdjType.QFQ,
                )
            )

    def test_etf_qfq_no_etf_adj_port_fails_closed(self) -> None:
        """ETF + qfq 但 etf_adj 端口未配置 → 拒绝（缺端口不得静默 raw）."""
        etf_bars = MagicMock()
        etf_bars.read.return_value = SAMPLE_ETF_BARS
        service = MarketService(read_ports=_readers(etf_adj=None, etf_bars=etf_bars))

        with pytest.raises(AdjustmentFactorMissingError, match="etf_adj"):
            service.find_bars(
                MarketBarsQuery(
                    instrument_ids=[ETF_ID],
                    start="2024-01-02",
                    end="2024-01-03",
                    adj=AdjType.QFQ,
                )
            )

    def test_index_adj_rejected_explicitly(self) -> None:
        """index + qfq 显式拒绝——此前静默忽略返回 raw（不支持组合防错）."""
        index_bars = MagicMock()
        index_bars.read.return_value = SAMPLE_INDEX_BARS
        service = MarketService(read_ports=_readers(index_bars=index_bars))

        with pytest.raises(ValueError, match="does not support adjustment"):
            service.find_bars(
                MarketBarsQuery(
                    instrument_ids=[INDEX_ID],
                    start="2024-01-02",
                    end="2024-01-03",
                    adj=AdjType.QFQ,
                )
            )

    def test_index_adj_none_returns_raw(self) -> None:
        """index + adj=none 不受影响（指数本身无复权语义）."""
        index_bars = MagicMock()
        index_bars.read.return_value = SAMPLE_INDEX_BARS
        service = MarketService(read_ports=_readers(index_bars=index_bars))

        result = service.find_bars(
            MarketBarsQuery(
                instrument_ids=[INDEX_ID],
                start="2024-01-02",
                end="2024-01-03",
                adj=AdjType.NONE,
            )
        )

        assert result["close"].to_list() == [3040.0, 3050.0]
