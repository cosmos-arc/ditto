"""FactorBridge 回测集成测试 — 验证因子信号注入回测流程."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from unittest.mock import MagicMock

import polars as pl
from ditto_application.processes.execution.backtest_process import (
    BacktestService,
    BacktestServiceConfig,
    BacktestServiceOptions,
)
from ditto_application.processes.execution.factor_bridge import (
    FactorBridge,
)
from ditto_backtest.data_feed import Slice
from ditto_backtest.steps import StepContext
from ditto_kernel.identity import InstrumentId
from ditto_kernel.time_context import TimeContext
from ditto_strategy.alpha.pipeline import StrategyInputBundle


def _make_slice_with_bars() -> Slice:
    """构造测试用 Slice."""
    mock_slice = MagicMock(spec=Slice)
    mock_bar_1 = MagicMock()
    mock_bar_1.open = 10.0
    mock_bar_1.high = 11.0
    mock_bar_1.low = 9.0
    mock_bar_1.close = 10.5
    mock_bar_1.volume = 1000.0
    mock_bar_1.prev_close = 10.0

    mock_bar_2 = MagicMock()
    mock_bar_2.open = 20.0
    mock_bar_2.high = 21.0
    mock_bar_2.low = 19.0
    mock_bar_2.close = 20.5
    mock_bar_2.volume = 2000.0
    mock_bar_2.prev_close = 20.0

    mock_bar_3 = MagicMock()
    mock_bar_3.open = 30.0
    mock_bar_3.high = 31.0
    mock_bar_3.low = 29.0
    mock_bar_3.close = 30.5
    mock_bar_3.volume = 3000.0
    mock_bar_3.prev_close = 30.0

    mock_slice.bars = {1: mock_bar_1, 2: mock_bar_2, 3: mock_bar_3}
    mock_slice.benchmark_close = None
    return mock_slice


def _make_step_context(date_str: str, slice_: Slice) -> StepContext:
    """构造测试用 StepContext."""
    ctx = MagicMock(spec=StepContext)
    ctx.time_context = MagicMock()
    ctx.time_context.trade_date = date_str
    ctx.time_context.knowledge_date = date.fromisoformat(date_str) - timedelta(days=1)
    ctx.slice_ = slice_
    return ctx


class _StrictHistoryDataFeed:
    """DataFeed fake that applies the same strict as_of boundary as production."""

    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._history = pl.DataFrame(rows)
        self.requested_as_of_dates: list[str] = []

    def get_history(
        self,
        instrument_ids: list[InstrumentId],
        as_of_date: str,
        lookback_days: int,
    ) -> pl.DataFrame:
        self.requested_as_of_dates.append(as_of_date)
        iid_values = [int(iid) for iid in instrument_ids]
        return (
            self._history.filter(
                pl.col("instrument_id").is_in(iid_values)
                & (pl.col("trade_date") < as_of_date),
            )
            .sort(["instrument_id", "trade_date"])
            .group_by("instrument_id", maintain_order=True)
            .tail(lookback_days)
        )


class TestFactorAwareBundleBuilder:
    """验证含因子信号注入的 input_bundle_builder."""

    def test_factor_bundle_produces_signal_values(self) -> None:
        """含因子表达式的 bundle builder 产出 signal_value 列."""
        bridge = FactorBridge()
        compiled = bridge.compile_and_validate(
            expressions=("close",),
            weights=(1.0,),
        )

        config = BacktestServiceConfig(
            strategy_id="test-strat",
            start_date="2024-01-02",
            end_date="2024-01-05",
        )

        # BacktestService 需要 pipeline 等参数，但我们只需要测试
        # _build_factor_aware_bundle_builder 的产出
        mock_pipeline = MagicMock()
        mock_planner = MagicMock()
        mock_brokerage = MagicMock()
        mock_pre_trade = MagicMock()
        mock_data_feed = MagicMock()

        service = BacktestService(
            config=config,
            pipeline=mock_pipeline,
            planner=mock_planner,
            brokerage=mock_brokerage,
            pre_trade_check=mock_pre_trade,
            data_feed=mock_data_feed,
            options=BacktestServiceOptions(compiled_expressions=compiled),
        )

        # 获取 bundle builder
        builder = service._build_factor_aware_bundle_builder(
            compiled, run_id="test-run"
        )

        # 构造测试输入
        mock_slice = _make_slice_with_bars()
        ctx = _make_step_context("2024-01-02", mock_slice)

        bundle = builder(ctx)

        assert isinstance(bundle, StrategyInputBundle)
        assert bundle.trade_date == "2024-01-02"
        assert bundle.strategy_id == "test-strat"
        assert bundle.signal_values is not None
        assert "instrument_id" in bundle.signal_values.columns
        assert "signal_value" in bundle.signal_values.columns
        assert bundle.signal_values.height == 3

    def test_factor_bundle_signal_values_in_range(self) -> None:
        """因子信号值在 [0, 1] 范围内."""
        bridge = FactorBridge()
        compiled = bridge.compile_and_validate(
            expressions=("close", "volume"),
            weights=(0.6, 0.4),
        )

        config = BacktestServiceConfig(
            strategy_id="test-strat",
            start_date="2024-01-02",
            end_date="2024-01-05",
        )

        mock_pipeline = MagicMock()
        mock_planner = MagicMock()
        mock_brokerage = MagicMock()
        mock_pre_trade = MagicMock()
        mock_data_feed = MagicMock()

        service = BacktestService(
            config=config,
            pipeline=mock_pipeline,
            planner=mock_planner,
            brokerage=mock_brokerage,
            pre_trade_check=mock_pre_trade,
            data_feed=mock_data_feed,
            options=BacktestServiceOptions(compiled_expressions=compiled),
        )

        builder = service._build_factor_aware_bundle_builder(
            compiled, run_id="test-run"
        )

        mock_slice = _make_slice_with_bars()
        ctx = _make_step_context("2024-01-02", mock_slice)

        bundle = builder(ctx)

        signal_values = bundle.signal_values["signal_value"].to_list()
        for v in signal_values:
            assert 0.0 <= v <= 1.0

    def test_factor_history_uses_knowledge_date_cutoff(self) -> None:
        """T 日因子回看不得读取 knowledge_date 当日仍不可见的历史行."""
        bridge = FactorBridge()
        compiled = bridge.compile_and_validate(
            expressions=("ts_mean(close, 2)",),
            weights=(1.0,),
        )

        data_feed = _StrictHistoryDataFeed(
            rows=[
                {
                    "instrument_id": 1,
                    "trade_date": "2026-04-08",
                    "open": 8.0,
                    "high": 8.0,
                    "low": 8.0,
                    "close": 8.0,
                    "volume": 800.0,
                },
                {
                    "instrument_id": 1,
                    "trade_date": "2026-04-09",
                    "open": 9.0,
                    "high": 9.0,
                    "low": 9.0,
                    "close": 9.0,
                    "volume": 900.0,
                },
            ],
        )
        service = BacktestService(
            config=BacktestServiceConfig(
                strategy_id="pit-strat",
                start_date="2026-04-08",
                end_date="2026-04-10",
            ),
            pipeline=MagicMock(),
            planner=MagicMock(),
            brokerage=MagicMock(),
            pre_trade_check=MagicMock(),
            data_feed=data_feed,
            options=BacktestServiceOptions(compiled_expressions=compiled),
        )
        builder = service._build_factor_aware_bundle_builder(
            compiled,
            run_id="pit-run",
        )

        bar = MagicMock()
        bar.open = 10.0
        bar.high = 10.0
        bar.low = 10.0
        bar.close = 10.0
        bar.volume = 1_000.0
        slice_ = MagicMock(spec=Slice)
        slice_.bars = {InstrumentId(1): bar}
        slice_.benchmark_close = None
        ctx = StepContext(
            time_context=TimeContext(
                decision_time=datetime(2026, 4, 10, 15, 0, tzinfo=UTC),
                knowledge_date=date(2026, 4, 9),
                trade_date="2026-04-10",
            ),
            is_rebalance_day=True,
            bars=slice_.bars,
            slice_=slice_,
        )

        bundle = builder(ctx)

        assert data_feed.requested_as_of_dates == ["2026-04-09"]
        assert bundle.market_data["trade_date"].to_list() == [
            "2026-04-08",
            "2026-04-10",
        ]

    def test_backtest_service_options_accept_compiled_expressions(self) -> None:
        """BacktestServiceOptions 接受 compiled_expressions 参数."""
        bridge = FactorBridge()
        compiled = bridge.compile_and_validate(
            expressions=("close",),
            weights=(1.0,),
        )

        options = BacktestServiceOptions(compiled_expressions=compiled)
        assert options.compiled_expressions is not None
        assert options.compiled_expressions.weights == (1.0,)

    def test_default_options_has_no_compiled_expressions(self) -> None:
        """默认 BacktestServiceOptions 的 compiled_expressions 为 None."""
        options = BacktestServiceOptions()
        assert options.compiled_expressions is None
