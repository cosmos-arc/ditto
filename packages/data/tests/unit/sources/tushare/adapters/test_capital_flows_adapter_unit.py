"""#518/#519/#520/#523 资金面六接口 adapter 单测——映射输出与请求形状."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_data.sources.tushare.adapters.capital_flows import (
    CapitalFlowsTushareAdapter,
)


def _adapter_with_response(
    response: pl.DataFrame,
) -> tuple[CapitalFlowsTushareAdapter, MagicMock]:
    client = MagicMock()
    client.query.return_value = response
    return CapitalFlowsTushareAdapter(_client=client), client


@pytest.mark.unit
class TestCapitalFlowsAdapters:
    """六接口共用 _fetch_daily_frame：映射列契约 + kd=T+1 + 参数归一."""

    def test_moneyflow_mapping_output(self) -> None:
        adapter, client = _adapter_with_response(
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
        adapter, _ = _adapter_with_response(
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
        adapter, _ = _adapter_with_response(
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
        adapter, _ = _adapter_with_response(
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
        adapter, _ = _adapter_with_response(
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
        adapter, client = _adapter_with_response(pl.DataFrame())
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


@pytest.mark.unit
class TestEventKeyCollapse:
    """#626 事件接口同披露键确定性收敛（源端两类同键多行形态）."""

    def _hk_hold_rows(self) -> pl.DataFrame:
        # 2026-06-30 实证形态：同标的两个北向持有者代码，vol/ratio 各异
        return pl.DataFrame(
            {
                "code": ["30271", "78678"],
                "trade_date": ["20260630", "20260630"],
                "ts_code": ["603062.SH", "603062.SH"],
                "name": ["信捷电气", "信捷电气"],
                "vol": [5980314.0, 245360.0],
                "ratio": [0.17, 0.66],
                "exchange": ["SH", "SH"],
            }
        )

    def _top_list_rows(self) -> pl.DataFrame:
        # 2020-02-03 实证形态：同 (标的, 日, 原因) 冗余行，float_values
        # null/有值差异
        base = {
            "trade_date": ["20200203", "20200203"],
            "ts_code": ["600825.SH", "600825.SH"],
            "name": ["新华传媒", "新华传媒"],
            "close": [4.74, 4.74],
            "pct_change": [-10.0569, -10.0569],
            "turnover_rate": [27.03, 27.03],
            "amount": [359175996.0, 359175996.0],
            "l_sell": [268015059.7, 268015059.7],
            "l_buy": [456795156.4, 456795156.4],
            "l_amount": [724810216.1, 724810216.1],
            "net_amount": [188780096.7, 188780096.7],
            "net_rate": [52.51, 52.51],
            "amount_rate": [52.51, 52.51],
            "float_values": [None, 4952800000.0],
            "reason": ["单只标的证券的当日融资买入数量达到当日该证券总交易量的50%…"]
            * 2,
        }
        return pl.DataFrame(base)

    def test_hk_hold_collapses_multi_holder_rows_order_independent(self) -> None:
        forward, reversed_ = (
            self._frame_rows_order("hk_hold", self._hk_hold_rows(), rev)
            for rev in (False, True)
        )
        assert forward.height == 1
        assert reversed_.height == 1
        # 同一行集合无论源端返回顺序如何都选出同一行（重试幂等）
        assert forward.equals(reversed_)

    def test_top_list_keeps_most_complete_row(self) -> None:
        adapter, _ = _adapter_with_response(self._top_list_rows())
        frame = adapter.fetch_top_list(trade_date="2020-02-03")
        assert frame.height == 1
        assert frame.row(0, named=True)["float_values"] == pytest.approx(4952800000.0)

    def test_top_list_collapse_order_independent(self) -> None:
        forward, reversed_ = (
            self._frame_rows_order("top_list", self._top_list_rows(), rev)
            for rev in (False, True)
        )
        assert forward.equals(reversed_)

    def test_top_inst_shared_collapse_dedupes_same_seat_key(self) -> None:
        rows = pl.DataFrame(
            {
                "trade_date": ["20260922", "20260922"],
                "ts_code": ["000560.SZ", "000560.SZ"],
                "exalter": ["机构专用", "机构专用"],
                "side": ["0", "0"],
                "buy": [27461627.53, 19999999.99],
                "buy_rate": [18.75, 12.34],
                "sell": [0.0, 0.0],
                "sell_rate": [0.0, 0.0],
                "net_buy": [27461627.53, 19999999.99],
                "reason": ["日涨幅偏离值达到7%的前5只证券"] * 2,
            }
        )
        forward, reversed_ = (
            self._frame_rows_order("top_inst", rows, rev) for rev in (False, True)
        )
        assert forward.height == 1
        assert forward.equals(reversed_)

    def test_hsgt_top10_exact_duplicate_rows_collapse(self) -> None:
        row = {
            "trade_date": ["20261016", "20261016"],
            "ts_code": ["000333.SZ", "000333.SZ"],
            "name": ["美的集团", "美的集团"],
            "close": [80.1, 80.1],
            "change": [-1.56, -1.56],
            "rank": [4, 4],
            "market_type": ["3", "3"],
            "amount": [1388236346.0, 1388236346.0],
            "net_amount": [None, None],
            "buy": [None, None],
            "sell": [None, None],
        }
        forward, reversed_ = (
            self._frame_rows_order("hsgt_top10", pl.DataFrame(row), rev)
            for rev in (False, True)
        )
        assert forward.height == 1
        assert forward.equals(reversed_)

    def test_moneyflow_same_key_rows_pass_through_uncollapsed(self) -> None:
        # moneyflow 逐标的单行契约：不收敛，真重复交 DQ unique 响亮失败
        rows = pl.DataFrame(
            {
                "trade_date": ["20260930", "20260930"],
                "ts_code": ["600519.SH", "600519.SH"],
                "net_mf_amount": [60958.84, 11111.11],
                "net_mf_vol": [4859.0, 1.0],
                "buy_elg_amount": [1.0, 1.0],
                "buy_elg_vol": [1.0, 1.0],
                "buy_lg_amount": [1.0, 1.0],
                "buy_lg_vol": [1.0, 1.0],
                "buy_md_amount": [1.0, 1.0],
                "buy_md_vol": [1.0, 1.0],
                "buy_sm_amount": [1.0, 1.0],
                "buy_sm_vol": [1.0, 1.0],
                "sell_elg_amount": [1.0, 1.0],
                "sell_elg_vol": [1.0, 1.0],
                "sell_lg_amount": [1.0, 1.0],
                "sell_lg_vol": [1.0, 1.0],
                "sell_md_amount": [1.0, 1.0],
                "sell_md_vol": [1.0, 1.0],
                "sell_sm_amount": [1.0, 1.0],
                "sell_sm_vol": [1.0, 1.0],
            }
        )
        adapter, _ = _adapter_with_response(rows)
        assert adapter.fetch_moneyflow(trade_date="2026-09-30").height == 2

    def _frame_rows_order(
        self, dataset: str, rows: pl.DataFrame, reverse: bool
    ) -> pl.DataFrame:
        adapter, _ = _adapter_with_response(rows.reverse() if reverse else rows)
        fetch = {
            "hk_hold": lambda: adapter.fetch_hk_hold(trade_date="2026-06-30"),
            "top_list": lambda: adapter.fetch_top_list(trade_date="2020-02-03"),
            "top_inst": lambda: adapter.fetch_top_inst(trade_date="2026-09-22"),
            "hsgt_top10": lambda: adapter.fetch_hsgt_top10(trade_date="2026-10-16"),
        }[dataset]
        return fetch().sort("source_ticker")

    def test_conflicting_same_key_values_warn_not_silent(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """同键非空值互异（真冲突）必须 WARN 可观测，与良性冗余可区分（F2）."""
        from ditto_data.sources.tushare.adapters import capital_flows

        warnings: list[tuple[str, dict[str, object]]] = []

        def fake_warning(message: str, **kwargs: object) -> None:
            warnings.append((message, kwargs))

        monkeypatch.setattr(capital_flows.logger, "warning", fake_warning)
        adapter, _ = _adapter_with_response(self._hk_hold_rows())
        frame = adapter.fetch_hk_hold(trade_date="2026-06-30")
        assert frame.height == 1
        conflicting = [w for w in warnings if "conflicting" in str(w[0])]
        assert conflicting, "真冲突形态必须留下 warning 痕迹"
        assert conflicting[0][1]["differing_columns"] == ["ratio", "vol"]

    def test_benign_null_redundancy_does_not_warn(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """null/有值冗余不算冲突——只 warn 真值互异（F2 判定边界）."""
        from ditto_data.sources.tushare.adapters import capital_flows

        warnings: list[str] = []
        monkeypatch.setattr(
            capital_flows.logger,
            "warning",
            lambda message, **kwargs: warnings.append(str(message)),
        )
        adapter, _ = _adapter_with_response(self._top_list_rows())
        adapter.fetch_top_list(trade_date="2020-02-03")
        assert not [w for w in warnings if "conflicting" in w]

    def test_equal_null_count_group_matches_legacy_hash_rule(self) -> None:
        """F1a 兼容钉：空值数持平的组，胜者=旧 #519 纯哈希 keep-last 规则.

        存量 top_inst（2026-09-22+）按旧规则写入；重拉按新规则时仅
        组内空值数有差的组可能换行，空值持平组必须逐位一致，否则
        VERIFY_IDENTICAL 重拉整批陪葬。旧规则在同一 transform 后帧上
        复算（哈希覆盖列集必须一致）。
        """
        from ditto_data.sources.tushare.adapters.capital_flows import (
            _collapse_same_key_rows,
        )
        from ditto_data.sources.tushare.processors.mappings import (
            HK_HOLD_MAPPING,
        )
        from ditto_data.sources.tushare.processors.transformer import (
            TushareDataTransformer,
        )

        transformed = TushareDataTransformer.transform(
            self._hk_hold_rows(), "hk_hold", HK_HOLD_MAPPING
        )
        legacy_pick = (
            transformed.with_columns(_dedupe_hash=pl.struct(pl.all()).hash())
            .sort("_dedupe_hash")
            .unique(subset=["source_ticker", "trade_date"], keep="last")
            .drop("_dedupe_hash")
        )
        current = _collapse_same_key_rows(
            "hk_hold", transformed, ("source_ticker", "trade_date")
        )
        assert current.select(["vol", "ratio"]).equals(
            legacy_pick.select(["vol", "ratio"])
        )
