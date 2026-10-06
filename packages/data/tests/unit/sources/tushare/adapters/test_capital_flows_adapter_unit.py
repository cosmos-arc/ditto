"""#518/#519/#520/#523 资金面六接口 adapter 单测——映射输出与请求形状."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_data.sources.tushare.adapters.capital_flows import (
    CapitalFlowsTushareAdapter,
)


@pytest.mark.unit
class TestCapitalFlowsAdapters:
    """六接口共用 _fetch_daily_frame：映射列契约 + kd=T+1 + 参数归一."""

    def _adapter_with_response(
        self, response: pl.DataFrame
    ) -> tuple[CapitalFlowsTushareAdapter, MagicMock]:
        client = MagicMock()
        client.query.return_value = response
        return CapitalFlowsTushareAdapter(_client=client), client

    def test_moneyflow_mapping_output(self) -> None:
        adapter, client = self._adapter_with_response(
            pl.DataFrame(
                {
                    "trade_date": ["20260930"],
                    "ts_code": ["600519.SH"],
                    "buy_elg_amount": [127633.14],
                    "buy_elg_vol": [10196.0],
                    "buy_lg_amount": [171675.91],
                    "buy_lg_vol": [13710.0],
                    "buy_md_amount": [180847.58],
                    "buy_md_vol": [14460.0],
                    "buy_sm_amount": [21.14],
                    "buy_sm_vol": [2.0],
                    "net_mf_amount": [60958.84],
                    "net_mf_vol": [4859.0],
                    "sell_elg_amount": [86609.04],
                    "sell_elg_vol": [6916.0],
                    "sell_lg_amount": [158665.28],
                    "sell_lg_vol": [12667.0],
                    "sell_md_amount": [234845.9],
                    "sell_md_vol": [18780.0],
                    "sell_sm_amount": [57.55],
                    "sell_sm_vol": [5.0],
                }
            )
        )
        frame = adapter.fetch_moneyflow(trade_date="2026-09-30")

        assert client.query.call_args.kwargs["trade_date"] == "20260930"
        assert client.query.call_args.kwargs["api_name"] == "moneyflow"
        row = frame.row(0, named=True)
        assert row["source_ticker"] == "600519.SH"
        assert row["trade_date"] == date(2026, 9, 30)
        assert row["knowledge_date"] == date(2026, 10, 1)
        assert row["net_mf_amount"] == pytest.approx(60958.84)
        assert frame.columns[0:3] == ["source_ticker", "trade_date", "knowledge_date"]

    def test_cyq_perf_mapping_output(self) -> None:
        adapter, _ = self._adapter_with_response(
            pl.DataFrame(
                {
                    "ts_code": ["600519.SH"],
                    "trade_date": ["20260930"],
                    "cost_5pct": [1178.1],
                    "cost_15pct": [1247.4],
                    "cost_50pct": [1339.8],
                    "cost_85pct": [1478.4],
                    "cost_95pct": [1894.2],
                    "his_high": [2263.8],
                    "his_low": [0.0],
                    "weight_avg": [1381.67],
                    "winner_rate": [21.21],
                }
            )
        )
        frame = adapter.fetch_cyq_perf(trade_date="2026-09-30")
        row = frame.row(0, named=True)
        # his_low=0 是源端标记，原值保留不填值
        assert row["his_low"] == 0.0
        assert row["winner_rate"] == pytest.approx(21.21)
        assert row["knowledge_date"] == date(2026, 10, 1)

    def test_hk_hold_drops_redundant_columns_keeps_exchange(self) -> None:
        adapter, _ = self._adapter_with_response(
            pl.DataFrame(
                {
                    "code": ["90519"],
                    "trade_date": ["20260930"],
                    "ts_code": ["600519.SH"],
                    "name": ["貴州茅台"],
                    "vol": [86831284.0],
                    "ratio": [6.91],
                    "exchange": ["SH"],
                }
            )
        )
        frame = adapter.fetch_hk_hold(trade_date="2026-09-30")
        assert frame.columns == [
            "source_ticker",
            "trade_date",
            "knowledge_date",
            "vol",
            "ratio",
            "exchange",
        ]

    def test_hsgt_top10_preserves_stopped_disclosure_nulls(self) -> None:
        """2024-08 改制后 buy/sell/net_amount 停披为 null——原样保留不填零."""
        adapter, _ = self._adapter_with_response(
            pl.DataFrame(
                {
                    "trade_date": ["20260930"],
                    "ts_code": ["000333.SZ"],
                    "name": ["美的集团"],
                    "close": [80.1],
                    "change": [-1.56],
                    "rank": [4],
                    "market_type": ["3"],
                    "amount": [1388236346.0],
                    "net_amount": [None],
                    "buy": [None],
                    "sell": [None],
                }
            )
        )
        frame = adapter.fetch_hsgt_top10(trade_date="2026-09-30")
        row = frame.row(0, named=True)
        assert row["buy"] is None
        assert row["net_amount"] is None
        assert row["pct_change"] == pytest.approx(-1.56)
        assert row["rank"] == 4
        assert row["market_type"] == "3"

    def test_top_list_reason_kept_in_output(self) -> None:
        adapter, _ = self._adapter_with_response(
            pl.DataFrame(
                {
                    "trade_date": ["20260922"],
                    "ts_code": ["000560.SZ"],
                    "name": ["我爱我家"],
                    "close": [3.51],
                    "pct_change": [10.0313],
                    "turnover_rate": [17.42],
                    "amount": [1412921349.0],
                    "l_sell": [202237378.68],
                    "l_buy": [274616275.3],
                    "l_amount": [476853653.98],
                    "net_amount": [72378896.62],
                    "net_rate": [5.12],
                    "amount_rate": [33.75],
                    "float_values": [8222835297.69],
                    "reason": ["日涨幅偏离值达到7%的前5只证券"],
                }
            )
        )
        frame = adapter.fetch_top_list(trade_date="2026-09-22")
        assert frame.row(0, named=True)["reason"] == "日涨幅偏离值达到7%的前5只证券"

    def test_instrument_mode_passes_range_params(self) -> None:
        adapter, client = self._adapter_with_response(pl.DataFrame())
        adapter.fetch_top_inst(
            ts_code="000560.SZ",
            start_date="2026-09-01",
            end_date="2026-09-30",
        )
        kwargs = client.query.call_args.kwargs
        assert kwargs["ts_code"] == "000560.SZ"
        assert kwargs["start_date"] == "20260901"
        assert kwargs["end_date"] == "20260930"
        assert "trade_date" not in kwargs
