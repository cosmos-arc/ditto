"""App 策略服务工厂 — 含 BacktestRuntimeBuilder 与 StrategyServiceFactory."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta

import polars as pl
from ditto_backtest.brokerage import BacktestBrokerage
from ditto_backtest.data_feed import (
    DataFeed,
    FeedInputRequirements,
    ProviderBackedDataFeed,
    SnapshotProviders,
)
from ditto_backtest.participation import daily_participation
from ditto_backtest.result import (
    BacktestAccountStateSnapshot,
    BacktestPendingOrderSnapshot,
    BacktestRuntimeStateSnapshot,
    BacktestSettlementStateSnapshot,
)
from ditto_backtest.simulation import BrokerageModel
from ditto_backtest.simulation.fill import AShareFillModel
from ditto_backtest.simulation.settlement import AShareSettlementModel
from ditto_backtest.simulation.slippage import SlippageModel
from ditto_data.catalog.snapshot_reader import SnapshotReadService
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
from ditto_execution.reality.ordinary_equity import RULES_OBSERVED_AT
from ditto_kernel.identity import InstrumentId
from ditto_kernel.order import OrderSide, OrderType
from ditto_kernel.trading import FeeModel, InstrumentRuleProvider, InstrumentRules
from ditto_portfolio.accounting import Account, CashBook, Position
from ditto_risk.pre_trade import (
    BuyingPowerCheck,
    CompositePreTradeCheck,
    LotSizeCheck,
    NoShortSellCheck,
    PriceValidityCheck,
)
from ditto_strategy.alpha.parameters import EffectiveParameter
from ditto_strategy.alpha.pipeline import StrategyPipeline
from ditto_strategy.alpha.selection_evidence import (
    SelectionEvidenceSink,
)
from ditto_strategy.alpha.specs import StrategySpec
from ditto_strategy.models import (
    ArtifactKind,
    StrategyArtifactRecord,
    StrategySpecRecord,
)
from ditto_strategy.storage.sqlite.services.strategy_artifact_service import (
    StrategyArtifactService,
)
from ditto_strategy.storage.sqlite.services.strategy_run_service import (
    StrategyRunCheckpointWriterProtocol,
)

from ditto_application.builders._resolution import (
    ResolutionResult,
    resolve_benchmark,
    resolve_instrument_display,
)
from ditto_application.builders.frozen_history import FrozenHistoryProvider
from ditto_application.builders.historical_members import (
    freeze_membership_intervals,
    freeze_roster,
)
from ditto_application.builders.ordinary_backtest import (
    build_ordinary_rules,
    ordinary_market_transform,
)
from ditto_application.builders.runtime_builder import (
    PublishedStrategyRuntime,
    StrategyRuntimeBuilder,
)
from ditto_application.catalog_maturity import assert_strategy_runtime_data_allowed
from ditto_application.contracts import REGIME_DEFAULT_LOOKBACK, CostConfig
from ditto_application.exceptions import AppBuilderError, AppError
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
from ditto_application.processes.execution.fee_override import build_slippage_model
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
from ditto_application.processes.experiments._prediction_pipeline import (
    build_frozen_prediction_pipeline,
)
from ditto_application.processes.experiments.baseline_registry import (
    BaselinePlanKind,
    BaselineRegistry,
    default_baseline_registry,
)
from ditto_application.processes.experiments.execution_bundle import (
    BaselineExecutorBinding,
)

__all__ = [
    "BacktestRuntimeBuilder",
    "PublishedBacktestRuntime",
    "StrategyServiceFactory",
    "build_frozen_baseline_pipeline",
    "build_frozen_prediction_pipeline",
]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def build_frozen_baseline_pipeline(
    binding: BaselineExecutorBinding,
    *,
    registry: BaselineRegistry | None = None,
    evidence_sink: SelectionEvidenceSink | None = None,
) -> StrategyPipeline:
    """Build the one registered synthetic baseline without moving lookup."""
    if type(binding) is not BaselineExecutorBinding:
        raise AppBuilderError(
            "frozen baseline execution binding is unsupported or drifted",
            details={
                "code": "REPRODUCIBILITY_FAILED",
                "reason": "baseline_execution_binding_drift",
            },
        )
    resolved_registry = registry or default_baseline_registry()
    if type(resolved_registry) is not BaselineRegistry:
        raise AppBuilderError(
            "frozen baseline execution binding is unsupported or drifted",
            details={
                "code": "REPRODUCIBILITY_FAILED",
                "reason": "baseline_execution_binding_drift",
            },
        )
    matches = tuple(
        descriptor
        for descriptor in resolved_registry.descriptors
        if descriptor.ref.identity == binding.baseline_ref
    )
    descriptor = matches[0] if len(matches) == 1 else None
    if (
        descriptor is None
        or binding.baseline_ref != "stock_universe_equal_weight.v1"
        or binding.kind is not BaselinePlanKind.STOCK_UNIVERSE_EQUAL_WEIGHT
        or binding.implementation_key
        != "research.baseline.stock_universe_equal_weight.v1"
        or binding.executor_contract_version != 1
        or binding.factor_versions != ()
        or resolved_registry.manifest_hash != binding.registry_manifest_hash
        or descriptor.ref.identity != binding.baseline_ref
        or descriptor.kind is not binding.kind
        or descriptor.implementation_key != binding.implementation_key
        or descriptor.executor_contract_version != binding.executor_contract_version
        or descriptor.canonical_hash != binding.descriptor_hash
        or descriptor.requires_exact_strategy
    ):
        raise AppBuilderError(
            "frozen baseline execution binding is unsupported or drifted",
            details={
                "code": "REPRODUCIBILITY_FAILED",
                "reason": "baseline_execution_binding_drift",
            },
        )
    return StrategyPipeline((), evidence_sink=evidence_sink)


def _compute_max_lookback(
    compiled: CompiledExpressions | None,
) -> int:
    """计算因子表达式所需最大 lookback 天数."""
    if compiled is None:
        return REGIME_DEFAULT_LOOKBACK
    return max(
        REGIME_DEFAULT_LOOKBACK,
        max(
            (expr.analysis.lookback for expr in compiled.expressions),
            default=REGIME_DEFAULT_LOOKBACK,
        ),
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
    rule_provider: InstrumentRuleProvider | None = None
    slippage_model: SlippageModel | None = None


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
        historical_reconstruction=config.historical_reconstruction,
        start_date=config.start_date,
        end_date=config.end_date,
        initial_cash=config.initial_cash,
        benchmark_id=benchmark_id,
        parameter_overrides=(),
        candidate_parameters=config.candidate_parameters,
        research_snapshot_id=config.research_snapshot_id,
        research_snapshot_manifest_hash=config.research_snapshot_manifest_hash,
        context_input_refs=config.context_input_refs,
        rebalance_freq=config.rebalance_freq,
        engine_version=config.engine_version,
        random_seed=config.random_seed,
        execution_delay=config.execution_delay,
        knowledge_lag_days=config.knowledge_lag_days,
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


def _validate_resume_pool(
    universe_ids: list[int],
    account: BacktestAccountStateSnapshot | None,
    runtime: BacktestRuntimeStateSnapshot | None,
) -> None:
    """A frozen pool cannot silently discard held, pending or delayed instruments."""
    carried: set[InstrumentId] = (
        {p.instrument_id for p in account.positions if p.quantity} if account else set()
    )
    if runtime is not None:
        carried.update(order.instrument_id for order in runtime.pending_orders)
        carried.update(
            p.instrument_id
            for signal in runtime.delayed_signals
            for p in signal.positions
        )
    missing = carried.difference(universe_ids)
    if missing:
        raise AppBuilderError(
            f"unresolved exit valuation for resumed instruments: {sorted(missing)}"
        )


def _settlement_calendar(
    provider: DataProvider, config: BacktestCatalogRequestConfig
) -> tuple[str, ...]:
    """Require a real next session, including for last-day T+1 purchases."""
    end = (date.fromisoformat(config.end_date) + timedelta(days=31)).isoformat()
    days = tuple(
        sorted(
            str(day)
            for day in provider.get_schedule(config.start_date, end)[
                "trade_date"
            ].to_list()
        )
    )
    if not days or days[-1] <= config.end_date:
        raise AppBuilderError("missing next trading session for T+1 settlement")
    return days


class BacktestRuntimeBuilder:
    """为 published strategy 组装最小可运行回测依赖。"""

    def __init__(
        self,
        *,
        strategy_runtime_builder: StrategyRuntimeBuilder,
        metadata_service: MetadataService,
        data_provider: DataProvider,
        fundamental_read_facade: FundamentalReadFacade | None = None,
        classification_read_facade: ClassificationReadFacade | None = None,
        snapshot_read_service: SnapshotReadService | None = None,
        artifact_service: StrategyArtifactService | None = None,
    ) -> None:
        self._strategy_runtime_builder = strategy_runtime_builder
        self._metadata_service = metadata_service
        self._data_provider = data_provider
        self._fundamental_read_facade = fundamental_read_facade
        self._classification_read_facade = classification_read_facade
        self._snapshot_read_service = snapshot_read_service
        self._artifact_service = artifact_service

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
        """Persist the exact frozen-input preflight even when execution is blocked."""
        historical = None
        evidence: dict[str, object] = {}
        if config.historical_reconstruction:
            if (
                not config.run_id
                or self._artifact_service is None
                or self._snapshot_read_service is None
            ):
                raise AppBuilderError(
                    "historical reconstruction requires durable run/snapshot services"
                )
            if config.resume_from_run_id:
                raise AppBuilderError(
                    "补充历史证据后须创建新运行,不能以新输入续跑旧 checkpoint"
                )
            if (
                self._artifact_service.get_artifact(
                    f"{config.run_id}:historical_inputs"
                )
                is not None
            ):
                raise AppBuilderError(
                    "historical inputs already frozen; "
                    + "create a new run to refresh evidence"
                )
            historical = FrozenHistoryProvider(
                self._snapshot_read_service,
                frozen_at=datetime.now(UTC),
                source=source,
            )
            evidence = {
                "purpose": "historical_reconstruction",
                "input_status": "blocked",
                "frozen_at": historical.frozen_at.isoformat(),
                "start_date": config.start_date,
                "end_date": config.end_date,
                "members": [],
                "sources": historical.sources,
                "historical_availability": "not_certified",
                "limitations": [
                    "近期留存事实按原始业务/公告日期重建;真实入库时间保持不变。",
                    "按冻结成员区间和上市日期逐日参与;未认证本地历史持有、原始版本完整性或严格快照重放。",
                    "规则、公司行动和历史身份缺证仍阻止执行;补证后创建新运行。",
                ],
            }
        try:
            runtime = self._build_published_runtime(
                config=config,
                version=version,
                source=source,
                fee_model=fee_model,
                slippage_model=slippage_model,
                allow_experimental_data=allow_experimental_data,
                historical_provider=historical,
            )
            evidence["input_status"] = "ready"
            return runtime
        except (AppError, ValueError, OSError) as exc:
            evidence["reason"] = str(exc)
            raise
        finally:
            if historical is not None and self._artifact_service is not None:
                evidence["members"] = list(historical.members)
                evidence["instrument_ids"] = list(historical.instrument_ids)
                evidence["membership_intervals"] = historical.membership_intervals
                evidence["roster"] = historical.roster
                evidence["participation"] = historical.participation
                self._artifact_service.save_artifact(
                    StrategyArtifactRecord(
                        artifact_id=f"{config.run_id}:historical_inputs",
                        strategy_id=config.strategy_id,
                        run_id=config.run_id,
                        artifact_type=ArtifactKind.HISTORICAL_INPUTS,
                        file_path="",
                        metadata=evidence,
                        created_at=historical.frozen_at.isoformat(),
                    )
                )

    def _build_published_runtime(
        self,
        *,
        config: BacktestCatalogRequestConfig,
        version: int | None = None,
        source: str = "tushare",
        fee_model: FeeModel | None = None,
        slippage_model: SlippageModel | None = None,
        allow_experimental_data: bool = False,
        historical_provider: FrozenHistoryProvider | None = None,
    ) -> PublishedBacktestRuntime:
        """从 published strategy catalog 构造回测运行时。"""
        if config.research_snapshot_id is not None:
            raise AppBuilderError(
                "ordinary catalog rules cannot certify a strict research snapshot"
            )
        runtime = self._strategy_runtime_builder.build_published_runtime(
            config.strategy_id,
            version,
            candidate_parameters=config.candidate_parameters,
        )
        assert_strategy_runtime_data_allowed(
            runtime.spec,
            allow_experimental_data=allow_experimental_data,
            context="catalog-backed backtest",
        )
        resolved_fee_model = fee_model or AShareFeeModel()
        resolved_slippage = slippage_model or build_slippage_model(
            CostConfig(
                slippage_bps=runtime.spec.execution.cost_model.slippage_bps,
                impact_model=runtime.spec.execution.cost_model.impact_model,
            )
        )
        account_state = _load_account_state(config)
        settlement_state = _load_settlement_state(config)
        runtime_state = _load_runtime_state(config)
        # 解析 universe → tickers + id_map + display_map
        universe_ids = self._resolve_historical_members(
            config, runtime.spec.universe, historical_provider, source
        )
        _validate_resume_pool(universe_ids, account_state, runtime_state)
        resolution = resolve_instrument_display(
            universe_ids,
            self._metadata_service,
            source=source,
            as_of=config.start_date,
        )
        if historical_provider is not None:
            identities = {
                int(str(row["instrument_id"])): row
                for row in historical_provider.roster
            }
            resolution = ResolutionResult(
                tickers=tuple(str(row["source_ticker"]) for row in identities.values()),
                id_map={
                    str(row["source_ticker"]): InstrumentId(iid)
                    for iid, row in identities.items()
                },
                display_map={
                    InstrumentId(iid): f"{row['ticker']}.{row['exchange']}"
                    for iid, row in identities.items()
                },
            )
            historical_provider.members = tuple(resolution.tickers)
        display_map = resolution.display_map
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

        pool = self._metadata_service.universe.get_universe_detail(
            runtime.spec.universe
        )
        if isinstance(pool, dict):
            pool_description = str(pool.get("description") or "")
            pool_description += (
                f" 普通规则核对时间 {RULES_OBSERVED_AT};仅覆盖已核实名单,"
                "未认证历史可得性。股票退出或无报价停牌拒绝估值;"
                "ETF 状态以实际正成交量核验,缺报价/零成交量拒绝。"
                "最低佣金 5 元为保守研究假设;不模拟分红、拆并份或退市清算。"
            )
            resolved_config = replace(
                resolved_config,
                sample_pool={
                    **{
                        key: pool.get(key)
                        for key in ("universe_id", "name", "source_ref")
                    },
                    "description": pool_description,
                },
            )
        benchmark_ticker = None
        if benchmark_id is not None:
            benchmark_resolution = resolve_instrument_display(
                [int(benchmark_id)],
                self._metadata_service,
                source=source,
                as_of=config.start_date,
            )
            benchmark_ticker = benchmark_resolution.tickers[0]

        data_feed, provider, rule_provider = self._build_data_feed(
            config=config,
            runtime=runtime,
            resolution=resolution,
            benchmark_id=benchmark_id,
            benchmark_ticker=benchmark_ticker,
            historical_provider=historical_provider,
            allow_experimental_data=allow_experimental_data,
        )
        settlement_days = _settlement_calendar(provider, config)

        def rules_getter(iid: InstrumentId, trade_date: str) -> InstrumentRules:
            rules = rule_provider.get_rules(trade_date, [iid])
            if iid not in rules:
                raise AppBuilderError(f"missing asset rule: {iid} {trade_date}")
            return rules[iid]

        brokerage = BacktestBrokerage(
            account=_build_account(
                initial_cash=config.initial_cash, account_state=account_state
            ),
            order_book=_build_order_book(runtime_state),
            model=BrokerageModel(
                fill_model=_build_fill_model(config),
                fee_model=resolved_fee_model,
                slippage_model=resolved_slippage,
                settlement_model=AShareSettlementModel(
                    trading_calendar=tuple(settlement_days)
                ),
            ),
            rules_getter=rules_getter,
        )
        if settlement_state is not None:
            brokerage.restore_settlement_state(settlement_state)
        return PublishedBacktestRuntime(
            record=runtime.record,
            spec=runtime.spec,
            pipeline=runtime.pipeline,
            planner=SimpleExecutionPlanner(
                default_order_type=runtime.spec.execution.default_order_type
            ),
            brokerage=brokerage,
            pre_trade_check=CompositePreTradeCheck(
                checks=(
                    NoShortSellCheck(),
                    PriceValidityCheck(),
                    LotSizeCheck(),
                    BuyingPowerCheck(),
                ),
            ),
            data_feed=data_feed,
            display_map=display_map,
            fee_model=resolved_fee_model,
            config=resolved_config,
            compiled_expressions=runtime.compiled_expressions,
            rule_provider=rule_provider,
            slippage_model=resolved_slippage,
        )

    def _resolve_historical_members(
        self,
        config: BacktestCatalogRequestConfig,
        universe: str,
        historical_provider: FrozenHistoryProvider | None,
        source: str,
    ) -> list[int]:
        """Freeze interval/identity facts before downstream input checks can fail."""
        if historical_provider is not None:
            previous = (
                self._artifact_service.get_artifact(
                    f"{config.parent_run_id}:historical_inputs"
                )
                if config.parent_run_id and self._artifact_service is not None
                else None
            )
            historical_provider.membership_intervals = freeze_membership_intervals(
                self._metadata_service,
                universe,
                start=config.start_date,
                end=config.end_date,
                original=previous.metadata if previous is not None else None,
            )
            universe_ids = sorted(
                {
                    int(str(row["instrument_id"]))
                    for row in historical_provider.membership_intervals
                }
            )
            historical_provider.instrument_ids = tuple(universe_ids)
            historical_provider.roster.extend(
                freeze_roster(
                    self._metadata_service,
                    historical_provider.membership_intervals,
                    start=config.start_date,
                    source=source,
                    original=previous.metadata if previous is not None else None,
                )
            )
        else:
            universe_ids = self._metadata_service.get_universe(
                universe, asof=config.start_date
            )
            if not universe_ids:
                raise AppBuilderError(
                    f"universe for {config.strategy_id} 在 {config.start_date} "
                    + "解析到 0 成员; 检查成员 PIT 区间"
                )
        return universe_ids

    def _build_data_feed(
        self,
        *,
        config: BacktestCatalogRequestConfig,
        runtime: PublishedStrategyRuntime,
        resolution: ResolutionResult,
        benchmark_id: InstrumentId | None,
        benchmark_ticker: str | None,
        historical_provider: FrozenHistoryProvider | None,
        allow_experimental_data: bool,
    ) -> tuple[ProviderBackedDataFeed, DataProvider, InstrumentRuleProvider]:
        """Assemble verified price channels and preflight their consumers."""
        # 计算数据加载起点:考虑因子表达式 lookback + Regime 默认 lookback
        max_lookback = _compute_max_lookback(runtime.compiled_expressions)
        data_start_date = _shift_back_calendar_days(config.start_date, max_lookback * 2)

        provider: DataProvider = historical_provider or self._data_provider
        if historical_provider is not None:
            data_start_date = historical_provider.prepare_calendar(
                start=config.start_date,
                end=(
                    date.fromisoformat(config.end_date) + timedelta(days=31)
                ).isoformat(),
                warmup=max_lookback,
                lag=config.knowledge_lag_days,
            )
            historical_provider.freeze(
                ticker_ids=resolution.id_map,
                asset_class=runtime.spec.asset_class,
                start=data_start_date,
                end=config.end_date,
                benchmark={benchmark_ticker: InstrumentId(int(benchmark_id))}
                if benchmark_ticker is not None and benchmark_id is not None
                else None,
                calendar_end=(
                    date.fromisoformat(config.end_date) + timedelta(days=31)
                ).isoformat(),
                include_fundamentals=runtime.spec.asset_class == "stock",
            )
        participation = None
        if historical_provider is not None:
            participation = daily_participation(
                historical_provider.roster,
                provider.get_schedule(data_start_date, config.end_date)[
                    "trade_date"
                ].to_list(),
                warmup_days=max_lookback,
                knowledge_lag_days=config.knowledge_lag_days,
            ).with_columns(
                pl.col("instrument_id")
                .replace_strict(
                    {int(iid): ticker for ticker, iid in resolution.id_map.items()},
                    return_dtype=pl.String,
                )
                .alias("symbol")
            )
            historical_provider.participation = (
                participation.filter(pl.col("trade_date") >= config.start_date)
                .select(
                    "instrument_id",
                    "symbol",
                    "trade_date",
                    "status",
                    "warmup_available",
                    "warmup_required",
                )
                .to_dicts()
            )
        rule_provider = build_ordinary_rules(
            self._metadata_service,
            [int(iid) for iid in resolution.id_map.values()],
            asset_class=runtime.spec.asset_class,
            commission_rate=runtime.spec.execution.cost_model.commission_rate,
            start=config.start_date,
            end=config.end_date,
            historical_roster=historical_provider.roster
            if historical_provider is not None
            else None,
        )

        # 基本面快照闭包:注入 DataFeed 数据通道,供 quality_roe / value_pe 等因子引用。
        # maturity gate 经 facade 的 allow_experimental_data 生效。
        fundamental_snapshot_fn = None
        fundamental_facade = historical_provider or self._fundamental_read_facade
        if fundamental_facade is not None:
            fundamental_snapshot_fn = build_fundamental_snapshot_fn(
                fundamental_facade,
                allow_experimental_data=allow_experimental_data,
            )
        # 分类快照闭包:注入 DataFeed 数据通道,供 sector_id 列(stock_sector_rotation
        # 结构列校验 + 因子中性化 neutralize_by="sector_id")使用。industry 数据未进
        # catalog maturity,无需 allow_experimental_data gate。
        classification_snapshot_fn = None
        if historical_provider is None and self._classification_read_facade is not None:
            classification_snapshot_fn = build_classification_snapshot_fn(
                self._classification_read_facade,
            )
        snapshot_providers = SnapshotProviders(
            fundamental=fundamental_snapshot_fn,
            classification=classification_snapshot_fn,
            require_source_snapshot_lineage=True,
            market=ordinary_market_transform(
                rule_provider, start_date=config.start_date, participation=participation
            ),
            participation=participation,
            requirements=FeedInputRequirements(
                start_date=config.start_date,
                warmup_days=max_lookback,
                knowledge_lag_days=config.knowledge_lag_days,
                benchmark_ticker=benchmark_ticker,
            ),
        )
        data_feed = ProviderBackedDataFeed(
            provider,
            tickers=resolution.tickers,
            start_date=data_start_date,
            end_date=config.end_date,
            id_map=resolution.id_map,
            benchmark_id=benchmark_id,
            snapshot_providers=snapshot_providers,
        )
        data_feed.validate_inputs()
        return data_feed, provider, rule_provider


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
        resolved_options = replace(
            resolved_options,
            rule_provider=runtime.rule_provider,
            slippage_model=runtime.slippage_model or resolved_options.slippage_model,
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
            external_should_stop=options.external_should_stop,
            checkpoint_writer=options.checkpoint_writer or self._checkpoint_writer,
            checkpoint_interval_days=options.checkpoint_interval_days,
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
