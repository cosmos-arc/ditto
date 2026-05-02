"""App 策略服务工厂 — 含 BacktestRuntimeBuilder 与 StrategyServiceFactory."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, timedelta

from ditto_backtest.data_feed import (
    DataFeed,
    ProviderBackedDataFeed,
)
from ditto_data.provider import DataProvider
from ditto_data.services.metadata_service import MetadataService
from ditto_execution.audit import ExecutionAuditService
from ditto_execution.brokerage import BacktestBrokerage, Brokerage
from ditto_execution.planner import ExecutionPlanner, SimpleExecutionPlanner
from ditto_execution.reality import AShareFeeModel, BrokerageModel
from ditto_execution.reality.slippage import FixedBpsSlippage, SlippageModel
from ditto_kernel.identity import InstrumentId
from ditto_kernel.trading import FeeModel
from ditto_portfolio.accounting.account import Account
from ditto_portfolio.accounting.cash import CashBook
from ditto_risk.pre_trade import (
    BuyingPowerCheck,
    CompositePreTradeCheck,
    LotSizeCheck,
)
from ditto_strategy.alpha.pipeline import StrategyPipeline
from ditto_strategy.alpha.specs import StrategySpec
from ditto_strategy.models import StrategySpecRecord
from ditto_strategy.storage.sqlite.services.strategy_artifact_service import (
    StrategyArtifactService,
)

from ditto_application.builders._resolution import (
    resolve_benchmark,
    resolve_instrument_display,
)
from ditto_application.builders.runtime_builder import StrategyRuntimeBuilder
from ditto_application.contracts import REGIME_DEFAULT_LOOKBACK
from ditto_application.processes.execution.backtest_process import (
    BacktestService,
    BacktestServiceConfig,
    BacktestServiceOptions,
)
from ditto_application.processes.execution.factor_bridge import CompiledExpressions
from ditto_application.processes.execution.strategy_input import StrategyInputAssembler
from ditto_application.processes.execution.strategy_run_process import (
    StrategyRunService,
    StrategyRunServiceConfig,
)
from ditto_application.processes.execution.strategy_types import RunLifecycleService

__all__ = [
    "BacktestRuntimeBuilder",
    "PublishedBacktestRuntime",
    "StrategyServiceFactory",
]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _compute_max_lookback(
    compiled: CompiledExpressions | None,
) -> int:
    """计算因子表达式所需最大 lookback 天数."""
    if compiled is None:
        return REGIME_DEFAULT_LOOKBACK
    return max(
        (expr.analysis.lookback for expr in compiled.expressions),
        default=REGIME_DEFAULT_LOOKBACK,
    )


def _shift_back_calendar_days(date_str: str, days: int) -> str:
    """将 YYYY-MM-DD 向前偏移 days 个日历日。"""
    d = date.fromisoformat(date_str) - timedelta(days=days)
    return d.isoformat()


# ===========================================================================
# PublishedBacktestRuntime
# ===========================================================================


@dataclass(frozen=True)
class PublishedBacktestRuntime:
    """从 published strategy 派生出的完整回测运行时。"""

    record: StrategySpecRecord
    spec: StrategySpec
    pipeline: StrategyPipeline
    planner: SimpleExecutionPlanner
    brokerage: BacktestBrokerage
    pre_trade_check: CompositePreTradeCheck
    data_feed: DataFeed
    display_map: dict[InstrumentId, str]
    fee_model: FeeModel
    config: BacktestServiceConfig
    compiled_expressions: CompiledExpressions | None = None


# ===========================================================================
# BacktestRuntimeBuilder
# ===========================================================================


class BacktestRuntimeBuilder:
    """为 published strategy 组装最小可运行回测依赖。"""

    def __init__(
        self,
        *,
        strategy_runtime_builder: StrategyRuntimeBuilder,
        metadata_service: MetadataService,
        data_provider: DataProvider,
    ) -> None:
        self._strategy_runtime_builder = strategy_runtime_builder
        self._metadata_service = metadata_service
        self._data_provider = data_provider

    def build_published_runtime(
        self,
        *,
        config: BacktestServiceConfig,
        version: int | None = None,
        source: str = "tushare",
        fee_model: FeeModel | None = None,
        slippage_model: SlippageModel | None = None,
    ) -> PublishedBacktestRuntime:
        """从 published strategy catalog 构造回测运行时。"""
        runtime = self._strategy_runtime_builder.build_published_runtime(
            config.strategy_id,
            version,
        )
        resolved_fee_model = fee_model or AShareFeeModel()
        resolved_slippage = slippage_model or FixedBpsSlippage()
        brokerage = BacktestBrokerage(
            account=Account(
                cash=CashBook(
                    available=config.initial_cash,
                    settled=config.initial_cash,
                    frozen=0.0,
                )
            ),
            model=BrokerageModel(
                fee_model=resolved_fee_model,
                slippage_model=resolved_slippage,
            ),
        )
        benchmark_id = resolve_benchmark(
            runtime.spec.benchmark,
            self._metadata_service,
            source,
            config.start_date,
            config_benchmark=config.benchmark_id,
        )
        resolved_config = replace(
            config,
            strategy_version=str(runtime.record.version),
            benchmark_id=benchmark_id,
        )

        # 解析 universe → tickers + id_map + display_map
        universe_ids = self._metadata_service.get_universe(
            runtime.spec.universe,
            asof=config.start_date,
        )
        resolution = resolve_instrument_display(universe_ids, self._metadata_service)
        tickers = resolution.tickers
        id_map = resolution.id_map
        display_map = resolution.display_map

        # 计算数据加载起点：考虑因子表达式 lookback + Regime 默认 lookback
        max_lookback = _compute_max_lookback(runtime.compiled_expressions)
        data_start_date = _shift_back_calendar_days(config.start_date, max_lookback * 2)

        data_feed = ProviderBackedDataFeed(
            self._data_provider,
            tickers=tickers,
            start_date=data_start_date,
            end_date=config.end_date,
            id_map=id_map,
            benchmark_id=resolved_config.benchmark_id,
        )

        return PublishedBacktestRuntime(
            record=runtime.record,
            spec=runtime.spec,
            pipeline=runtime.pipeline,
            planner=SimpleExecutionPlanner(),
            brokerage=brokerage,
            pre_trade_check=CompositePreTradeCheck(
                checks=(LotSizeCheck(), BuyingPowerCheck()),
            ),
            data_feed=data_feed,
            display_map=display_map,
            fee_model=resolved_fee_model,
            config=resolved_config,
            compiled_expressions=runtime.compiled_expressions,
        )


# ===========================================================================
# StrategyServiceFactory
# ===========================================================================


class StrategyServiceFactory:
    """为 App 层策略服务预接控制面依赖的工厂。"""

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
        resolved_options = options or BacktestServiceOptions()
        runtime = self._backtest_runtime_builder.build_published_runtime(
            config=config,
            version=resolved_version,
            source=source,
            fee_model=resolved_options.fee_model,
            slippage_model=resolved_options.slippage_model,
        )
        if resolved_options.fee_model is None:
            resolved_options = replace(
                resolved_options,
                fee_model=runtime.fee_model,
            )
        if resolved_options.display_map is None:
            resolved_options = replace(
                resolved_options,
                display_map=runtime.display_map,
            )
        if resolved_options.compiled_expressions is None:
            resolved_options = replace(
                resolved_options,
                compiled_expressions=runtime.compiled_expressions,
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

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

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
            slippage_model=options.slippage_model,
            rule_provider=options.rule_provider,
            post_trade_guard=options.post_trade_guard,
            compiled_expressions=options.compiled_expressions,
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
