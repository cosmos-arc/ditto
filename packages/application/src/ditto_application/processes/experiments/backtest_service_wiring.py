"""Fail-closed verification of the concrete research backtest service graph."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, fields
from datetime import date, timedelta
from typing import cast

from ditto_backtest.brokerage import BacktestBrokerage
from ditto_backtest.simulation import (
    AShareFillModel,
    AShareSettlementModel,
    BrokerageModel,
    ClosingAuctionFillModel,
    FixedBpsSlippage,
)
from ditto_execution.orders.book import OrderBook
from ditto_execution.orders.journal import InMemoryOrderEventJournal
from ditto_execution.planner import SimpleExecutionPlanner
from ditto_execution.reality import AShareFeeModel
from ditto_execution.rules import InMemoryRuleProvider
from ditto_kernel.identity import InstrumentId
from ditto_kernel.order import OrderType
from ditto_kernel.trading import (
    DEFAULT_LOT_SIZE,
    FeeSchedule,
    InstrumentDefinition,
    InstrumentRules,
    TradingRuleSet,
)
from ditto_portfolio.accounting import Account, CashBook
from ditto_risk.pre_trade import (
    BuyingPowerCheck,
    CompositePreTradeCheck,
    LotSizeCheck,
)
from ditto_strategy.alpha.parameters import canonical_parameter_hash
from ditto_strategy.alpha.pipeline import StrategyPipeline
from ditto_strategy.alpha.selection_evidence import SelectionEvidenceCollector

from ditto_application.exceptions import AppBuilderError, AppProcessError
from ditto_application.processes.execution.backtest_process import (
    BacktestService,
    BacktestServiceConfig,
    BacktestServiceOptions,
)
from ditto_application.processes.execution.factor_bridge import (
    CompiledExpressions,
    compiled_expressions_execution_hash,
)
from ditto_application.processes.experiments import _selection_evidence_graph
from ditto_application.processes.experiments._backtest_exact_state import (
    all_references_identical,
    has_exact_runtime_value,
    pristine_order_state_drift_reason,
)
from ditto_application.processes.experiments.execution_bundle import (
    BaselineExecutorBinding,
    ExactBenchmarkBinding,
    ResearchExecutionAudit,
    ResearchFillMode,
    StrategyExecutionBinding,
)
from ditto_application.processes.experiments.execution_contracts import (
    ResearchAssetLane,
)
from ditto_application.processes.experiments.research_backtest_checkpoint import (
    RESEARCH_CHECKPOINT_INTERVAL_DAYS,
    ResearchBacktestCheckpointControl,
    ResearchBacktestResumeState,
    build_research_backtest_config,
    build_research_backtest_strategy_config,
    require_research_resume_runtime_state,
)
from ditto_application.processes.experiments.research_data_feed import ResearchDataFeed
from ditto_application.processes.experiments.research_policy_artifact import (
    VerifiedInstrumentRulesArtifact,
)

__all__ = [
    "ClosedBacktestServiceGraph",
    "ConstructedBacktestComponents",
    "KnowledgeLagRuleProvider",
    "KnowledgeLagRulesGetter",
    "require_actual_component_state",
    "require_closed_backtest_service",
]

_PRE_TRADE_CHECK_TYPES = (LotSizeCheck, BuyingPowerCheck)
_CLOSING_AUCTION_PARTICIPATION_RATE = 0.05


def _error(reason: str, **details: object) -> AppProcessError:
    return AppProcessError(
        "frozen research backtest construction failed",
        details={
            "code": "REPRODUCIBILITY_FAILED",
            "reason": reason,
            **details,
        },
    )


@dataclass(frozen=True, slots=True)
class KnowledgeLagRuleProvider:
    """Apply the audit's calendar-day knowledge fence to verified PIT rules."""

    inner: InMemoryRuleProvider
    knowledge_lag_days: int

    def _as_of(self, value: str) -> str:
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            raise _error("invalid_rule_query_date", as_of_date=value) from None
        return (parsed - timedelta(days=self.knowledge_lag_days)).isoformat()

    def get_definition(
        self, instrument_id: InstrumentId
    ) -> InstrumentDefinition | None:
        """Return the static definition bound to the verified artifact."""
        return self.inner.get_definition(instrument_id)

    def get_trading_rule(
        self,
        instrument_id: InstrumentId,
        as_of_date: str,
    ) -> TradingRuleSet | None:
        """Resolve only rules known by the lagged decision cutoff."""
        return self.inner.get_trading_rule(instrument_id, self._as_of(as_of_date))

    def get_fee_schedule(
        self,
        instrument_id: InstrumentId,
        as_of_date: str,
    ) -> FeeSchedule | None:
        """Resolve only fees known by the lagged decision cutoff."""
        return self.inner.get_fee_schedule(instrument_id, self._as_of(as_of_date))

    def get_rules(
        self,
        as_of_date: str,
        instrument_ids: list[InstrumentId],
    ) -> dict[InstrumentId, InstrumentRules]:
        """Resolve an exact rule batch at the lagged decision cutoff."""
        return self.inner.get_rules(self._as_of(as_of_date), instrument_ids)


@dataclass(frozen=True, slots=True)
class KnowledgeLagRulesGetter:
    """Exact callable binding brokerage lookups to one lag-aware provider."""

    provider: KnowledgeLagRuleProvider

    def __call__(self, instrument_id: InstrumentId, trade_date: str) -> InstrumentRules:
        """Return complete rules or fail closed without a fallback provider."""
        resolved = self.provider.get_rules(trade_date, [instrument_id])
        rules = resolved.get(instrument_id)
        if rules is None:
            raise _error(
                "frozen_instrument_rules_missing",
                instrument_id=int(instrument_id),
                trade_date=trade_date,
            )
        return rules


@dataclass(frozen=True, slots=True)
class ConstructedBacktestComponents:
    """Concrete local object graph used by one research service."""

    feed: ResearchDataFeed
    rules: VerifiedInstrumentRulesArtifact
    auction_model: ClosingAuctionFillModel
    fill_model: AShareFillModel
    brokerage_model: BrokerageModel
    cash: CashBook
    account: Account
    order_journal: InMemoryOrderEventJournal
    order_book: OrderBook
    rules_getter: KnowledgeLagRulesGetter
    rule_provider: KnowledgeLagRuleProvider
    brokerage: BacktestBrokerage
    planner: SimpleExecutionPlanner
    fee_model: AShareFeeModel
    slippage_model: FixedBpsSlippage
    settlement_model: AShareSettlementModel
    pre_trade: CompositePreTradeCheck
    options: BacktestServiceOptions
    benchmark: ExactBenchmarkBinding | None


@dataclass(frozen=True, slots=True)
class ClosedBacktestServiceGraph:
    """Exact local objects that the returned service is allowed to retain."""

    service: BacktestService
    audit: ResearchExecutionAudit
    config: BacktestServiceConfig
    pipeline: StrategyPipeline
    selection_evidence_collector: SelectionEvidenceCollector
    planner: SimpleExecutionPlanner
    brokerage: BacktestBrokerage
    pre_trade: CompositePreTradeCheck
    feed: ResearchDataFeed
    options: BacktestServiceOptions
    fee_model: AShareFeeModel
    slippage_model: FixedBpsSlippage
    rule_provider: KnowledgeLagRuleProvider
    compiled_expressions: CompiledExpressions | None
    pipeline_attestation: object | None
    external_should_stop: Callable[[], bool]
    components: ConstructedBacktestComponents
    checkpoint_control: ResearchBacktestCheckpointControl | None = None


def require_closed_backtest_service(
    graph: ClosedBacktestServiceGraph,
    *,
    expected_audit: ResearchExecutionAudit,
    expected_should_stop: Callable[[], bool],
) -> None:
    """Prove the returned service retained only the closed local graph."""
    if type(graph) is not ClosedBacktestServiceGraph:
        raise _error("invalid_closed_backtest_service_graph")
    service = graph.service
    if type(service) is not BacktestService:
        raise _error("constructed_backtest_service_type_drift")
    service_state = vars(service)
    expected_references: dict[str, object] = {
        "_config": graph.config,
        "_pipeline": graph.pipeline,
        "_planner": graph.planner,
        "_brokerage": graph.brokerage,
        "_pre_trade_check": graph.pre_trade,
        "_data_feed": graph.feed,
        "_options": graph.options,
    }
    expected_state_keys = {*expected_references, "_last_run_cancelled"}
    if (
        set(service_state) != expected_state_keys
        or any(
            service_state.get(name) is not value
            for name, value in expected_references.items()
        )
        or service_state.get("_last_run_cancelled") is not None
    ):
        raise _error("constructed_backtest_service_wiring_drift")
    if (
        type(expected_audit) is not ResearchExecutionAudit
        or graph.audit is not expected_audit
    ):
        raise _error("research_backtest_audit_drift")
    if graph.external_should_stop is not expected_should_stop or not callable(
        expected_should_stop
    ):
        raise _error("external_stop_callback_drift")

    options = graph.options
    checkpoint_control = graph.checkpoint_control
    if (
        type(options) is not BacktestServiceOptions
        or type(checkpoint_control) is not ResearchBacktestCheckpointControl
    ):
        raise _error("constructed_backtest_service_options_drift")
    _require_exact_state_keys(
        options,
        {item.name for item in fields(BacktestServiceOptions)},
        "constructed_backtest_service_options_drift",
    )
    expected_options: dict[str, object] = {
        "fee_model": graph.fee_model,
        "slippage_model": graph.slippage_model,
        "rule_provider": graph.rule_provider,
        "compiled_expressions": graph.compiled_expressions,
        "external_should_stop": expected_should_stop,
        "checkpoint_writer": checkpoint_control.writer,
        "restore_runtime_state": (
            None
            if checkpoint_control.resume is None
            else checkpoint_control.resume.runtime
        ),
    }
    if any(
        getattr(options, name) is not value for name, value in expected_options.items()
    ):
        raise _error("constructed_backtest_service_options_drift")
    none_only = (
        options.post_trade_guard,
        options.audit_service,
        options.artifact_service,
        options.artifact_dir,
        options.display_map,
        options.run_service,
        options.lineage_recorder,
    )
    if (
        any(value is not None for value in none_only)
        or (options.allow_experimental_data is not False)
        or (
            type(options.checkpoint_interval_days) is not int
            or options.checkpoint_interval_days != RESEARCH_CHECKPOINT_INTERVAL_DAYS
        )
    ):
        raise _error("unauthorized_backtest_service_option")

    components = graph.components
    if (
        type(components) is not ConstructedBacktestComponents
        or type(graph.config) is not BacktestServiceConfig
        or type(graph.pipeline) is not StrategyPipeline
        or graph.feed is not components.feed
        or graph.planner is not components.planner
        or graph.brokerage is not components.brokerage
        or graph.pre_trade is not components.pre_trade
        or graph.options is not components.options
        or graph.fee_model is not components.fee_model
        or graph.slippage_model is not components.slippage_model
        or graph.rule_provider is not components.rule_provider
        or graph.compiled_expressions is not options.compiled_expressions
        or options.checkpoint_writer is not checkpoint_control.writer
    ):
        raise _error("constructed_backtest_service_graph_drift")
    _require_audit_bound_config(graph, checkpoint_control)
    _require_pipeline_state(graph)
    ResearchDataFeed.require_verified_state(
        graph.feed,
        expected_snapshot=expected_audit.semantics.snapshot,
        expected_start_date=expected_audit.semantics.test_start.isoformat(),
        expected_end_date=expected_audit.semantics.test_end.isoformat(),
        expected_knowledge_lag_days=expected_audit.semantics.knowledge_lag_days,
        expected_benchmark=expected_audit.semantics.backtest.benchmark,
        expected_manifest_hash=(
            expected_audit.semantics.backtest.data_feed_manifest_hash
        ),
    )
    require_actual_component_state(
        config=graph.config,
        expected_order_type=_audit_order_type(expected_audit),
        expected_slippage_basis_points=(
            expected_audit.semantics.backtest.slippage_basis_points
        ),
        components=components,
        resume_state=checkpoint_control.resume,
    )
    _require_rules_state(graph)


def _require_exact_state_keys(
    value: object,
    expected: set[str],
    reason: str,
) -> None:
    try:
        actual = set(vars(value))
    except TypeError:
        raise _error(reason) from None
    if actual != expected:
        raise _error(
            reason,
            expected_state_keys=tuple(sorted(expected)),
            actual_state_keys=tuple(sorted(actual)),
        )


def _expected_service_config(
    graph: ClosedBacktestServiceGraph,
    checkpoint_control: ResearchBacktestCheckpointControl,
) -> BacktestServiceConfig:
    audit = graph.audit
    semantics = audit.semantics
    strategy = semantics.strategy
    config = graph.config
    if type(strategy) is StrategyExecutionBinding:
        if (
            canonical_parameter_hash(config.effective_parameters)
            != strategy.parameter_hash
        ):
            raise _error("constructed_strategy_parameter_state_drift")
        if (
            compiled_expressions_execution_hash(graph.compiled_expressions)
            != strategy.compiled_factor_set_hash
        ):
            raise _error("compiled_factor_set_execution_drift")
        resolved = build_research_backtest_strategy_config(
            strategy,
            effective_parameters=config.effective_parameters,
            rebalance_frequency=semantics.backtest.rebalance_frequency,
        )
    elif type(strategy) is BaselineExecutorBinding:
        if graph.compiled_expressions is not None or config.effective_parameters:
            raise _error("synthetic_baseline_execution_drift")
        resolved = build_research_backtest_strategy_config(
            strategy,
            effective_parameters=(),
            rebalance_frequency=semantics.backtest.rebalance_frequency,
        )
    else:
        raise _error("invalid_strategy_execution_binding")
    return build_research_backtest_config(
        audit=audit,
        strategy=resolved,
        initial_cash=semantics.backtest.initial_cash_minor_units / 100,
        benchmark=semantics.backtest.benchmark,
        resume=checkpoint_control.resume,
    )


def _require_audit_bound_config(
    graph: ClosedBacktestServiceGraph,
    checkpoint_control: ResearchBacktestCheckpointControl,
) -> None:
    config = graph.config
    if type(config) is not BacktestServiceConfig:
        raise _error("constructed_backtest_service_config_drift")
    _require_exact_state_keys(
        config,
        {item.name for item in fields(BacktestServiceConfig)},
        "constructed_backtest_service_config_drift",
    )
    if not has_exact_runtime_value(
        config,
        _expected_service_config(graph, checkpoint_control),
    ):
        raise _error("constructed_backtest_service_config_drift")


def _require_pipeline_state(graph: ClosedBacktestServiceGraph) -> None:
    pipeline = graph.pipeline
    stages = pipeline.stages
    collector = graph.selection_evidence_collector
    strategy = graph.audit.semantics.strategy
    _selection_evidence_graph.require_pristine_selection_evidence_graph(
        pipeline=pipeline,
        collector=collector,
        stages=stages,
        is_baseline=type(strategy) is BaselineExecutorBinding,
        is_stock_lane=graph.audit.semantics.policy.lane is ResearchAssetLane.STOCK,
    )
    if type(strategy) is BaselineExecutorBinding:
        if graph.pipeline_attestation is not None or stages != ():
            raise _error("synthetic_baseline_execution_drift")
        return
    if type(strategy) is not StrategyExecutionBinding:
        raise _error("invalid_strategy_execution_binding")
    attestation = graph.pipeline_attestation
    attestation_type = type(attestation)
    if (
        attestation is None
        or attestation_type.__module__
        != "ditto_application.builders.node_pipeline_builder"
        or attestation_type.__qualname__ != "AttestedNodePipeline"
    ):
        raise _error("invalid_research_pipeline_attestation")
    if getattr(attestation, "evidence_sink", object()) is not collector:
        raise _error("research_pipeline_evidence_sink_drift")
    verifier = getattr(attestation_type, "require_verified_pipeline", None)
    if not callable(verifier):
        raise _error("invalid_research_pipeline_attestation")
    try:
        verified = verifier(
            attestation,
            expected_execution_hash=strategy.pipeline_execution_hash,
        )
    except AppBuilderError as error:
        raise _error(
            "research_pipeline_execution_drift",
            builder_reason=error.details.get("reason"),
        ) from error
    if verified is not pipeline:
        raise _error("research_pipeline_execution_drift")


def _require_rules_state(graph: ClosedBacktestServiceGraph) -> None:
    components = graph.components
    rules = components.rules
    if type(rules) is not VerifiedInstrumentRulesArtifact:
        raise _error("constructed_instrument_rules_artifact_drift")
    if rules.input_evidence not in graph.audit.semantics.snapshot.inputs:
        raise _error("constructed_instrument_rules_artifact_drift")
    frozen_roles = {
        item.role: item.inputs
        for item in graph.audit.semantics.backtest.policy_model_evidence
        if item.role in {"fees", "rules", "settlement"}
    }
    if frozen_roles != {
        "fees": (rules.input_evidence,),
        "rules": (rules.input_evidence,),
        "settlement": (rules.input_evidence,),
    }:
        raise _error("constructed_instrument_rules_artifact_drift")
    rebuilt = VerifiedInstrumentRulesArtifact(
        input_evidence=rules.input_evidence,
        artifact_bytes=rules.artifact_bytes,
    )
    if rebuilt.evidence != rules.evidence:
        raise _error("constructed_instrument_rules_artifact_drift")
    inner = components.rule_provider.inner
    rebuilt_inner = VerifiedInstrumentRulesArtifact.build_rule_provider(rebuilt)
    expected_keys = {"_definitions", "_trading_rules", "_fee_schedules"}
    _require_exact_state_keys(
        inner,
        expected_keys,
        "constructed_rule_provider_state_drift",
    )
    if not has_exact_runtime_value(vars(inner), vars(rebuilt_inner)):
        raise _error("constructed_rule_provider_state_drift")
    if (
        type(components.rules_getter) is not KnowledgeLagRulesGetter
        or components.rules_getter.provider is not components.rule_provider
    ):
        raise _error("constructed_rule_getter_drift")


def _require_component_types(components: ConstructedBacktestComponents) -> None:
    expected_types: tuple[tuple[str, type[object]], ...] = (
        ("auction_model", ClosingAuctionFillModel),
        ("fill_model", AShareFillModel),
        ("brokerage_model", BrokerageModel),
        ("cash", CashBook),
        ("account", Account),
        ("order_journal", InMemoryOrderEventJournal),
        ("order_book", OrderBook),
        ("rule_provider", KnowledgeLagRuleProvider),
        ("brokerage", BacktestBrokerage),
        ("planner", SimpleExecutionPlanner),
        ("pre_trade", CompositePreTradeCheck),
        ("fee_model", AShareFeeModel),
        ("slippage_model", FixedBpsSlippage),
        ("settlement_model", AShareSettlementModel),
    )
    if any(
        type(getattr(components, name)) is not expected
        for name, expected in expected_types
    ):
        raise _error("constructed_backtest_component_type_drift")


def _require_component_state_shapes(
    components: ConstructedBacktestComponents,
) -> None:
    expected: tuple[tuple[object, set[str], str], ...] = (
        (
            components.auction_model,
            {"participation_rate_threshold"},
            "constructed_auction_model_state_drift",
        ),
        (
            components.fill_model,
            {"_auction", "_participation_rate"},
            "constructed_fill_model_state_drift",
        ),
        (
            components.brokerage_model,
            {"fill_model", "slippage_model", "fee_model", "settlement_model"},
            "constructed_brokerage_model_state_drift",
        ),
        (
            components.cash,
            {"available", "settled", "frozen"},
            "constructed_cash_state_drift",
        ),
        (
            components.account,
            {"_positions", "_cash", "_event_bus"},
            "constructed_brokerage_account_drift",
        ),
        (
            components.order_journal,
            {"_events"},
            "constructed_order_journal_state_drift",
        ),
        (
            components.order_book,
            {"_tickets", "_journal"},
            "constructed_order_book_state_drift",
        ),
        (
            components.brokerage,
            {
                "_account",
                "_order_book",
                "_model",
                "_rules_getter",
                "_fill_counter",
                "_frozen_quantities",
                "_current_trade_date",
            },
            "constructed_brokerage_state_drift",
        ),
        (
            components.planner,
            {"_counter", "_default_lot_size", "_default_order_type"},
            "constructed_execution_planner_state_drift",
        ),
        (
            components.pre_trade,
            {"_checks"},
            "constructed_pre_trade_check_state_drift",
        ),
        (components.fee_model, set(), "constructed_fee_model_state_drift"),
        (
            components.slippage_model,
            {"bps"},
            "constructed_slippage_model_state_drift",
        ),
        (
            components.settlement_model,
            {"trading_calendar"},
            "constructed_settlement_model_state_drift",
        ),
    )
    for value, keys, reason in expected:
        _require_exact_state_keys(value, keys, reason)


def _require_fill_state(
    config: BacktestServiceConfig,
    components: ConstructedBacktestComponents,
) -> None:
    expected_fill_rate = (
        0.0
        if ResearchFillMode(config.fill_mode) is ResearchFillMode.ALL_OR_NOTHING
        else config.participation_rate
    )
    fill_state = vars(components.fill_model)
    if (
        not has_exact_runtime_value(
            components.fill_model.participation_rate,
            expected_fill_rate,
        )
        or fill_state.get("_auction") is not components.auction_model
        or not has_exact_runtime_value(
            components.auction_model.participation_rate_threshold,
            _CLOSING_AUCTION_PARTICIPATION_RATE,
        )
    ):
        raise _error("constructed_fill_model_parameter_drift")


def _audit_order_type(audit: ResearchExecutionAudit) -> OrderType:
    planner = audit.semantics.backtest.execution_planner
    if planner.contract_version != 1:
        raise _error("constructed_execution_planner_parameter_drift")
    order_type = {
        "ditto_execution.simple_execution_planner.market": OrderType.MARKET,
        "ditto_execution.simple_execution_planner.limit": OrderType.LIMIT,
    }.get(planner.implementation_key)
    if order_type is None:
        raise _error("constructed_execution_planner_parameter_drift")
    return order_type


def _require_planner_state(
    expected_order_type: OrderType,
    components: ConstructedBacktestComponents,
) -> tuple[OrderType, tuple[LotSizeCheck, BuyingPowerCheck]]:
    planner_state = vars(components.planner)
    planner_order_type: object = planner_state.get("_default_order_type")
    if (
        type(planner_order_type) is not OrderType
        or planner_order_type is not expected_order_type
        or not has_exact_runtime_value(
            planner_state.get("_default_lot_size"),
            DEFAULT_LOT_SIZE,
        )
        or not has_exact_runtime_value(components.planner.snapshot_id_counter(), 0)
    ):
        raise _error("constructed_execution_planner_parameter_drift")
    raw_checks: object = vars(components.pre_trade).get("_checks")
    if type(raw_checks) is not tuple:
        raise _error("constructed_pre_trade_check_order_drift")
    check_objects = cast("tuple[object, ...]", raw_checks)
    if tuple(type(item) for item in check_objects) != _PRE_TRADE_CHECK_TYPES:
        raise _error("constructed_pre_trade_check_order_drift")
    for check in check_objects:
        _require_exact_state_keys(
            check,
            set(),
            "constructed_pre_trade_check_state_drift",
        )
    return planner_order_type, cast(
        "tuple[LotSizeCheck, BuyingPowerCheck]",
        check_objects,
    )


def _require_brokerage_state(
    config: BacktestServiceConfig,
    components: ConstructedBacktestComponents,
    resume_state: ResearchBacktestResumeState | None,
) -> None:
    model = components.brokerage_model
    if not all_references_identical(
        (
            (model.fill_model, components.fill_model),
            (model.slippage_model, components.slippage_model),
            (model.fee_model, components.fee_model),
            (model.settlement_model, components.settlement_model),
        )
    ):
        raise _error("constructed_brokerage_model_drift")
    brokerage_state = vars(components.brokerage)
    if (
        not all_references_identical(
            (
                (brokerage_state.get("_account"), components.account),
                (brokerage_state.get("_order_book"), components.order_book),
                (brokerage_state.get("_model"), model),
                (brokerage_state.get("_rules_getter"), components.rules_getter),
            )
        )
        or not has_exact_runtime_value(
            components.brokerage.snapshot_fill_counter(),
            0,
        )
        or not has_exact_runtime_value(
            brokerage_state.get("_current_trade_date"),
            "",
        )
    ):
        raise _error("constructed_brokerage_state_drift")
    if resume_state is None:
        _require_pristine_account_and_orders(config, components)
    else:
        require_research_resume_runtime_state(
            resume_state,
            account=components.account,
            cash=components.cash,
            brokerage=components.brokerage,
            order_book=components.order_book,
            order_journal=components.order_journal,
        )

    if type(
        components.rule_provider.inner
    ) is not InMemoryRuleProvider or not has_exact_runtime_value(
        components.rule_provider.knowledge_lag_days,
        config.knowledge_lag_days,
    ):
        raise _error("constructed_rule_provider_drift")
    if not has_exact_runtime_value(
        components.settlement_model.trading_calendar,
        tuple(components.feed.trading_days()),
    ):
        raise _error("constructed_settlement_calendar_drift")


def _require_pristine_account_and_orders(
    config: BacktestServiceConfig,
    components: ConstructedBacktestComponents,
) -> None:
    if not has_exact_runtime_value(
        vars(components.brokerage).get("_frozen_quantities"),
        {},
    ):
        raise _error("constructed_brokerage_state_drift")

    account_state = vars(components.account)
    positions = account_state.get("_positions")
    if not has_exact_runtime_value(positions, {}):
        raise _error("constructed_brokerage_account_drift")
    expected_cash = CashBook(
        available=config.initial_cash,
        settled=config.initial_cash,
        frozen=0.0,
    )
    if (
        account_state.get("_cash") is not components.cash
        or account_state.get("_event_bus") is not None
        or not has_exact_runtime_value(components.cash, expected_cash)
    ):
        raise _error("constructed_brokerage_account_drift")

    order_state_drift = pristine_order_state_drift_reason(
        components.order_journal,
        components.order_book,
    )
    if order_state_drift is not None:
        raise _error(order_state_drift)


def require_actual_component_state(
    *,
    config: BacktestServiceConfig,
    expected_order_type: OrderType,
    expected_slippage_basis_points: int,
    components: ConstructedBacktestComponents,
    resume_state: ResearchBacktestResumeState | None,
) -> tuple[OrderType, tuple[LotSizeCheck, BuyingPowerCheck]]:
    """Verify state and identity of every numerical component."""
    _require_component_types(components)
    _require_component_state_shapes(components)
    _require_fill_state(config, components)
    if not has_exact_runtime_value(
        components.slippage_model.bps,
        float(expected_slippage_basis_points),
    ):
        raise _error("constructed_slippage_model_parameter_drift")
    if (resume_state is None) is not (config.resume_from_run_id == ""):
        raise _error("constructed_checkpoint_control_drift")
    planner_evidence = _require_planner_state(expected_order_type, components)
    _require_brokerage_state(config, components, resume_state)
    return planner_evidence
