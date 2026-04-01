"""Port 策略服务工厂。"""

from __future__ import annotations

from dataclasses import replace

from ditto_datahub.services.audit import ExecutionAuditService
from ditto_datahub.services.strategy.strategy_artifact_service import (
    StrategyArtifactService,
)
from ditto_engine.backtest.data_feed import DataFeed
from ditto_engine.backtest.risk.pre_trade import CompositePreTradeCheck
from ditto_engine.execution.brokerage import Brokerage
from ditto_engine.execution.planner import ExecutionPlanner
from ditto_engine.strategy.pipeline import StrategyPipeline

from ditto_port.services.strategy.backtest_runtime_builder import (
    BacktestRuntimeBuilder,
)
from ditto_port.services.strategy.backtest_service import (
    BacktestService,
    BacktestServiceConfig,
    BacktestServiceOptions,
)
from ditto_port.services.strategy.input_assembler import StrategyInputAssembler
from ditto_port.services.strategy.lifecycle import RunLifecycleService
from ditto_port.services.strategy.runtime_builder import StrategyRuntimeBuilder
from ditto_port.services.strategy.strategy_run_service import (
    StrategyRunService,
    StrategyRunServiceConfig,
)

__all__ = ["StrategyServiceFactory"]


class StrategyServiceFactory:
    """为 Port 层策略服务预接控制面依赖的工厂。"""

    def __init__(
        self,
        *,
        audit_service: ExecutionAuditService,
        artifact_service: StrategyArtifactService,
        run_service: RunLifecycleService,
        runtime_builder: StrategyRuntimeBuilder | None = None,
        backtest_runtime_builder: BacktestRuntimeBuilder | None = None,
    ) -> None:
        self._audit_service = audit_service
        self._artifact_service = artifact_service
        self._run_service = run_service
        self._runtime_builder = runtime_builder
        self._backtest_runtime_builder = backtest_runtime_builder

    def build_strategy_run_service(
        self,
        *,
        config: StrategyRunServiceConfig,
        pipeline: StrategyPipeline,
        assembler: StrategyInputAssembler | None = None,
    ) -> StrategyRunService:
        """构造带控制面依赖的 StrategyRunService。"""
        resolved_assembler = assembler or self._build_input_assembler(config)
        return StrategyRunService(
            config=config,
            pipeline=pipeline,
            assembler=resolved_assembler,
            artifact_service=self._artifact_service,
            run_service=self._run_service,
        )

    def build_strategy_run_service_from_catalog(
        self,
        *,
        config: StrategyRunServiceConfig,
        version: int | None = None,
        assembler: StrategyInputAssembler | None = None,
    ) -> StrategyRunService:
        """从 published strategy catalog 直接构造 ``StrategyRunService``。"""
        if self._runtime_builder is None:
            msg = "StrategyRuntimeBuilder 未配置, 无法从 catalog 构造运行服务"
            raise ValueError(msg)
        resolved_version = version
        if resolved_version is None:
            resolved_version = self._parse_catalog_version(config.strategy_version)
        runtime = self._runtime_builder.build_published_runtime(
            config.strategy_id,
            resolved_version,
        )
        resolved_config = replace(
            config,
            strategy_version=str(runtime.record.version),
            spec=runtime.spec,
        )
        return self.build_strategy_run_service(
            config=resolved_config,
            pipeline=runtime.pipeline,
            assembler=assembler,
        )

    def build_backtest_service(
        self,
        *,
        config: BacktestServiceConfig,
        pipeline: StrategyPipeline,
        planner: ExecutionPlanner,
        brokerage: Brokerage,
        pre_trade_check: CompositePreTradeCheck,
        data_feed: DataFeed,
        options: BacktestServiceOptions | None = None,
    ) -> BacktestService:
        """构造带控制面依赖的 BacktestService。"""
        resolved_options = self._build_backtest_options(options)
        return BacktestService(
            config=config,
            pipeline=pipeline,
            planner=planner,
            brokerage=brokerage,
            pre_trade_check=pre_trade_check,
            data_feed=data_feed,
            options=resolved_options,
        )

    def build_backtest_service_from_catalog(
        self,
        *,
        config: BacktestServiceConfig,
        version: int | None = None,
        options: BacktestServiceOptions | None = None,
        source: str = "tushare",
    ) -> BacktestService:
        """从 published strategy catalog 直接构造 ``BacktestService``。"""
        if self._backtest_runtime_builder is None:
            msg = "BacktestRuntimeBuilder 未配置, 无法从 catalog 构造回测服务"
            raise ValueError(msg)
        resolved_version = version
        if resolved_version is None:
            resolved_version = self._parse_catalog_version(config.strategy_version)
        runtime = self._backtest_runtime_builder.build_published_runtime(
            config=config,
            version=resolved_version,
            source=source,
        )
        resolved_options = options or BacktestServiceOptions()
        if resolved_options.fee_model is None:
            resolved_options = replace(
                resolved_options,
                fee_model=runtime.fee_model,
            )
        if resolved_options.display_map is None:
            resolved_options = replace(
                resolved_options,
                display_map=runtime.data_feed.display_map,
            )
        return self.build_backtest_service(
            config=runtime.config,
            pipeline=runtime.pipeline,
            planner=runtime.planner,
            brokerage=runtime.brokerage,
            pre_trade_check=runtime.pre_trade_check,
            data_feed=runtime.data_feed,
            options=resolved_options,
        )

    def _build_input_assembler(
        self,
        config: StrategyRunServiceConfig,
    ) -> StrategyInputAssembler:
        """按运行配置创建默认输入组装器。"""
        parameters: dict[str, object] | None = None
        if config.spec is not None:
            parameters = dict(config.spec.params)
        return StrategyInputAssembler(
            strategy_id=config.strategy_id,
            run_id=config.run_id,
            parameters=parameters,
        )

    def _build_backtest_options(
        self,
        options: BacktestServiceOptions | None,
    ) -> BacktestServiceOptions:
        """将容器内控制面服务并入 BacktestServiceOptions。"""
        if options is None:
            return BacktestServiceOptions(
                audit_service=self._audit_service,
                artifact_service=self._artifact_service,
                run_service=self._run_service,
            )
        return BacktestServiceOptions(
            fee_model=options.fee_model,
            rule_provider=options.rule_provider,
            post_trade_guard=options.post_trade_guard,
            audit_service=options.audit_service or self._audit_service,
            artifact_service=options.artifact_service or self._artifact_service,
            artifact_dir=options.artifact_dir,
            display_map=options.display_map,
            run_service=options.run_service or self._run_service,
        )

    @staticmethod
    def _parse_catalog_version(strategy_version: str) -> int | None:
        """将 run lifecycle 中的版本字符串尽量解析成 catalog version。"""
        if strategy_version == "":
            return None
        try:
            return int(strategy_version)
        except ValueError:
            return None
