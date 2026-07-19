"""App 策略服务工厂 — 含 BacktestRuntimeBuilder 与 StrategyServiceFactory."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, timedelta

from ditto_backtest.brokerage import BacktestBrokerage
from ditto_backtest.data_feed import (
    DataFeed,
    ProviderBackedDataFeed,
    SnapshotProviders,
)
from ditto_backtest.result import (
    BacktestAccountStateSnapshot,
    BacktestPendingOrderSnapshot,
    BacktestRuntimeStateSnapshot,
    BacktestSettlementStateSnapshot,
)
from ditto_backtest.simulation import BrokerageModel
from ditto_backtest.simulation.fill import AShareFillModel
from ditto_backtest.simulation.slippage import FixedBpsSlippage, SlippageModel
from ditto_data.catalog.promotion import DatasetMaturityPromotionReader
from ditto_data.lineage import DataLineageRecorder
from ditto_data.provider import DataProvider
from ditto_data.services.metadata_service import MetadataService
from ditto_execution.audit import ExecutionAuditService
from ditto_execution.brokerage import Brokerage
from ditto_execution.orders.book import OrderBook
from ditto_execution.orders.ids import ClientOrderId
from ditto_execution.orders.journal import InMemoryOrderEventJournal
from ditto_execution.orders.model import Order
from ditto_execution.orders.status import OrderStatus
from ditto_execution.orders.ticket import OrderTicket
from ditto_execution.planner import ExecutionPlanner, SimpleExecutionPlanner
from ditto_execution.reality import AShareFeeModel
from ditto_kernel.identity import InstrumentId
from ditto_kernel.order import OrderSide, OrderType
from ditto_kernel.trading import FeeModel
from ditto_portfolio.accounting import Account, CashBook, Position
from ditto_risk.pre_trade import (
    BuyingPowerCheck,
    CompositePreTradeCheck,
    LotSizeCheck,
)
from ditto_strategy.alpha.parameters import EffectiveParameter
from ditto_strategy.alpha.pipeline import StrategyPipeline
from ditto_strategy.alpha.specs import StrategySpec
from ditto_strategy.models import StrategySpecRecord
from ditto_strategy.storage.sqlite.services.strategy_artifact_service import (
    StrategyArtifactService,
)
from ditto_strategy.storage.sqlite.services.strategy_run_service import (
    StrategyRunCheckpointWriterProtocol,
)

from ditto_application.builders._resolution import (
    resolve_benchmark,
    resolve_instrument_display,
)
from ditto_application.builders.runtime_builder import StrategyRuntimeBuilder
from ditto_application.catalog_maturity import assert_strategy_runtime_data_allowed
from ditto_application.contracts import REGIME_DEFAULT_LOOKBACK
from ditto_application.exceptions import AppBuilderError
from ditto_application.processes.execution.backtest_process import (
    BacktestCatalogRequestConfig,
    BacktestService,
    BacktestServiceConfig,
    BacktestServiceOptions,
)
from ditto_application.processes.execution.classification_snapshot import (
    ClassificationReadFacade,
    build_classification_snapshot_fn,
)
from ditto_application.processes.execution.factor_bridge import CompiledExpressions
from ditto_application.processes.execution.fundamental_snapshot import (
    FundamentalReadFacade,
    build_fundamental_snapshot_fn,
)
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


def _load_account_state(
    config: BacktestCatalogRequestConfig,
) -> BacktestAccountStateSnapshot | None:
    """Load verified account-state resume evidence from config."""
    if not config.resume_account_state_json:
        return None
    try:
        snapshot = BacktestAccountStateSnapshot.from_json(
            config.resume_account_state_json,
        )
    except ValueError as exc:
        msg = "Invalid resume_account_state_json"
        raise AppBuilderError(msg) from exc
    _assert_resume_hash(
        label="resume_account_state_hash",
        expected=config.resume_account_state_hash,
        actual=snapshot.state_hash,
    )
    return snapshot


def _load_settlement_state(
    config: BacktestCatalogRequestConfig,
) -> BacktestSettlementStateSnapshot | None:
    """Load verified settlement-state resume evidence from config."""
    if not config.resume_settlement_state_json:
        return None
    try:
        snapshot = BacktestSettlementStateSnapshot.from_json(
            config.resume_settlement_state_json,
        )
    except ValueError as exc:
        msg = "Invalid resume_settlement_state_json"
        raise AppBuilderError(msg) from exc
    _assert_resume_hash(
        label="resume_settlement_state_hash",
        expected=config.resume_settlement_state_hash,
        actual=snapshot.state_hash,
    )
    return snapshot


def _load_runtime_state(
    config: BacktestCatalogRequestConfig,
) -> BacktestRuntimeStateSnapshot | None:
    """Load verified runtime-state resume evidence from config."""
    if not config.resume_runtime_state_json:
        return None
    try:
        snapshot = BacktestRuntimeStateSnapshot.from_json(
            config.resume_runtime_state_json,
        )
    except ValueError as exc:
        msg = "Invalid resume_runtime_state_json"
        raise AppBuilderError(msg) from exc
    _assert_resume_hash(
        label="resume_runtime_state_hash",
        expected=config.resume_runtime_state_hash,
        actual=snapshot.state_hash,
    )
    return snapshot


def _assert_resume_hash(*, label: str, expected: str, actual: str) -> None:
    """Validate optional checkpoint hash evidence when provided."""
    if expected and expected != actual:
        msg = f"{label} mismatch: expected {expected}, got {actual}"
        raise AppBuilderError(msg)


def _build_fill_model(config: BacktestCatalogRequestConfig) -> AShareFillModel:
    """Build the configured A-share fill model for backtests."""
    participation_rate = (
        0.0 if config.fill_mode == "all_or_nothing" else config.participation_rate
    )
    return AShareFillModel(participation_rate=participation_rate)


def _build_account(
    *,
    initial_cash: float,
    account_state: BacktestAccountStateSnapshot | None,
) -> Account:
    """Build a mutable Account from initial cash or checkpoint state."""
    if account_state is None:
        return Account(
            cash=CashBook(
                available=initial_cash,
                settled=initial_cash,
                frozen=0.0,
            )
        )
    return Account(
        positions={
            position.instrument_id: Position(
                instrument_id=position.instrument_id,
                quantity=position.quantity,
                available_quantity=position.available_quantity,
                average_cost=position.average_cost,
                market_value=position.market_value,
                unrealized_pnl=position.unrealized_pnl,
                realized_pnl=position.realized_pnl,
                total_fees=position.total_fees,
            )
            for position in account_state.positions
        },
        cash=CashBook(
            available=account_state.cash_available,
            settled=account_state.cash_settled,
            frozen=account_state.cash_frozen,
        ),
    )


def _build_order_ticket(snapshot: BacktestPendingOrderSnapshot) -> OrderTicket:
    """Build an execution ticket from checkpoint pending-order state."""
    return OrderTicket(
        order=Order(
            client_id=ClientOrderId(snapshot.client_order_id),
            instrument_id=snapshot.instrument_id,
            order_type=OrderType(snapshot.order_type),
            direction=OrderSide(snapshot.direction),
            quantity=snapshot.quantity,
            price=snapshot.price,
            stop_price=snapshot.stop_price,
            trade_date=snapshot.trade_date,
        ),
        status=OrderStatus(snapshot.status),
        filled_quantity=snapshot.filled_quantity,
        filled_price=snapshot.filled_price,
        average_fill_price=snapshot.average_fill_price,
    )


def _build_order_book(
    runtime_state: BacktestRuntimeStateSnapshot | None,
) -> OrderBook:
    """Build an OrderBook and restore pending tickets when provided."""
    order_book = OrderBook(journal=InMemoryOrderEventJournal())
    if runtime_state is None:
        return order_book
    for pending_order in runtime_state.pending_orders:
        order_book.restore_ticket(_build_order_ticket(pending_order))
    return order_book


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


def _resolve_backtest_catalog_request(
    config: BacktestCatalogRequestConfig,
    *,
    strategy_version: str,
    benchmark_id: InstrumentId | None,
    base_spec_hash: str,
    spec_hash: str,
    parameter_hash: str,
    effective_parameters: tuple[EffectiveParameter, ...],
) -> BacktestServiceConfig:
    """Resolve a catalog launch request without dropping any request field."""
    return BacktestServiceConfig(
        strategy_id=config.strategy_id,
        strategy_version=strategy_version,
        run_id=config.run_id,
        parent_run_id=config.parent_run_id,
        start_date=config.start_date,
        end_date=config.end_date,
        initial_cash=config.initial_cash,
        benchmark_id=benchmark_id,
        parameter_overrides=(),
        candidate_parameters=config.candidate_parameters,
        research_snapshot_id=config.research_snapshot_id,
        research_snapshot_manifest_hash=config.research_snapshot_manifest_hash,
        rebalance_freq=config.rebalance_freq,
        engine_version=config.engine_version,
        execution_delay=config.execution_delay,
        code_version=config.code_version,
        data_catalog_identities=config.data_catalog_identities,
        factor_report_refs=config.factor_report_refs,
        recommendation_status=config.recommendation_status,
        participation_rate=config.participation_rate,
        fill_mode=config.fill_mode,
        resume_from_run_id=config.resume_from_run_id,
        resume_checkpoint_trade_date=config.resume_checkpoint_trade_date,
        resume_checkpoint_completed_days=config.resume_checkpoint_completed_days,
        resume_checkpoint_total_days=config.resume_checkpoint_total_days,
        resume_checkpoint_nav=config.resume_checkpoint_nav,
        resume_checkpoint_order_count=config.resume_checkpoint_order_count,
        resume_checkpoint_fill_count=config.resume_checkpoint_fill_count,
        resume_account_state_json=config.resume_account_state_json,
        resume_account_state_hash=config.resume_account_state_hash,
        resume_settlement_state_json=config.resume_settlement_state_json,
        resume_settlement_state_hash=config.resume_settlement_state_hash,
        resume_runtime_state_json=config.resume_runtime_state_json,
        resume_runtime_state_hash=config.resume_runtime_state_hash,
        base_spec_hash=base_spec_hash,
        spec_hash=spec_hash,
        parameter_hash=parameter_hash,
        effective_parameters=effective_parameters,
    )


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
        maturity_promotion_reader: DatasetMaturityPromotionReader | None = None,
        fundamental_read_facade: FundamentalReadFacade | None = None,
        classification_read_facade: ClassificationReadFacade | None = None,
    ) -> None:
        self._strategy_runtime_builder = strategy_runtime_builder
        self._metadata_service = metadata_service
        self._data_provider = data_provider
        self._maturity_promotion_reader = maturity_promotion_reader
        self._fundamental_read_facade = fundamental_read_facade
        self._classification_read_facade = classification_read_facade

    def build_published_runtime(
        self,
        *,
        config: BacktestCatalogRequestConfig,
        version: int | None = None,
        source: str = "tushare",
        fee_model: FeeModel | None = None,
        slippage_model: SlippageModel | None = None,
        allow_experimental_data: bool = False,
    ) -> PublishedBacktestRuntime:
        """从 published strategy catalog 构造回测运行时。"""
        runtime = self._strategy_runtime_builder.build_published_runtime(
            config.strategy_id,
            version,
            candidate_parameters=config.candidate_parameters,
        )
        assert_strategy_runtime_data_allowed(
            runtime.spec,
            allow_experimental_data=allow_experimental_data,
            maturity_promotion_reader=self._maturity_promotion_reader,
            context="catalog-backed backtest",
        )
        resolved_fee_model = fee_model or AShareFeeModel()
        resolved_slippage = slippage_model or FixedBpsSlippage()
        account_state = _load_account_state(config)
        settlement_state = _load_settlement_state(config)
        runtime_state = _load_runtime_state(config)
        brokerage = BacktestBrokerage(
            account=_build_account(
                initial_cash=config.initial_cash,
                account_state=account_state,
            ),
            order_book=_build_order_book(runtime_state),
            model=BrokerageModel(
                fill_model=_build_fill_model(config),
                fee_model=resolved_fee_model,
                slippage_model=resolved_slippage,
            ),
        )
        if settlement_state is not None:
            brokerage.restore_settlement_state(settlement_state)
        benchmark_id = resolve_benchmark(
            runtime.spec.benchmark,
            self._metadata_service,
            source,
            config.start_date,
            config_benchmark=config.benchmark_id,
        )
        resolved_config = _resolve_backtest_catalog_request(
            config,
            strategy_version=str(runtime.record.version),
            benchmark_id=benchmark_id,
            base_spec_hash=runtime.base_spec_hash,
            spec_hash=runtime.spec_hash,
            parameter_hash=runtime.parameter_hash,
            effective_parameters=runtime.effective_parameters,
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

        # 基本面快照闭包：注入 DataFeed 数据通道，供 quality_roe / value_pe 等因子引用。
        # maturity gate 经 facade 的 allow_experimental_data 生效。
        fundamental_snapshot_fn = None
        if self._fundamental_read_facade is not None:
            fundamental_snapshot_fn = build_fundamental_snapshot_fn(
                self._fundamental_read_facade,
                allow_experimental_data=allow_experimental_data,
            )
        # 分类快照闭包:注入 DataFeed 数据通道,供 sector_id 列(stock_sector_rotation
        # 结构列校验 + 因子中性化 neutralize_by="sector_id")使用。industry 数据未进
        # catalog maturity,无需 allow_experimental_data gate。
        classification_snapshot_fn = None
        if self._classification_read_facade is not None:
            classification_snapshot_fn = build_classification_snapshot_fn(
                self._classification_read_facade,
            )
        snapshot_providers = SnapshotProviders(
            fundamental=fundamental_snapshot_fn,
            classification=classification_snapshot_fn,
        )
        data_feed = ProviderBackedDataFeed(
            self._data_provider,
            tickers=tickers,
            start_date=data_start_date,
            end_date=config.end_date,
            id_map=id_map,
            benchmark_id=resolved_config.benchmark_id,
            snapshot_providers=snapshot_providers,
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
        lineage_recorder: DataLineageRecorder | None = None,
        checkpoint_writer: StrategyRunCheckpointWriterProtocol | None = None,
    ) -> None:
        self._audit_service = audit_service
        self._artifact_service = artifact_service
        self._run_service = run_service
        self._runtime_builder = runtime_builder
        self._backtest_runtime_builder = backtest_runtime_builder
        self._lineage_recorder = lineage_recorder
        self._checkpoint_writer = checkpoint_writer

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
            raise AppBuilderError(msg)
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
        config: BacktestCatalogRequestConfig,
        version: int | None = None,
        options: BacktestServiceOptions | None = None,
        source: str = "tushare",
    ) -> BacktestService:
        """从 published strategy catalog 直接构造 ``BacktestService``。"""
        if self._backtest_runtime_builder is None:
            msg = "BacktestRuntimeBuilder 未配置, 无法从 catalog 构造回测服务"
            raise AppBuilderError(msg)
        resolved_version = version
        if resolved_version is None:
            resolved_version = self._parse_catalog_version(config.strategy_version)
        if resolved_version is None or resolved_version <= 0:
            msg = (
                "Backtest catalog execution requires an exact positive catalog version"
            )
            raise AppBuilderError(msg)
        resolved_options = options or BacktestServiceOptions()
        runtime = self._backtest_runtime_builder.build_published_runtime(
            config=config,
            version=resolved_version,
            source=source,
            fee_model=resolved_options.fee_model,
            slippage_model=resolved_options.slippage_model,
            allow_experimental_data=resolved_options.allow_experimental_data,
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
                checkpoint_writer=self._checkpoint_writer,
                lineage_recorder=self._lineage_recorder,
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
            checkpoint_writer=options.checkpoint_writer or self._checkpoint_writer,
            lineage_recorder=options.lineage_recorder or self._lineage_recorder,
            allow_experimental_data=options.allow_experimental_data,
            restore_runtime_state=options.restore_runtime_state,
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
