"""Exact component assembly for an audit-bound research backtest service."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

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
from ditto_kernel.identity import InstrumentId
from ditto_kernel.order import OrderType
from ditto_portfolio.accounting import Account, CashBook
from ditto_risk.pre_trade import (
    BuyingPowerCheck,
    CompositePreTradeCheck,
    LotSizeCheck,
)
from ditto_strategy.alpha.parameters import (
    EffectiveParameter,
    canonical_parameter_hash,
)
from ditto_strategy.alpha.pipeline import StrategyPipeline

from ditto_application.exceptions import AppProcessError
from ditto_application.processes.execution.backtest_process import (
    BacktestService,
    BacktestServiceConfig,
    BacktestServiceOptions,
)
from ditto_application.processes.execution.factor_bridge import CompiledExpressions
from ditto_application.processes.experiments._execution_bundle_inputs import (
    BaselineExecutorBinding,
)
from ditto_application.processes.experiments.backtest_service_wiring import (
    ClosedBacktestServiceGraph,
    ConstructedBacktestComponents,
    KnowledgeLagRuleProvider,
    KnowledgeLagRulesGetter,
    require_actual_component_state,
    require_closed_backtest_service,
)
from ditto_application.processes.experiments.execution_bundle import (
    BacktestExecutionConfigBinding,
    ExactBenchmarkBinding,
    ExecutionEvidenceSource,
    PolicyModelEvidenceBinding,
    ResearchExecutionAudit,
    ResearchExecutionSemantics,
    ResearchFillMode,
    StrategyExecutionBinding,
    VersionedExecutionComponent,
)
from ditto_application.processes.experiments.research_data_feed import (
    ResearchDataFeed,
)
from ditto_application.processes.experiments.research_policy_artifact import (
    VerifiedInstrumentRulesArtifact,
)

__all__ = [
    "FrozenBacktestStrategyBuild",
    "ResearchBacktestComponentBuild",
    "build_research_backtest_service",
]

_PARTS_PER_MILLION = 1_000_000
_MINOR_UNITS_PER_CNY = 100
_CONTRACT_VERSION = 1
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
class FrozenBacktestStrategyBuild:
    """Rebuilt strategy values consumed by the real backtest path."""

    binding: StrategyExecutionBinding | BaselineExecutorBinding
    pipeline: StrategyPipeline
    pipeline_attestation: object | None
    compiled_expressions: CompiledExpressions | None
    effective_parameters: tuple[EffectiveParameter, ...]
    planner_order_type: OrderType
    rebalance_frequency: str


@dataclass(frozen=True, slots=True)
class ResearchBacktestComponentBuild:
    """Real service plus evidence reconstructed from its concrete components."""

    service: BacktestService
    execution_config: BacktestExecutionConfigBinding
    graph: ClosedBacktestServiceGraph


def build_research_backtest_service(
    *,
    audit: ResearchExecutionAudit,
    strategy: FrozenBacktestStrategyBuild,
    rules_artifact: VerifiedInstrumentRulesArtifact,
    feed: ResearchDataFeed,
    benchmark: ExactBenchmarkBinding | None,
    external_should_stop: Callable[[], bool],
) -> ResearchBacktestComponentBuild:
    """Build all numerical components and attest their concrete identities."""
    declared = audit.semantics.backtest
    _require_policy_model_evidence(audit.semantics, rules_artifact)
    _require_declared_components(declared, strategy)
    initial_cash = _initial_cash(declared)
    participation_rate = declared.participation_rate_ppm / _PARTS_PER_MILLION
    if declared.fill_mode is ResearchFillMode.ALL_OR_NOTHING:
        participation_rate = 0.0
    auction_model = ClosingAuctionFillModel(
        participation_rate_threshold=_CLOSING_AUCTION_PARTICIPATION_RATE,
    )
    fill_model = AShareFillModel(
        auction_model=auction_model,
        participation_rate=participation_rate,
    )
    fee_model = AShareFeeModel()
    slippage_model = FixedBpsSlippage(
        bps=float(declared.slippage_basis_points),
    )
    settlement_model = AShareSettlementModel(tuple(feed.trading_days()))
    brokerage_model = BrokerageModel(
        fill_model=fill_model,
        slippage_model=slippage_model,
        fee_model=fee_model,
        settlement_model=settlement_model,
    )
    rule_provider = KnowledgeLagRuleProvider(
        rules_artifact.build_rule_provider(),
        audit.semantics.knowledge_lag_days,
    )
    _validate_rule_coverage(
        audit.semantics,
        strategy,
        feed,
        rule_provider,
    )
    cash = CashBook(
        available=initial_cash,
        settled=initial_cash,
        frozen=0.0,
    )
    account = Account(cash=cash)
    order_journal = InMemoryOrderEventJournal()
    order_book = OrderBook(journal=order_journal)
    rules_getter = KnowledgeLagRulesGetter(rule_provider)
    brokerage = BacktestBrokerage(
        account=account,
        order_book=order_book,
        model=brokerage_model,
        rules_getter=rules_getter,
    )
    planner = SimpleExecutionPlanner(
        default_order_type=strategy.planner_order_type,
    )
    pre_trade = CompositePreTradeCheck(
        checks=(LotSizeCheck(), BuyingPowerCheck()),
    )
    config = _service_config(
        audit,
        strategy,
        initial_cash,
        benchmark,
    )
    options = BacktestServiceOptions(
        fee_model=fee_model,
        slippage_model=slippage_model,
        rule_provider=rule_provider,
        compiled_expressions=strategy.compiled_expressions,
        external_should_stop=external_should_stop,
    )
    service = BacktestService(
        config=config,
        pipeline=strategy.pipeline,
        planner=planner,
        brokerage=brokerage,
        pre_trade_check=pre_trade,
        data_feed=feed,
        options=options,
    )
    components = ConstructedBacktestComponents(
        feed=feed,
        rules=rules_artifact,
        auction_model=auction_model,
        fill_model=fill_model,
        brokerage_model=brokerage_model,
        cash=cash,
        account=account,
        order_journal=order_journal,
        order_book=order_book,
        rules_getter=rules_getter,
        rule_provider=rule_provider,
        brokerage=brokerage,
        planner=planner,
        fee_model=fee_model,
        slippage_model=slippage_model,
        settlement_model=settlement_model,
        pre_trade=pre_trade,
        options=options,
        benchmark=benchmark,
    )
    graph = ClosedBacktestServiceGraph(
        service=service,
        audit=audit,
        config=config,
        pipeline=strategy.pipeline,
        planner=components.planner,
        brokerage=components.brokerage,
        pre_trade=components.pre_trade,
        feed=components.feed,
        options=components.options,
        fee_model=components.fee_model,
        slippage_model=components.slippage_model,
        rule_provider=components.rule_provider,
        compiled_expressions=strategy.compiled_expressions,
        pipeline_attestation=strategy.pipeline_attestation,
        external_should_stop=external_should_stop,
        components=components,
    )
    require_closed_backtest_service(
        graph,
        expected_audit=audit,
        expected_should_stop=external_should_stop,
    )
    actual = _actual_backtest_binding(
        audit.semantics,
        config,
        strategy,
        components,
    )
    if actual != declared:
        raise _error("constructed_backtest_component_drift")
    return ResearchBacktestComponentBuild(service, actual, graph)


def _initial_cash(binding: BacktestExecutionConfigBinding) -> float:
    if binding.currency != "CNY":
        raise _error("unsupported_research_currency", currency=binding.currency)
    return float(
        Decimal(binding.initial_cash_minor_units) / Decimal(_MINOR_UNITS_PER_CNY)
    )


def _validate_rule_coverage(
    semantics: ResearchExecutionSemantics,
    strategy: FrozenBacktestStrategyBuild,
    feed: ResearchDataFeed,
    provider: KnowledgeLagRuleProvider,
) -> None:
    """Prove every executable PIT member has complete lagged rule evidence."""
    expected_asset_class = semantics.policy.rules.required_asset_class.value
    expected_currency = semantics.backtest.currency
    expected_order_type = strategy.planner_order_type.value
    for trade_date in feed.trading_days():
        instrument_ids = sorted(feed.get_slice(trade_date).bars, key=int)
        resolved = provider.get_rules(trade_date, instrument_ids)
        if set(resolved) != set(instrument_ids):
            raise _error(
                "frozen_instrument_rules_missing",
                trade_date=trade_date,
                instrument_ids=tuple(int(item) for item in instrument_ids),
            )
        for instrument_id, rules in resolved.items():
            definition, trading_rule, _fee_schedule = rules
            if (
                definition.asset_class != expected_asset_class
                or definition.currency != expected_currency
            ):
                raise _error(
                    "frozen_instrument_definition_policy_drift",
                    trade_date=trade_date,
                    instrument_id=int(instrument_id),
                )
            try:
                session_date = date.fromisoformat(trade_date)
                ipo_date = (
                    None
                    if definition.ipo_date is None
                    else date.fromisoformat(definition.ipo_date)
                )
                delisting_date = (
                    None
                    if definition.delisting_date is None
                    else date.fromisoformat(definition.delisting_date)
                )
            except (TypeError, ValueError):
                raise _error(
                    "frozen_instrument_lifecycle_drift",
                    trade_date=trade_date,
                    instrument_id=int(instrument_id),
                ) from None
            if (
                definition.lifecycle_state != "normal"
                or (ipo_date is not None and session_date < ipo_date)
                or (delisting_date is not None and session_date > delisting_date)
            ):
                raise _error(
                    "frozen_instrument_lifecycle_drift",
                    trade_date=trade_date,
                    instrument_id=int(instrument_id),
                )
            if expected_order_type not in trading_rule.order_types_supported:
                raise _error(
                    "frozen_order_type_not_supported",
                    trade_date=trade_date,
                    instrument_id=int(instrument_id),
                    order_type=expected_order_type,
                )


def _service_config(
    audit: ResearchExecutionAudit,
    strategy: FrozenBacktestStrategyBuild,
    initial_cash: float,
    benchmark: ExactBenchmarkBinding | None,
) -> BacktestServiceConfig:
    semantics = audit.semantics
    snapshot = semantics.snapshot
    binding = strategy.binding
    if type(binding) is StrategyExecutionBinding:
        strategy_id = binding.exact_strategy.strategy_id
        strategy_version = str(binding.exact_strategy.version)
        base_spec_hash = binding.exact_strategy.spec_hash
        spec_hash = binding.resolved_spec_hash
        parameter_hash = binding.parameter_hash
        candidate_parameters = binding.candidate_parameters
        effective_parameters = strategy.effective_parameters
        factor_refs = tuple(item.binding_hash for item in binding.factor_bindings)
    elif type(binding) is BaselineExecutorBinding:
        strategy_id = binding.baseline_ref
        strategy_version = str(binding.executor_contract_version)
        base_spec_hash = binding.descriptor_hash
        spec_hash = binding.descriptor_hash
        parameter_hash = canonical_parameter_hash(())
        candidate_parameters = ()
        effective_parameters = ()
        factor_refs = ()
    else:
        raise _error("invalid_strategy_execution_binding")
    return BacktestServiceConfig(
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        run_id=audit.backtest_run_id,
        start_date=semantics.test_start.isoformat(),
        end_date=semantics.test_end.isoformat(),
        initial_cash=initial_cash,
        benchmark_id=(
            None if benchmark is None else InstrumentId(benchmark.instrument_id)
        ),
        candidate_parameters=candidate_parameters,
        research_snapshot_id=snapshot.exact_snapshot.snapshot_id,
        research_snapshot_manifest_hash=snapshot.exact_snapshot.manifest_hash,
        rebalance_freq=strategy.rebalance_frequency,
        engine_version=semantics.backtest.engine_version,
        random_seed=semantics.seed,
        execution_delay=semantics.execution_delay_sessions,
        knowledge_lag_days=semantics.knowledge_lag_days,
        code_version=semantics.environment.code_version,
        data_catalog_identities=tuple(
            f"{item.input_id}:{item.content_hash}:{item.schema_hash}"
            for item in snapshot.inputs
        ),
        factor_report_refs=factor_refs,
        recommendation_status="research",
        participation_rate=(
            semantics.backtest.participation_rate_ppm / _PARTS_PER_MILLION
        ),
        fill_mode=semantics.backtest.fill_mode.value,
        resume_from_run_id="",
        spec_hash=spec_hash,
        base_spec_hash=base_spec_hash,
        parameter_hash=parameter_hash,
        effective_parameters=effective_parameters,
    )


def _require_declared_components(
    binding: BacktestExecutionConfigBinding,
    strategy: FrozenBacktestStrategyBuild,
) -> None:
    order_type = strategy.planner_order_type.value
    fill_key = f"ditto_backtest.a_share_fill.{binding.fill_mode.value}"
    expected_rebalance = (
        "research.baseline.fold_schedule"
        if strategy.rebalance_frequency == "fold_schedule"
        else f"ditto_backtest.rebalance.{strategy.rebalance_frequency}"
    )
    expected = {
        "engine": (binding.engine, "ditto_backtest.engine_loop"),
        "rebalance_policy": (binding.rebalance_policy, expected_rebalance),
        "fill_model": (
            binding.fill_model,
            fill_key,
        ),
        "brokerage_model": (
            binding.brokerage_model,
            "ditto_backtest.backtest_brokerage",
        ),
        "execution_planner": (
            binding.execution_planner,
            f"ditto_execution.simple_execution_planner.{order_type}",
        ),
    }
    for role, (component, key) in expected.items():
        if (
            component.implementation_key != key
            or component.contract_version != _CONTRACT_VERSION
        ):
            raise _error("unsupported_backtest_component", role=role)
    if binding.engine_version != "0.1.0":
        raise _error("unsupported_backtest_engine_version")
    if binding.rebalance_frequency != strategy.rebalance_frequency:
        raise _error("rebalance_frequency_drift")
    if binding.post_trade_guard is not None:
        raise _error("unsupported_post_trade_guard")
    if binding.pre_trade_checks != (
        VersionedExecutionComponent("ditto_risk.lot_size_check", 1),
        VersionedExecutionComponent("ditto_risk.buying_power_check", 1),
    ):
        raise _error("pre_trade_check_order_drift")


def _require_policy_model_evidence(
    semantics: ResearchExecutionSemantics,
    rules: VerifiedInstrumentRulesArtifact,
) -> None:
    expected = _policy_models_from_objects(
        semantics,
        rules,
        AShareFeeModel(),
        FixedBpsSlippage(float(semantics.backtest.slippage_basis_points)),
        AShareSettlementModel(),
    )
    if semantics.backtest.policy_model_evidence != expected:
        raise _error("policy_model_evidence_drift")


def _actual_backtest_binding(
    semantics: ResearchExecutionSemantics,
    config: BacktestServiceConfig,
    strategy: FrozenBacktestStrategyBuild,
    components: ConstructedBacktestComponents,
) -> BacktestExecutionConfigBinding:
    planner_order_type, checks = require_actual_component_state(
        config=config,
        expected_order_type=strategy.planner_order_type,
        expected_slippage_basis_points=semantics.backtest.slippage_basis_points,
        components=components,
    )
    minor_units = int(
        Decimal(str(components.cash.available)) * Decimal(_MINOR_UNITS_PER_CNY)
    )
    planner_key = f"ditto_execution.simple_execution_planner.{planner_order_type.value}"
    rebalance_key = (
        "research.baseline.fold_schedule"
        if config.rebalance_freq == "fold_schedule"
        else f"ditto_backtest.rebalance.{config.rebalance_freq}"
    )
    fill_key = f"ditto_backtest.a_share_fill.{config.fill_mode}"
    return BacktestExecutionConfigBinding(
        initial_cash_minor_units=minor_units,
        currency="CNY",
        engine=VersionedExecutionComponent("ditto_backtest.engine_loop", 1),
        engine_version=config.engine_version,
        rebalance_policy=VersionedExecutionComponent(rebalance_key, 1),
        rebalance_frequency=config.rebalance_freq,
        participation_rate_ppm=int(
            Decimal(str(config.participation_rate)) * Decimal(_PARTS_PER_MILLION)
        ),
        fill_mode=ResearchFillMode(config.fill_mode),
        fill_model=VersionedExecutionComponent(
            fill_key,
            1,
        ),
        brokerage_model=VersionedExecutionComponent(
            "ditto_backtest.backtest_brokerage",
            1,
        ),
        execution_planner=VersionedExecutionComponent(planner_key, 1),
        slippage_basis_points=int(components.slippage_model.bps),
        benchmark=components.benchmark,
        policy_hash=semantics.policy.canonical_hash,
        policy_model_evidence=_policy_models_from_objects(
            semantics,
            components.rules,
            components.fee_model,
            components.slippage_model,
            components.settlement_model,
        ),
        pre_trade_checks=tuple(
            VersionedExecutionComponent(
                "ditto_risk.lot_size_check"
                if type(item) is LotSizeCheck
                else "ditto_risk.buying_power_check",
                1,
            )
            for item in checks
        ),
        post_trade_guard=None,
        data_feed_manifest_hash=components.feed.evidence_manifest.canonical_hash,
    )


def _policy_models_from_objects(
    semantics: ResearchExecutionSemantics,
    rules: VerifiedInstrumentRulesArtifact,
    fee_model: AShareFeeModel,
    slippage_model: FixedBpsSlippage,
    settlement_model: AShareSettlementModel,
) -> tuple[PolicyModelEvidenceBinding, ...]:
    if (
        type(fee_model) is not AShareFeeModel
        or type(slippage_model) is not FixedBpsSlippage
        or type(settlement_model) is not AShareSettlementModel
        or slippage_model.bps != float(semantics.policy.slippage.basis_points)
    ):
        raise _error("constructed_policy_model_type_drift")
    policy = semantics.policy
    actual_models = (
        (policy.fees.model_key, policy.fees.model_version),
        (policy.rules.contract_key, policy.rules.contract_version),
        (policy.settlement.model_key, policy.settlement.model_version),
        (policy.slippage.model_key, policy.slippage.model_version),
    )
    expected_models = (
        ("ditto_execution.a_share_fee", 1),
        ("ditto_kernel.instrument_rules", 1),
        ("ditto_backtest.a_share_settlement", 1),
        ("ditto_backtest.fixed_bps_slippage", 1),
    )
    if actual_models != expected_models:
        raise _error("unsupported_policy_model_component")
    frozen = ExecutionEvidenceSource.FROZEN_SNAPSHOT_PIT
    code = ExecutionEvidenceSource.VERSIONED_CODE_REGISTRY
    evidence = rules.input_evidence
    return (
        PolicyModelEvidenceBinding(
            role="fees",
            implementation=VersionedExecutionComponent(
                "ditto_execution.a_share_fee",
                1,
            ),
            evidence_source=frozen,
            inputs=(evidence,),
        ),
        PolicyModelEvidenceBinding(
            role="rules",
            implementation=VersionedExecutionComponent(
                "ditto_kernel.instrument_rules",
                1,
            ),
            evidence_source=frozen,
            inputs=(evidence,),
        ),
        PolicyModelEvidenceBinding(
            role="settlement",
            implementation=VersionedExecutionComponent(
                "ditto_backtest.a_share_settlement",
                1,
            ),
            evidence_source=frozen,
            inputs=(evidence,),
        ),
        PolicyModelEvidenceBinding(
            role="slippage",
            implementation=VersionedExecutionComponent(
                "ditto_backtest.fixed_bps_slippage",
                1,
            ),
            evidence_source=code,
            inputs=(),
        ),
    )
