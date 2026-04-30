"""FactorBridge 回测集成测试 — 验证因子信号注入回测流程."""

from __future__ import annotations

from unittest.mock import MagicMock

from ditto_application.process.execution.backtest_process import (
    BacktestService,
    BacktestServiceConfig,
    BacktestServiceOptions,
)
from ditto_application.process.execution.factor_bridge import (
    FactorBridge,
)
from ditto_engine.backtest.data_feed import Slice
from ditto_engine.backtest.steps import StepContext
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


def _make_step_context(date: str, slice_: Slice) -> StepContext:
    """构造测试用 StepContext."""
    ctx = MagicMock(spec=StepContext)
    ctx.date = date
    ctx.slice_ = slice_
    return ctx


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
