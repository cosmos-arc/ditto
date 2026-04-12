"""StrategyServiceFactory 单元测试。"""

from __future__ import annotations

from unittest.mock import MagicMock

from ditto_app.builders import (
    BacktestRuntimeBuilder,
    PublishedBacktestRuntime,
    StrategyServiceFactory,
)
from ditto_app.process.execution.backtest_process import (
    BacktestService,
    BacktestServiceConfig,
    BacktestServiceOptions,
)
from ditto_app.process.execution.strategy_types import RunLifecycleService
from ditto_data.models.strategy import StrategySpecRecord
from ditto_data.services.audit import ExecutionAuditService
from ditto_data.services.strategy.strategy_artifact_service import (
    StrategyArtifactService,
)
from ditto_engine.alpha.pipeline import StrategyPipeline
from ditto_engine.alpha.specs import StrategySpec
from ditto_engine.backtest.data_feed import DataFeed
from ditto_engine.execution.brokerage import BacktestBrokerage
from ditto_engine.execution.planner import SimpleExecutionPlanner
from ditto_engine.execution.reality import SimpleFeeModel
from ditto_engine.risk.pre_trade import CompositePreTradeCheck
from ditto_kernel.identity import InstrumentId


def _make_runtime() -> PublishedBacktestRuntime:
    spec = StrategySpec(
        strategy_id="momentum-etf",
        name="Momentum ETF",
        template="etf_rotation",
        universe="cn_etf",
        asset_class="etf",
        benchmark="000300.SH",
        params={"top_k": 3},
        tags=("momentum", "etf"),
    )
    return PublishedBacktestRuntime(
        record=StrategySpecRecord(
            strategy_id=spec.strategy_id,
            name=spec.name,
            spec_json={},
            version=4,
            status="published",
            tags=spec.tags,
        ),
        spec=spec,
        pipeline=MagicMock(spec=StrategyPipeline),
        planner=SimpleExecutionPlanner(),
        brokerage=MagicMock(spec=BacktestBrokerage),
        pre_trade_check=MagicMock(spec=CompositePreTradeCheck),
        data_feed=MagicMock(spec=DataFeed),
        display_map={
            InstrumentId(2_000_001): "510300.XSHG",
            InstrumentId(2_000_002): "159919.XSHE",
        },
        fee_model=SimpleFeeModel(),
        config=BacktestServiceConfig(
            strategy_id=spec.strategy_id,
            strategy_version="4",
            start_date="2026-01-01",
            end_date="2026-03-01",
            initial_cash=1_000_000.0,
            benchmark_id=InstrumentId(3_000_001),
        ),
    )


class TestStrategyServiceFactory:
    """Port strategy factory 的 catalog-backed backtest 测试。"""

    def test_build_backtest_service_from_catalog_uses_runtime_builder(self) -> None:
        """factory 应使用 BacktestRuntimeBuilder 组装 BacktestService。"""
        runtime = _make_runtime()
        runtime_builder = MagicMock(spec=BacktestRuntimeBuilder)
        runtime_builder.build_published_runtime.return_value = runtime
        factory = StrategyServiceFactory(
            audit_service=MagicMock(spec=ExecutionAuditService),
            artifact_service=MagicMock(spec=StrategyArtifactService),
            run_service=MagicMock(spec=RunLifecycleService),
            backtest_runtime_builder=runtime_builder,
        )

        service = factory.build_backtest_service_from_catalog(
            config=BacktestServiceConfig(
                strategy_id="momentum-etf",
                start_date="2026-01-01",
                end_date="2026-03-01",
                initial_cash=1_000_000.0,
            ),
            version=4,
        )

        assert isinstance(service, BacktestService)
        assert service._config.strategy_version == "4"
        assert service._pipeline is runtime.pipeline
        assert service._planner is runtime.planner
        assert service._brokerage is runtime.brokerage
        assert service._pre_trade_check is runtime.pre_trade_check
        assert service._data_feed is runtime.data_feed
        assert service._options.fee_model is runtime.fee_model
        call_kwargs = runtime_builder.build_published_runtime.call_args.kwargs
        assert call_kwargs["config"].strategy_id == "momentum-etf"
        assert call_kwargs["version"] == 4
        assert call_kwargs["source"] == "tushare"
        assert call_kwargs["fee_model"] is None
        assert call_kwargs["slippage_model"] is None

    def test_build_backtest_options_preserves_display_map(self) -> None:
        """_build_backtest_options 保留调用方传入的 display_map。"""
        factory = StrategyServiceFactory(
            audit_service=MagicMock(spec=ExecutionAuditService),
            artifact_service=MagicMock(spec=StrategyArtifactService),
            run_service=MagicMock(spec=RunLifecycleService),
        )
        display_map = {InstrumentId(1): "510300.SH"}
        options = BacktestServiceOptions(display_map=display_map)
        result = factory._build_backtest_options(options)
        assert result.display_map is display_map

    def test_build_backtest_options_preserves_compiled_expressions(self) -> None:
        """_build_backtest_options 保留调用方传入的 compiled_expressions (R2)."""
        factory = StrategyServiceFactory(
            audit_service=MagicMock(spec=ExecutionAuditService),
            artifact_service=MagicMock(spec=StrategyArtifactService),
            run_service=MagicMock(spec=RunLifecycleService),
        )
        compiled = MagicMock(name="compiled_expressions")
        options = BacktestServiceOptions(compiled_expressions=compiled)
        result = factory._build_backtest_options(options)
        assert result.compiled_expressions is compiled

    def test_build_backtest_service_from_catalog_injects_display_map(self) -> None:
        """catalog-backed 路径自动从 runtime.display_map 注入 display_map。"""
        from dataclasses import replace

        test_display_map = {InstrumentId(1): "510300.SH"}

        runtime = _make_runtime()
        runtime = replace(runtime, display_map=test_display_map)

        runtime_builder = MagicMock(spec=BacktestRuntimeBuilder)
        runtime_builder.build_published_runtime.return_value = runtime
        factory = StrategyServiceFactory(
            audit_service=MagicMock(spec=ExecutionAuditService),
            artifact_service=MagicMock(spec=StrategyArtifactService),
            run_service=MagicMock(spec=RunLifecycleService),
            backtest_runtime_builder=runtime_builder,
        )

        service = factory.build_backtest_service_from_catalog(
            config=BacktestServiceConfig(
                strategy_id="momentum-etf",
                start_date="2026-01-01",
                end_date="2026-03-01",
                initial_cash=1_000_000.0,
            ),
            version=4,
        )

        assert service._options.display_map == test_display_map

    def test_build_backtest_options_preserves_slippage_model(self) -> None:
        """_build_backtest_options 保留调用方传入的 slippage_model (R6)."""
        from ditto_engine.execution.reality.slippage import FixedBpsSlippage

        factory = StrategyServiceFactory(
            audit_service=MagicMock(spec=ExecutionAuditService),
            artifact_service=MagicMock(spec=StrategyArtifactService),
            run_service=MagicMock(spec=RunLifecycleService),
        )
        slippage = FixedBpsSlippage(bps=5.0)
        options = BacktestServiceOptions(slippage_model=slippage)
        result = factory._build_backtest_options(options)
        assert result.slippage_model is slippage


class TestBuildPublishedRuntimeCostModels:
    """build_published_runtime 接受自定义 fee_model / slippage_model (R6)."""

    def test_custom_fee_model_passed_to_brokerage(self) -> None:
        """自定义 fee_model 传入 BrokerageModel。"""
        from ditto_engine.execution.reality import AShareFeeModel

        runtime = _make_runtime()
        runtime_builder = MagicMock(spec=BacktestRuntimeBuilder)
        runtime_builder.build_published_runtime.return_value = runtime
        factory = StrategyServiceFactory(
            audit_service=MagicMock(spec=ExecutionAuditService),
            artifact_service=MagicMock(spec=StrategyArtifactService),
            run_service=MagicMock(spec=RunLifecycleService),
            backtest_runtime_builder=runtime_builder,
        )

        custom_fee = AShareFeeModel()
        service = factory.build_backtest_service_from_catalog(
            config=BacktestServiceConfig(
                strategy_id="momentum-etf",
                start_date="2026-01-01",
                end_date="2026-03-01",
                initial_cash=1_000_000.0,
            ),
            version=4,
            options=BacktestServiceOptions(fee_model=custom_fee),
        )

        assert service._options.fee_model is custom_fee

    def test_default_fee_model_from_runtime_when_not_provided(self) -> None:
        """未提供 fee_model 时使用 runtime 默认值。"""
        runtime = _make_runtime()
        runtime_builder = MagicMock(spec=BacktestRuntimeBuilder)
        runtime_builder.build_published_runtime.return_value = runtime
        factory = StrategyServiceFactory(
            audit_service=MagicMock(spec=ExecutionAuditService),
            artifact_service=MagicMock(spec=StrategyArtifactService),
            run_service=MagicMock(spec=RunLifecycleService),
            backtest_runtime_builder=runtime_builder,
        )

        service = factory.build_backtest_service_from_catalog(
            config=BacktestServiceConfig(
                strategy_id="momentum-etf",
                start_date="2026-01-01",
                end_date="2026-03-01",
                initial_cash=1_000_000.0,
            ),
            version=4,
        )

        assert service._options.fee_model is runtime.fee_model

    def test_build_published_runtime_accepts_slippage_model(self) -> None:
        """build_published_runtime 接受 slippage_model 参数。"""
        from ditto_engine.execution.reality.slippage import FixedBpsSlippage

        runtime = _make_runtime()
        runtime_builder = MagicMock(spec=BacktestRuntimeBuilder)
        runtime_builder.build_published_runtime.return_value = runtime
        factory = StrategyServiceFactory(
            audit_service=MagicMock(spec=ExecutionAuditService),
            artifact_service=MagicMock(spec=StrategyArtifactService),
            run_service=MagicMock(spec=RunLifecycleService),
            backtest_runtime_builder=runtime_builder,
        )

        custom_slippage = FixedBpsSlippage(bps=5.0)
        service = factory.build_backtest_service_from_catalog(
            config=BacktestServiceConfig(
                strategy_id="momentum-etf",
                start_date="2026-01-01",
                end_date="2026-03-01",
                initial_cash=1_000_000.0,
            ),
            version=4,
            options=BacktestServiceOptions(slippage_model=custom_slippage),
        )

        assert service._options.slippage_model is custom_slippage
