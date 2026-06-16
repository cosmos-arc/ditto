"""seed_stock_selection_rotation 端到端集成测试.

验证个股选股 seed 的因子链路（signal_expressions 编译 + 基本面注入 + 信号计算）
能端到端跑通，不再出现 P0-#1 修复前的 ColumnNotFoundError。

覆盖：
  - seed 三因子（quality_roe, value_pe, momentum_1m）ID 解析 + 编译
  - 基本面截面注入（roe / pe_ratio）+ 历史窗口（momentum_1m 时序）
  - PIT: get_fundamental_snapshot as_of = knowledge_date
  - 确定性：相同输入两次跑结果一致
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_application.processes.execution.factor_bridge import (
    FactorBridge,
    build_factor_bundle,
)
from ditto_backtest.data_feed import Slice
from ditto_backtest.steps import StepContext
from ditto_kernel.identity import InstrumentId
from ditto_kernel.time_context import TimeContext
from ditto_strategy.alpha.seeds import SEED_STRATEGY_SPECS

_INSTRUMENT_IDS = [1, 2, 3]
_KNOWLEDGE_DATE = date(2024, 6, 1)
_TRADE_DATE = "2024-06-03"
_HISTORY_END = date(2024, 5, 31)
_HISTORY_DAYS = 22  # > momentum_1m 的 ts_pct_change(close, 20) 窗口


def _make_bar(close: float) -> MagicMock:
    bar = MagicMock()
    bar.open = close * 0.99
    bar.high = close * 1.01
    bar.low = close * 0.98
    bar.close = close
    bar.volume = 1_000_000.0
    bar.prev_close = close
    return bar


def _make_history_df(
    instrument_ids: list[int],
    days: int,
    end_date: date,
) -> pl.DataFrame:
    """构造 N 标的 × days 天历史 OHLCV（trade_date < end_date 的窗口）."""
    rows: list[dict[str, Any]] = []
    for iid in instrument_ids:
        base = 10.0 + iid
        growth = 0.001 * (1 + iid * 0.5)  # 不同增长率，避免 momentum tie
        for i in range(days):
            d = (end_date - timedelta(days=days - i)).isoformat()
            close = base * (1 + growth * i)
            rows.append(
                {
                    "instrument_id": iid,
                    "trade_date": d,
                    "open": close * 0.99,
                    "high": close * 1.01,
                    "low": close * 0.98,
                    "close": close,
                    "volume": 1_000_000.0,
                },
            )
    return pl.DataFrame(rows)


def _make_fundamental_df(instrument_ids: list[int]) -> pl.DataFrame:
    """构造基本面截面快照（roe / net_margin / eps）."""
    n = len(instrument_ids)
    return pl.DataFrame(
        {
            "instrument_id": instrument_ids,
            "roe": [0.10 + 0.05 * i for i in range(n)],
            "net_margin": [0.08 + 0.02 * i for i in range(n)],
            "eps": [1.0 + 0.5 * i for i in range(n)],
        },
    )


def _make_data_feed(
    history_df: pl.DataFrame,
    fundamental_df: pl.DataFrame,
) -> MagicMock:
    feed = MagicMock()
    feed.get_history.return_value = history_df
    feed.get_fundamental_snapshot.return_value = fundamental_df
    return feed


def _make_ctx() -> StepContext:
    bars = {
        InstrumentId(1): _make_bar(11.0),
        InstrumentId(2): _make_bar(12.0),
        InstrumentId(3): _make_bar(13.0),
    }
    slice_ = MagicMock(spec=Slice)
    slice_.bars = bars
    slice_.benchmark_close = None
    return StepContext(
        time_context=TimeContext(
            decision_time=datetime(2024, 6, 3, 15, 0, tzinfo=UTC),
            knowledge_date=_KNOWLEDGE_DATE,
            trade_date=_TRADE_DATE,
        ),
        is_rebalance_day=True,
        bars=slice_.bars,
        slice_=slice_,
    )


def _build_seed_bundle() -> Any:
    spec = SEED_STRATEGY_SPECS["seed_stock_selection_rotation"]
    bridge = FactorBridge()
    compiled = bridge.compile_and_validate(
        expressions=spec.signal_expressions,
        weights=spec.signal_weights,
    )
    history_df = _make_history_df(_INSTRUMENT_IDS, _HISTORY_DAYS, _HISTORY_END)
    data_feed = _make_data_feed(history_df, _make_fundamental_df(_INSTRUMENT_IDS))
    return build_factor_bundle(
        ctx=_make_ctx(),
        strategy_id="seed_stock_selection_rotation",
        run_id="e2e",
        bridge=bridge,
        compiled=compiled,
        data_feed=data_feed,
        lookback_days=25,
    )


@pytest.mark.integration
class TestSeedStockSelectionRotationE2E:
    """_seed_stock_selection_rotation seed 因子链路端到端验证."""

    def test_seed_factor_pipeline_runs_without_column_not_found(self) -> None:
        """seed 三因子端到端编译+计算，不再 ColumnNotFoundError，产出 signal_value."""
        spec = SEED_STRATEGY_SPECS["seed_stock_selection_rotation"]
        # 前置断言：seed 确实用三因子 ID（P0-#1 修复前提）
        assert spec.signal_expressions == ("quality_roe", "value_pe", "momentum_1m")

        bundle = _build_seed_bundle()

        assert bundle.signal_values is not None
        assert bundle.signal_values.height == 3
        assert "signal_value" in bundle.signal_values.columns
        values = bundle.signal_values["signal_value"].to_list()
        assert len(values) == 3
        assert all(isinstance(v, float) for v in values)

    def test_deterministic_signal_values_across_runs(self) -> None:
        """相同输入两次跑产生相同 signal_value（确定性基线）."""
        first = _build_seed_bundle().signal_values
        second = _build_seed_bundle().signal_values
        assert first is not None
        assert second is not None
        assert first.sort("instrument_id")["signal_value"].to_list() == (
            second.sort("instrument_id")["signal_value"].to_list()
        )

    def test_fundamental_snapshot_uses_knowledge_date_pit(self) -> None:
        """seed 回测路径 get_fundamental_snapshot 的 as_of = knowledge_date（PIT）."""
        spec = SEED_STRATEGY_SPECS["seed_stock_selection_rotation"]
        bridge = FactorBridge()
        compiled = bridge.compile_and_validate(
            expressions=spec.signal_expressions,
            weights=spec.signal_weights,
        )
        history_df = _make_history_df(_INSTRUMENT_IDS, _HISTORY_DAYS, _HISTORY_END)
        data_feed = _make_data_feed(history_df, _make_fundamental_df(_INSTRUMENT_IDS))

        build_factor_bundle(
            ctx=_make_ctx(),
            strategy_id="s",
            run_id="r",
            bridge=bridge,
            compiled=compiled,
            data_feed=data_feed,
            lookback_days=25,
        )

        call = data_feed.get_fundamental_snapshot.call_args
        # knowledge_date=2024-06-01，非 trade_date=2024-06-03
        assert call.args[1] == _KNOWLEDGE_DATE
