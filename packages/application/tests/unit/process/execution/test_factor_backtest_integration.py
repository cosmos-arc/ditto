"""FactorBridge 回测集成测试 — 验证因子信号注入回测流程."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from typing import get_type_hints
from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_application.processes.execution._factor_bundle import (
    build_factor_aware_bundle_builder as build_factor_aware_bundle_builder_impl,
)
from ditto_application.processes.execution._factor_bundle import (
    build_factor_bundle as build_factor_bundle_impl,
)
from ditto_application.processes.execution.backtest_process import (
    BacktestService,
    BacktestServiceConfig,
    BacktestServiceOptions,
)
from ditto_application.processes.execution.factor_bridge import (
    CompiledExpressions,
    FactorBridge,
    build_factor_aware_bundle_builder,
    build_factor_bundle,
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

    def trading_days(self) -> list[str]:
        return []

    def get_slice(self, date: str) -> Slice:
        raise NotImplementedError

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

    def get_fundamental_snapshot(
        self,
        instrument_ids: Sequence[InstrumentId],
        as_of_date: date,
    ) -> pl.DataFrame:
        """Stub: 该 fake 不提供基本面数据，返回空 DataFrame（is_empty 触发跳过注入）."""
        return pl.DataFrame()

    def get_classification_snapshot(
        self,
        instrument_ids: Sequence[InstrumentId],
        as_of_date: date,
    ) -> pl.DataFrame:
        """Stub: 不提供行业分类数据，返回空 DataFrame（is_empty 触发跳过）."""
        return pl.DataFrame()


class TestFactorAwareBundleBuilder:
    """验证含因子信号注入的 input_bundle_builder."""

    def test_public_bundle_type_hints_resolve_at_runtime(self) -> None:
        bundle_hints = get_type_hints(build_factor_bundle)
        factory_hints = get_type_hints(build_factor_aware_bundle_builder)

        assert bundle_hints["bridge"] is FactorBridge
        assert bundle_hints["compiled"] is CompiledExpressions
        assert factory_hints["bridge"] is FactorBridge
        assert factory_hints["compiled"] is CompiledExpressions

    def test_internal_bundle_type_hints_are_self_contained(self) -> None:
        """The cycle-free implementation must not depend on facade side effects."""
        bundle_hints = get_type_hints(build_factor_bundle_impl)
        factory_hints = get_type_hints(build_factor_aware_bundle_builder_impl)

        assert {"bridge", "compiled", "return"} <= bundle_hints.keys()
        assert {"bridge", "compiled", "return"} <= factory_hints.keys()

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
            spec_hash="a" * 64,
            base_spec_hash="b" * 64,
            parameter_hash="4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
            effective_parameters=(),
            research_snapshot_id=None,
            research_snapshot_manifest_hash=None,
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
            spec_hash="a" * 64,
            base_spec_hash="b" * 64,
            parameter_hash="4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
            effective_parameters=(),
            research_snapshot_id=None,
            research_snapshot_manifest_hash=None,
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
        assert bundle.signal_values is not None

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
                spec_hash="a" * 64,
                base_spec_hash="b" * 64,
                parameter_hash="4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
                effective_parameters=(),
                research_snapshot_id=None,
                research_snapshot_manifest_hash=None,
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


class TestFactorBundleFundamentalInjection:
    """RED-4: build_factor_bundle 注入基本面截面 + 补算 pe_ratio."""

    def test_injects_roe_and_pe_ratio_to_today_rows(self) -> None:
        """注入后当日 market_data 含 roe/pe_ratio 列，pe_ratio = close / eps."""
        bridge = FactorBridge()
        compiled = bridge.compile_and_validate(
            expressions=("quality_roe",),
            weights=(1.0,),
        )
        data_feed = MagicMock()
        data_feed.get_history.return_value = pl.DataFrame()
        data_feed.get_fundamental_snapshot.return_value = pl.DataFrame(
            {
                "instrument_id": [1, 2, 3],
                "roe": [0.15, 0.10, 0.20],
                "net_margin": [0.12, 0.08, 0.18],
                "eps": [1.5, 2.0, 2.5],
            },
        )

        ctx = _make_step_context("2024-01-02", _make_slice_with_bars())
        bundle = build_factor_bundle(
            ctx=ctx,
            strategy_id="t",
            run_id="t",
            bridge=bridge,
            compiled=compiled,
            data_feed=data_feed,
            lookback_days=20,
        )
        assert bundle.signal_values is not None

        today = bundle.market_data.filter(pl.col("trade_date") == "2024-01-02")
        assert "roe" in today.columns
        assert "pe_ratio" in today.columns
        # bar1 close=10.5, eps=1.5 → pe_ratio ≈ 7.0
        today_sorted = today.sort("instrument_id")
        assert today_sorted["pe_ratio"][0] == pytest.approx(7.0)
        # quality_roe → roe 列 → signal_value 产出（不再 ColumnNotFoundError）
        assert bundle.signal_values.height == 3
        assert "signal_value" in bundle.signal_values.columns

    def test_carries_pit_industry_and_market_cap_into_instrument_frame(self) -> None:
        """The final strategy frame retains exact exposure source values."""
        bridge = FactorBridge()
        compiled = bridge.compile_and_validate(
            expressions=("quality_roe",),
            weights=(1.0,),
        )
        data_feed = MagicMock()
        data_feed.get_history.return_value = pl.DataFrame()
        data_feed.get_fundamental_snapshot.return_value = pl.DataFrame(
            {
                "instrument_id": [1, 2, 3],
                "roe": [0.15, 0.10, 0.20],
                "eps": [1.5, 2.0, 2.5],
                "market_cap": [8.0, 30.0, 90.0],
            },
        )
        data_feed.get_classification_snapshot.return_value = pl.DataFrame(
            {
                "instrument_id": [1, 2, 3],
                "sector_id": ["bank", "tech", "bank"],
            },
        )

        bundle = build_factor_bundle(
            ctx=_make_step_context("2024-01-02", _make_slice_with_bars()),
            strategy_id="t",
            run_id="t",
            bridge=bridge,
            compiled=compiled,
            data_feed=data_feed,
            lookback_days=20,
        )

        assert bundle.instruments.sort("instrument_id").to_dict(as_series=False) == {
            "instrument_id": [1, 2, 3],
            "sector_id": ["bank", "tech", "bank"],
            "market_cap": [8.0, 30.0, 90.0],
        }

    def test_fundamental_snapshot_uses_knowledge_date(self) -> None:
        """get_fundamental_snapshot 的 as_of = knowledge_date（PIT，非 trade_date）."""
        bridge = FactorBridge()
        compiled = bridge.compile_and_validate(
            expressions=("quality_roe",),
            weights=(1.0,),
        )
        data_feed = MagicMock()
        data_feed.get_history.return_value = pl.DataFrame()
        data_feed.get_fundamental_snapshot.return_value = pl.DataFrame(
            {
                "instrument_id": [1, 2, 3],
                "roe": [0.15, 0.10, 0.20],
                "net_margin": [0.12, 0.08, 0.18],
                "eps": [1.5, 2.0, 2.5],
            },
        )

        ctx = _make_step_context("2024-01-02", _make_slice_with_bars())
        # _make_step_context: knowledge_date=2024-01-01, trade_date=2024-01-02
        build_factor_bundle(
            ctx=ctx,
            strategy_id="t",
            run_id="t",
            bridge=bridge,
            compiled=compiled,
            data_feed=data_feed,
            lookback_days=20,
        )

        # PIT: as_of 必须是 knowledge_date（2024-01-01），不是 trade_date（2024-01-02）
        call = data_feed.get_fundamental_snapshot.call_args
        assert call.args[1] == date(2024, 1, 1)

    def test_empty_fundamental_skips_injection(self) -> None:
        """无基本面数据时 market_data 不含基本面列，纯市场因子仍工作."""
        bridge = FactorBridge()
        compiled = bridge.compile_and_validate(
            expressions=("close",),
            weights=(1.0,),
        )
        data_feed = MagicMock()
        data_feed.get_history.return_value = pl.DataFrame()
        data_feed.get_fundamental_snapshot.return_value = pl.DataFrame()

        ctx = _make_step_context("2024-01-02", _make_slice_with_bars())
        bundle = build_factor_bundle(
            ctx=ctx,
            strategy_id="t",
            run_id="t",
            bridge=bridge,
            compiled=compiled,
            data_feed=data_feed,
            lookback_days=20,
        )
        assert bundle.signal_values is not None

        assert "roe" not in bundle.market_data.columns
        assert "pe_ratio" not in bundle.market_data.columns
        assert bundle.signal_values.height == 3

    def test_quality_roe_and_value_pe_run_without_column_not_found(self) -> None:
        """seed quality_roe + value_pe 注入后不报 ColumnNotFoundError."""
        bridge = FactorBridge()
        compiled = bridge.compile_and_validate(
            expressions=("quality_roe", "value_pe"),
            weights=(0.5, 0.5),
        )
        data_feed = MagicMock()
        data_feed.get_history.return_value = pl.DataFrame()
        data_feed.get_fundamental_snapshot.return_value = pl.DataFrame(
            {
                "instrument_id": [1, 2, 3],
                "roe": [0.15, 0.10, 0.20],
                "net_margin": [0.12, 0.08, 0.18],
                "eps": [1.5, 2.0, 2.5],
            },
        )

        ctx = _make_step_context("2024-01-02", _make_slice_with_bars())
        bundle = build_factor_bundle(
            ctx=ctx,
            strategy_id="t",
            run_id="t",
            bridge=bridge,
            compiled=compiled,
            data_feed=data_feed,
            lookback_days=20,
        )
        assert bundle.signal_values is not None

        # quality_roe→roe, value_pe→-pe_ratio 两因子都能计算
        assert bundle.signal_values.height == 3
        values = bundle.signal_values["signal_value"].to_list()
        assert all(isinstance(v, float) for v in values)
