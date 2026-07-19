"""Contract tests for the frozen R3 daily core-factor catalog."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from hashlib import sha256
from typing import cast

import orjson
import pytest
from ditto_features.evaluation.evaluator._helpers import empty_report
from ditto_features.evaluation.report import (
    FactorExposureResult,
    project_r3_factor_diagnostics,
)
from ditto_features.factors import core_daily
from ditto_features.factors.core_daily import (
    R3_CORE_FACTOR_CATALOG,
    AssetLane,
    AvailabilityContext,
    AvailabilityReason,
    CertifiedHistoryCoverage,
    Lookback,
    LookbackUnit,
    MaterializedIntermediate,
    MissingValuePolicy,
    PitRequirement,
    PreprocessingStep,
    StandardizationMethod,
    WinsorizationMethod,
    assess_core_factor_input_availability,
)
from ditto_features.factors.factor_specs import ALL_FACTOR_SPECS
from ditto_features.factors.production_guard import validate_r3_core_factor_catalog

CORE_IDS = (
    "momentum_1m",
    "momentum_3m",
    "reversal_1w",
    "volatility_factor",
    "vol_ratio",
    "liquidity",
    "relative_strength_60d",
    "ep_ttm",
    "bp_ratio",
    "quality_roe",
    "revenue_growth",
    "log_free_float_cap",
)

MARKET_LANES = frozenset({AssetLane.STOCK, AssetLane.ETF})
STOCK_LANE = frozenset({AssetLane.STOCK})
EXPECTED_CONTRACT = {
    "momentum_1m": (
        MARKET_LANES,
        {
            AssetLane.STOCK: ("stock_daily", "adj_factor"),
            AssetLane.ETF: ("etf_daily", "fund_adj"),
        },
        Lookback(20, LookbackUnit.TRADING_DAYS),
        PitRequirement.KNOWN_AT,
    ),
    "momentum_3m": (
        MARKET_LANES,
        {
            AssetLane.STOCK: ("stock_daily", "adj_factor"),
            AssetLane.ETF: ("etf_daily", "fund_adj"),
        },
        Lookback(60, LookbackUnit.TRADING_DAYS),
        PitRequirement.KNOWN_AT,
    ),
    "reversal_1w": (
        MARKET_LANES,
        {
            AssetLane.STOCK: ("stock_daily", "adj_factor"),
            AssetLane.ETF: ("etf_daily", "fund_adj"),
        },
        Lookback(5, LookbackUnit.TRADING_DAYS),
        PitRequirement.KNOWN_AT,
    ),
    "volatility_factor": (
        MARKET_LANES,
        {
            AssetLane.STOCK: ("stock_daily", "adj_factor"),
            AssetLane.ETF: ("etf_daily", "fund_adj"),
        },
        Lookback(20, LookbackUnit.TRADING_DAYS),
        PitRequirement.KNOWN_AT,
    ),
    "vol_ratio": (
        MARKET_LANES,
        {
            AssetLane.STOCK: ("stock_daily", "adj_factor"),
            AssetLane.ETF: ("etf_daily", "fund_adj"),
        },
        Lookback(60, LookbackUnit.TRADING_DAYS),
        PitRequirement.KNOWN_AT,
    ),
    "liquidity": (
        MARKET_LANES,
        {AssetLane.STOCK: ("stock_daily",), AssetLane.ETF: ("etf_daily",)},
        Lookback(20, LookbackUnit.TRADING_DAYS),
        PitRequirement.KNOWN_AT,
    ),
    "relative_strength_60d": (
        MARKET_LANES,
        {
            AssetLane.STOCK: ("stock_daily", "adj_factor", "index_daily"),
            AssetLane.ETF: ("etf_daily", "fund_adj", "index_daily"),
        },
        Lookback(60, LookbackUnit.TRADING_DAYS),
        PitRequirement.KNOWN_AT,
    ),
    "ep_ttm": (
        STOCK_LANE,
        {
            AssetLane.STOCK: (
                "stock_daily",
                "income_statement",
                "balance_sheet",
            )
        },
        Lookback(4, LookbackUnit.REPORTING_PERIODS),
        PitRequirement.ANNOUNCEMENT_KNOWN_AT,
    ),
    "bp_ratio": (
        STOCK_LANE,
        {AssetLane.STOCK: ("stock_daily", "balance_sheet")},
        Lookback(1, LookbackUnit.REPORTING_PERIODS),
        PitRequirement.ANNOUNCEMENT_KNOWN_AT,
    ),
    "quality_roe": (
        STOCK_LANE,
        {AssetLane.STOCK: ("balance_sheet", "income_statement")},
        Lookback(1, LookbackUnit.REPORTING_PERIODS),
        PitRequirement.ANNOUNCEMENT_KNOWN_AT,
    ),
    "revenue_growth": (
        STOCK_LANE,
        {AssetLane.STOCK: ("income_statement",)},
        Lookback(4, LookbackUnit.REPORTING_PERIODS),
        PitRequirement.ANNOUNCEMENT_KNOWN_AT,
    ),
    "log_free_float_cap": (
        STOCK_LANE,
        {AssetLane.STOCK: ("stock_daily", "valuation_metrics")},
        Lookback(1, LookbackUnit.TRADING_DAYS),
        PitRequirement.KNOWN_AT,
    ),
}

PREPROCESSING_ORDER = (
    PreprocessingStep.PIT_ALIGNMENT,
    PreprocessingStep.COVERAGE_VALIDATION,
    PreprocessingStep.MISSING_VALUE_POLICY,
    PreprocessingStep.WINSORIZATION,
    PreprocessingStep.NEUTRALIZATION,
    PreprocessingStep.STANDARDIZATION,
    PreprocessingStep.WEIGHTED_SCORING,
)


def _descriptor(factor_id: str):  # type annotation would repeat the public API
    return R3_CORE_FACTOR_CATALOG.by_id(factor_id)


def _context(
    *datasets: str,
    lane: AssetLane = AssetLane.STOCK,
    history: int = 500,
    reporting_history: int | None = None,
    benchmark_id: str | None = "000300.SH",
) -> AvailabilityContext:
    expanded_datasets = set(datasets)
    if lane is AssetLane.STOCK:
        if "stock_daily" in expanded_datasets:
            expanded_datasets.add("adj_factor")
        expanded_datasets.update({"industry_mapping", "valuation_metrics"})
    elif "etf_daily" in expanded_datasets:
        expanded_datasets.add("fund_adj")
    certified_fields_by_dataset = {
        "stock_daily": frozenset({"market.close", "market.amount"}),
        "etf_daily": frozenset({"market.close", "market.amount"}),
        "adj_factor": frozenset({"market.adj_factor"}),
        "fund_adj": frozenset({"market.adj_factor"}),
        "index_daily": frozenset({"benchmark.close"}),
        "income_statement": frozenset(
            {
                "fundamentals.net_income_ttm",
                "fundamentals.net_income",
                "fundamentals.revenue",
            }
        ),
        "balance_sheet": frozenset(
            {
                "fundamentals.total_shares",
                "fundamentals.total_equity",
                "fundamentals.equity",
            }
        ),
        "valuation_metrics": frozenset(
            {"market_cap", "fundamentals.free_float_shares"}
        ),
        "industry_mapping": frozenset({"industry_id"}),
    }
    coverage = CertifiedHistoryCoverage(
        trading_days=history,
        reporting_periods=(history if reporting_history is None else reporting_history),
    )
    benchmarks = {}
    if benchmark_id is not None and "index_daily" in expanded_datasets:
        benchmarks[benchmark_id] = core_daily.CertifiedBenchmarkEvidence(
            benchmark_id=benchmark_id,
            dataset_id="index_daily",
            certified_fields=frozenset({"benchmark.close"}),
            certified_history=coverage,
            certified_pit=PitRequirement.KNOWN_AT,
        )
    return AvailabilityContext(
        lane=lane,
        certified_datasets=frozenset(expanded_datasets),
        certified_history=dict.fromkeys(expanded_datasets, coverage),
        certified_fields={
            dataset: certified_fields_by_dataset.get(dataset, frozenset())
            for dataset in expanded_datasets
        },
        benchmark_id=benchmark_id,
        certified_benchmarks=benchmarks,
        certified_pit={
            dataset: (
                PitRequirement.ANNOUNCEMENT_KNOWN_AT
                if dataset in {"income_statement", "balance_sheet"}
                else PitRequirement.KNOWN_AT
            )
            for dataset in expanded_datasets
        },
    )


def test_catalog_freezes_exact_ids_lanes_datasets_lookbacks_and_pit() -> None:
    assert R3_CORE_FACTOR_CATALOG.factor_ids == CORE_IDS
    assert len(R3_CORE_FACTOR_CATALOG.descriptors) == 12

    for factor_id, (lanes, datasets, lookback, pit) in EXPECTED_CONTRACT.items():
        descriptor = _descriptor(factor_id)
        assert descriptor.lanes == lanes
        assert {
            lane: descriptor.required_datasets_for(lane) for lane in descriptor.lanes
        } == datasets
        assert descriptor.lookback == lookback
        assert descriptor.pit_requirement is pit

    with pytest.raises(FrozenInstanceError):
        _descriptor("momentum_1m").factor_id = "changed"  # type: ignore[misc]


def test_preprocessing_order_and_payload_hash_are_stable() -> None:
    assert R3_CORE_FACTOR_CATALOG.preprocessing.steps == PREPROCESSING_ORDER
    assert (
        R3_CORE_FACTOR_CATALOG.preprocessing.missing_value_policy
        is MissingValuePolicy.DROP
    )
    assert (
        R3_CORE_FACTOR_CATALOG.preprocessing.winsorization is WinsorizationMethod.MAD_3
    )
    assert (
        R3_CORE_FACTOR_CATALOG.preprocessing.standardization
        is StandardizationMethod.ZSCORE
    )
    assert R3_CORE_FACTOR_CATALOG.preprocessing.applicable_lanes == MARKET_LANES
    assert R3_CORE_FACTOR_CATALOG.preprocessing.industry_neutralization_lanes == (
        STOCK_LANE
    )
    assert R3_CORE_FACTOR_CATALOG.preprocessing.size_neutralization_lanes == STOCK_LANE
    expected_hash = sha256(
        orjson.dumps(
            R3_CORE_FACTOR_CATALOG.resolved_payload,
            option=orjson.OPT_SORT_KEYS,
        )
    ).hexdigest()
    assert R3_CORE_FACTOR_CATALOG.payload_hash == expected_hash
    assert R3_CORE_FACTOR_CATALOG.payload_hash == (
        R3_CORE_FACTOR_CATALOG.recompute_payload_hash()
    )


def test_preprocessing_rejects_untyped_or_unsupported_methods() -> None:
    preprocessing = R3_CORE_FACTOR_CATALOG.preprocessing
    with pytest.raises(ValueError, match="invalid preprocessing step"):
        replace(
            preprocessing,
            steps=(cast(PreprocessingStep, "pit_alignment"),),
        )
    with pytest.raises(ValueError, match="invalid missing-value policy"):
        replace(
            preprocessing,
            missing_value_policy=cast(MissingValuePolicy, "forward_fill"),
        )
    with pytest.raises(ValueError, match="invalid winsorization method"):
        replace(
            preprocessing,
            winsorization=cast(WinsorizationMethod, "percentile"),
        )
    with pytest.raises(ValueError, match="invalid standardization method"):
        replace(
            preprocessing,
            standardization=cast(StandardizationMethod, "min_max"),
        )


def test_size_factor_rejects_size_neutralization() -> None:
    size = _descriptor("log_free_float_cap")
    with pytest.raises(ValueError, match=r"size factor.*size-neutralized"):
        replace(size, neutralize_size=True)


@pytest.mark.parametrize(
    ("factor_id", "context", "reason", "datasets"),
    [
        (
            "quality_roe",
            _context("balance_sheet"),
            AvailabilityReason.UNCERTIFIED_DATASET,
            ("income_statement",),
        ),
        (
            "momentum_3m",
            _context("stock_daily", history=59),
            AvailabilityReason.INSUFFICIENT_HISTORY,
            ("stock_daily", "adj_factor"),
        ),
        (
            "relative_strength_60d",
            _context("stock_daily", "index_daily", benchmark_id=None),
            AvailabilityReason.BENCHMARK_MISSING,
            (),
        ),
    ],
)
def test_availability_is_stable_and_fail_closed(
    factor_id: str,
    context: AvailabilityContext,
    reason: AvailabilityReason,
    datasets: tuple[str, ...],
) -> None:
    first = assess_core_factor_input_availability(_descriptor(factor_id), context)
    second = assess_core_factor_input_availability(_descriptor(factor_id), context)
    assert first == second
    assert first.certified_inputs_available is False
    assert first.reason is reason
    assert first.dataset_ids == datasets


def test_fundamental_availability_has_no_current_value_fallback() -> None:
    descriptor = _descriptor("ep_ttm")
    context = _context("stock_daily", "income_statement", "balance_sheet")
    unavailable = assess_core_factor_input_availability(
        descriptor,
        replace(context, certified_pit={}),
    )
    assert unavailable.certified_inputs_available is False
    assert unavailable.reason is AvailabilityReason.PIT_ALIGNMENT_MISSING
    assert not hasattr(context, "current_value_fallback")


def test_market_availability_requires_known_at_alignment() -> None:
    context = replace(
        _context("stock_daily", history=20),
        certified_pit={},
    )
    unavailable = assess_core_factor_input_availability(
        _descriptor("momentum_1m"),
        context,
    )
    assert unavailable.certified_inputs_available is False
    assert unavailable.reason is AvailabilityReason.PIT_ALIGNMENT_MISSING
    assert unavailable.dataset_ids == ("stock_daily", "adj_factor")


def test_history_coverage_uses_the_descriptor_lookback_unit() -> None:
    market = _context("stock_daily", history=59, reporting_history=500)
    market_result = assess_core_factor_input_availability(
        _descriptor("momentum_3m"),
        market,
    )
    assert market_result.reason is AvailabilityReason.INSUFFICIENT_HISTORY

    fundamental = _context(
        "stock_daily",
        "income_statement",
        "balance_sheet",
        history=500,
        reporting_history=4,
    )
    fundamental = replace(
        fundamental,
        certified_history={
            "stock_daily": CertifiedHistoryCoverage(500, 4),
            "income_statement": CertifiedHistoryCoverage(500, 3),
            "balance_sheet": CertifiedHistoryCoverage(500, 4),
        },
    )
    fundamental_result = assess_core_factor_input_availability(
        _descriptor("ep_ttm"),
        fundamental,
    )
    assert fundamental_result.reason is AvailabilityReason.INSUFFICIENT_HISTORY
    assert fundamental_result.dataset_ids == ("income_statement",)


def test_availability_context_copies_history_evidence() -> None:
    history = {"stock_daily": CertifiedHistoryCoverage(20, 0)}
    context = AvailabilityContext(
        lane=AssetLane.STOCK,
        certified_datasets=frozenset(history),
        certified_history=history,
        certified_pit={"stock_daily": PitRequirement.KNOWN_AT},
    )
    history["stock_daily"] = CertifiedHistoryCoverage(0, 0)
    assert context.certified_history["stock_daily"].trading_days == 20


@pytest.mark.parametrize(
    ("factor_id", "context"),
    [
        ("momentum_1m", _context("stock_daily", history=20)),
        (
            "relative_strength_60d",
            _context("stock_daily", "index_daily", history=60),
        ),
        (
            "ep_ttm",
            replace(
                _context(
                    "stock_daily",
                    "income_statement",
                    "balance_sheet",
                    history=4,
                ),
            ),
        ),
    ],
)
def test_availability_opens_only_when_every_contract_is_satisfied(
    factor_id: str,
    context: AvailabilityContext,
) -> None:
    result = assess_core_factor_input_availability(_descriptor(factor_id), context)
    assert result.certified_inputs_available is True
    assert result.reason is None
    assert result.dataset_ids == ()


def test_catalog_is_valid_for_production_without_relaxing_expression_guard() -> None:
    validate_r3_core_factor_catalog(R3_CORE_FACTOR_CATALOG)
    assert ALL_FACTOR_SPECS["relative_strength_60d"].computation_type == "python"
    assert ALL_FACTOR_SPECS["relative_strength_60d"].expression == ""
    liquidity = _descriptor("liquidity")
    assert liquidity.materialized_intermediates == (
        MaterializedIntermediate(
            column_id="ts_mean_daily_amount_20d",
            expression="ts_mean(market.amount, 20)",
            dependencies=("market.amount",),
            lookback=Lookback(21, LookbackUnit.TRADING_DAYS),
        ),
    )

    with pytest.raises(ValueError, match="unregistered core factor"):
        validate_r3_core_factor_catalog(
            replace(
                R3_CORE_FACTOR_CATALOG,
                descriptors=(
                    replace(
                        R3_CORE_FACTOR_CATALOG.descriptors[0],
                        factor_id="unknown_factor",
                    ),
                    *R3_CORE_FACTOR_CATALOG.descriptors[1:],
                ),
            )
        )


def test_production_validation_rechecks_bypassed_descriptor_and_catalog_state() -> None:
    descriptor = replace(_descriptor("momentum_1m"))
    object.__setattr__(descriptor, "lookback", Lookback(19, LookbackUnit.TRADING_DAYS))
    bypassed_descriptor_catalog = replace(
        R3_CORE_FACTOR_CATALOG,
        descriptors=(descriptor, *R3_CORE_FACTOR_CATALOG.descriptors[1:]),
    )
    with pytest.raises(ValueError, match="catalog payload changed"):
        validate_r3_core_factor_catalog(bypassed_descriptor_catalog)

    bypassed_catalog = replace(R3_CORE_FACTOR_CATALOG)
    object.__setattr__(
        bypassed_catalog,
        "descriptors",
        (*bypassed_catalog.descriptors, bypassed_catalog.descriptors[-1]),
    )
    with pytest.raises(ValueError, match="core factor IDs changed"):
        validate_r3_core_factor_catalog(bypassed_catalog)


def test_diagnostics_projection_only_marks_metrics_that_are_present() -> None:
    projection = project_r3_factor_diagnostics(
        {
            "coverage": 0.91,
            "missingness": 0.09,
            "rank_ic": 0.04,
            "icir": 0.8,
            "avg_turnover": 0.12,
        }
    )
    assert projection.computed_metrics == (
        "coverage",
        "missingness",
        "rank_ic",
        "icir",
        "turnover",
    )
    assert projection.values == {
        "coverage": 0.91,
        "missingness": 0.09,
        "rank_ic": 0.04,
        "icir": 0.8,
        "turnover": 0.12,
    }
    assert "decay" not in projection.computed_metrics
    assert "quantile_return" not in projection.computed_metrics
    assert "cost_drag" not in projection.computed_metrics
    assert "factor_contribution" not in projection.computed_metrics


def test_coverage_and_missingness_do_not_imply_other_diagnostics() -> None:
    projection = project_r3_factor_diagnostics({"coverage": 1.0, "missingness": 0.0})
    assert projection.computed_metrics == ("coverage", "missingness")
    assert projection.values == {"coverage": 1.0, "missingness": 0.0}


def test_empty_collections_and_empty_report_are_not_claimed_as_computed() -> None:
    projection = project_r3_factor_diagnostics(
        {
            "coverage": 0.5,
            "ic_decay": [],
            "quantile_annual_returns": {},
            "factor_exposure": None,
        }
    )
    assert projection.computed_metrics == ("coverage",)

    report = empty_report(
        factor_id="momentum_1m",
        factor_version=1,
        period=("2025-01-01", "2025-01-31"),
        holding_period=5,
        n_quantiles=5,
    )
    empty_projection = project_r3_factor_diagnostics(report)
    assert empty_projection.computed_metrics == ()
    assert empty_projection.values == {}


def test_actual_report_projects_only_existing_evaluator_diagnostics() -> None:
    base = empty_report(
        factor_id="momentum_1m",
        factor_version=1,
        period=("2025-01-01", "2025-06-30"),
        holding_period=5,
        n_quantiles=5,
    )
    exposure = FactorExposureResult(
        target_exposure={"size": 0.12},
        correlation_matrix={"momentum_1m": {"size": 0.1}},
        orthogonal_residual_stats={"size": 0.03},
        n_factors=1,
        n_dates=20,
    )
    report = replace(
        base,
        n_observations=200,
        n_dates=20,
        rank_ic_summary=replace(base.rank_ic_summary, mean=0.04, icir=0.8),
        ic_decay=[(1, 0.04), (5, 0.02)],
        quantile_annual_returns={1: -0.01, 5: 0.08},
        long_short=replace(base.long_short, annual_return=0.12),
        avg_turnover=0.2,
        net_return_after_cost=0.10,
        factor_exposure=exposure,
    )

    projection = project_r3_factor_diagnostics(report)
    assert projection.computed_metrics == (
        "rank_ic",
        "icir",
        "decay",
        "quantile_return",
        "turnover",
        "cost_drag",
        "exposure",
    )
    assert projection.values["rank_ic"] == 0.04
    assert projection.values["icir"] == 0.8
    assert projection.values["decay"] == ((1, 0.04), (5, 0.02))
    assert projection.values["quantile_return"] == {1: -0.01, 5: 0.08}
    assert projection.values["turnover"] == 0.2
    assert projection.values["cost_drag"] == pytest.approx(0.02)
    assert projection.values["exposure"] == exposure
    assert projection.values["exposure"] is not exposure
    assert "coverage" not in projection.computed_metrics
    assert "missingness" not in projection.computed_metrics


def test_price_return_inputs_are_lane_adjusted_per_dataset_contracts() -> None:
    for factor_id in (
        "momentum_1m",
        "momentum_3m",
        "reversal_1w",
        "volatility_factor",
        "vol_ratio",
        "relative_strength_60d",
    ):
        descriptor = _descriptor(factor_id)
        stock = {
            item.dataset_id: item
            for item in descriptor.input_requirements_for(AssetLane.STOCK)
        }
        etf = {
            item.dataset_id: item
            for item in descriptor.input_requirements_for(AssetLane.ETF)
        }
        assert set(stock) >= {"stock_daily", "adj_factor"}
        assert set(etf) >= {"etf_daily", "fund_adj"}
        for requirement in (*stock.values(), *etf.values()):
            assert isinstance(requirement.lookback, Lookback)
            assert requirement.pit_requirement is PitRequirement.KNOWN_AT
            assert requirement.required_fields

    liquidity = _descriptor("liquidity")
    stock_liquidity = liquidity.input_requirements_for(AssetLane.STOCK)
    etf_liquidity = liquidity.input_requirements_for(AssetLane.ETF)
    assert tuple(item.dataset_id for item in stock_liquidity) == ("stock_daily",)
    assert tuple(item.dataset_id for item in etf_liquidity) == ("etf_daily",)
    assert stock_liquidity[0].required_fields == ("market.amount",)
    assert etf_liquidity[0].required_fields == ("market.amount",)


def test_liquidity_materialization_uses_certified_amount_capability() -> None:
    liquidity = _descriptor("liquidity")
    assert liquidity.materialized_intermediates == (
        MaterializedIntermediate(
            column_id="ts_mean_daily_amount_20d",
            expression="ts_mean(market.amount, 20)",
            dependencies=("market.amount",),
            lookback=Lookback(21, LookbackUnit.TRADING_DAYS),
        ),
    )
    assert ALL_FACTOR_SPECS["liquidity"].dependencies == ("market.amount",)


def test_derived_factor_requirements_use_recursive_leaf_inputs() -> None:
    for factor_id in ("volatility_factor", "vol_ratio"):
        descriptor = _descriptor(factor_id)
        for lane in descriptor.lanes:
            daily = descriptor.input_requirements_for(lane)[0]
            assert daily.required_fields == ("market.close",)
            assert not any(
                field.startswith("volatility_") for field in daily.required_fields
            )

    quality = _descriptor("quality_roe")
    quality_requirements = {
        item.dataset_id: item
        for item in quality.input_requirements_for(AssetLane.STOCK)
    }
    assert quality_requirements["income_statement"].required_fields == (
        "fundamentals.net_income",
    )
    assert quality_requirements["balance_sheet"].required_fields == (
        "fundamentals.equity",
    )
    assert all(
        requirement.lookback == Lookback(1, LookbackUnit.REPORTING_PERIODS)
        for requirement in quality_requirements.values()
    )


def test_missing_uncertified_factor_fields_fail_closed() -> None:
    context = AvailabilityContext(
        lane=AssetLane.STOCK,
        certified_datasets=frozenset(
            {
                "stock_daily",
                "adj_factor",
                "income_statement",
                "balance_sheet",
                "valuation_metrics",
                "industry_mapping",
            }
        ),
        certified_history={
            dataset_id: CertifiedHistoryCoverage(500, 8)
            for dataset_id in (
                "stock_daily",
                "adj_factor",
                "income_statement",
                "balance_sheet",
                "valuation_metrics",
                "industry_mapping",
            )
        },
        certified_fields={
            "stock_daily": frozenset({"market.close"}),
            "adj_factor": frozenset({"market.adj_factor"}),
            "income_statement": frozenset({"fundamentals.revenue"}),
            "balance_sheet": frozenset(),
            "valuation_metrics": frozenset({"market_cap"}),
            "industry_mapping": frozenset({"industry_id"}),
        },
        certified_pit={
            "stock_daily": PitRequirement.KNOWN_AT,
            "adj_factor": PitRequirement.KNOWN_AT,
            "income_statement": PitRequirement.ANNOUNCEMENT_KNOWN_AT,
            "balance_sheet": PitRequirement.ANNOUNCEMENT_KNOWN_AT,
            "valuation_metrics": PitRequirement.KNOWN_AT,
            "industry_mapping": PitRequirement.KNOWN_AT,
        },
    )

    ep = assess_core_factor_input_availability(_descriptor("ep_ttm"), context)
    assert ep.certified_inputs_available is False
    assert ep.reason is AvailabilityReason.UNCERTIFIED_INPUT_FIELD
    assert set(ep.missing_fields) == {
        "fundamentals.net_income_ttm",
        "fundamentals.total_shares",
    }

    size = assess_core_factor_input_availability(
        _descriptor("log_free_float_cap"), context
    )
    assert size.certified_inputs_available is False
    assert size.reason is AvailabilityReason.UNCERTIFIED_INPUT_FIELD
    assert size.missing_fields == ("fundamentals.free_float_shares",)


def test_preprocessing_inputs_are_explicit_and_fail_closed() -> None:
    preprocessing = R3_CORE_FACTOR_CATALOG.preprocessing
    industry = preprocessing.industry_requirements_for(AssetLane.STOCK)
    size = preprocessing.size_requirements_for(AssetLane.STOCK)
    assert tuple(item.dataset_id for item in industry) == ("industry_mapping",)
    assert industry[0].required_fields == ("industry_id",)
    assert tuple(item.dataset_id for item in size) == ("valuation_metrics",)
    assert size[0].required_fields == ("market_cap",)

    context = AvailabilityContext(
        lane=AssetLane.STOCK,
        certified_datasets=frozenset({"stock_daily", "adj_factor"}),
        certified_history={
            "stock_daily": CertifiedHistoryCoverage(20, 0),
            "adj_factor": CertifiedHistoryCoverage(20, 0),
        },
        certified_fields={
            "stock_daily": frozenset({"market.close"}),
            "adj_factor": frozenset({"market.adj_factor"}),
        },
        certified_pit={
            "stock_daily": PitRequirement.KNOWN_AT,
            "adj_factor": PitRequirement.KNOWN_AT,
        },
    )
    unavailable = assess_core_factor_input_availability(
        _descriptor("momentum_1m"), context
    )
    assert unavailable.reason is AvailabilityReason.PREPROCESSING_INPUT_MISSING
    assert unavailable.dataset_ids == ("industry_mapping", "valuation_metrics")


def test_size_factor_skips_only_size_neutralization_requirement() -> None:
    context = AvailabilityContext(
        lane=AssetLane.STOCK,
        certified_datasets=frozenset(
            {"stock_daily", "valuation_metrics", "industry_mapping"}
        ),
        certified_history={
            dataset_id: CertifiedHistoryCoverage(20, 4)
            for dataset_id in (
                "stock_daily",
                "valuation_metrics",
                "industry_mapping",
            )
        },
        certified_fields={
            "stock_daily": frozenset({"market.close"}),
            "valuation_metrics": frozenset({"fundamentals.free_float_shares"}),
            "industry_mapping": frozenset({"industry_id"}),
        },
        certified_pit={
            "stock_daily": PitRequirement.KNOWN_AT,
            "valuation_metrics": PitRequirement.KNOWN_AT,
            "industry_mapping": PitRequirement.KNOWN_AT,
        },
    )
    result = assess_core_factor_input_availability(
        _descriptor("log_free_float_cap"), context
    )
    assert result.certified_inputs_available is True


def test_relative_strength_requires_concrete_certified_benchmark_evidence() -> None:
    assert hasattr(core_daily, "CertifiedBenchmarkEvidence")
    evidence_type = core_daily.CertifiedBenchmarkEvidence
    benchmark = evidence_type(
        benchmark_id="000300.SH",
        dataset_id="index_daily",
        certified_fields=frozenset({"benchmark.close"}),
        certified_history=CertifiedHistoryCoverage(60, 0),
        certified_pit=PitRequirement.KNOWN_AT,
    )
    context = AvailabilityContext(
        lane=AssetLane.STOCK,
        certified_datasets=frozenset(
            {
                "stock_daily",
                "adj_factor",
                "industry_mapping",
                "valuation_metrics",
            }
        ),
        certified_history={
            dataset_id: CertifiedHistoryCoverage(60, 0)
            for dataset_id in (
                "stock_daily",
                "adj_factor",
                "industry_mapping",
                "valuation_metrics",
            )
        },
        certified_fields={
            "stock_daily": frozenset({"market.close"}),
            "adj_factor": frozenset({"market.adj_factor"}),
            "industry_mapping": frozenset({"industry_id"}),
            "valuation_metrics": frozenset({"market_cap"}),
        },
        benchmark_id="000300.SH",
        certified_benchmarks={"000300.SH": benchmark},
        certified_pit={
            "stock_daily": PitRequirement.KNOWN_AT,
            "adj_factor": PitRequirement.KNOWN_AT,
            "industry_mapping": PitRequirement.KNOWN_AT,
            "valuation_metrics": PitRequirement.KNOWN_AT,
        },
    )
    assert assess_core_factor_input_availability(
        _descriptor("relative_strength_60d"), context
    ).certified_inputs_available

    missing = replace(context, certified_benchmarks={})
    unavailable = assess_core_factor_input_availability(
        _descriptor("relative_strength_60d"), missing
    )
    assert unavailable.reason is AvailabilityReason.BENCHMARK_UNCERTIFIED

    short = replace(
        context,
        certified_benchmarks={
            "000300.SH": replace(
                benchmark,
                certified_history=CertifiedHistoryCoverage(59, 0),
            )
        },
    )
    assert (
        assess_core_factor_input_availability(
            _descriptor("relative_strength_60d"), short
        ).reason
        is AvailabilityReason.INSUFFICIENT_HISTORY
    )


def test_catalog_hash_and_guard_bind_actual_factor_spec(monkeypatch) -> None:
    descriptor = _descriptor("momentum_1m")
    assert descriptor.factor_spec.expression == "ts_pct_change(market.close, 20)"
    assert descriptor.factor_spec.dependencies == ("market.close",)
    assert descriptor.factor_spec.computation_type == "expression"
    assert descriptor.factor_spec.compiled_lookback == 20

    altered = replace(
        ALL_FACTOR_SPECS["momentum_1m"],
        expression="ts_pct_change(market.close, 10)",
    )
    monkeypatch.setitem(ALL_FACTOR_SPECS, "momentum_1m", altered)
    with pytest.raises(ValueError, match="factor spec contract drifted"):
        validate_r3_core_factor_catalog(R3_CORE_FACTOR_CATALOG)

    altered_contract = replace(
        descriptor.factor_spec,
        expression="ts_pct_change(market.close, 10)",
        compiled_lookback=10,
    )
    altered_catalog = replace(
        R3_CORE_FACTOR_CATALOG,
        descriptors=(
            replace(descriptor, factor_spec=altered_contract),
            *R3_CORE_FACTOR_CATALOG.descriptors[1:],
        ),
    )
    assert altered_catalog.payload_hash != R3_CORE_FACTOR_CATALOG.payload_hash


def test_catalog_guard_binds_transitive_factor_dependency_graph(monkeypatch) -> None:
    upstream = ALL_FACTOR_SPECS["volatility_20"]
    monkeypatch.setitem(
        ALL_FACTOR_SPECS,
        "volatility_20",
        replace(upstream, expression="ts_std(returns_1, 10)"),
    )
    with pytest.raises(ValueError, match="factor spec contract drifted"):
        validate_r3_core_factor_catalog(R3_CORE_FACTOR_CATALOG)

    volatility = _descriptor("volatility_factor")
    assert volatility.factor_spec.leaf_dependencies == ("market.close",)
    assert volatility.factor_spec.dependency_graph_hash


def test_catalog_hash_is_a_frozen_external_literal() -> None:
    assert R3_CORE_FACTOR_CATALOG.payload_hash == (
        "ec79390c84b1bcc2234ffc24bcb50c36cccf38b28492e6052b9a924e0f5e67f3"
    )


@pytest.mark.parametrize("value", [True, False, 1.5, "1"])
def test_lookback_rejects_bool_and_non_int_values(value: object) -> None:
    with pytest.raises(ValueError, match="positive int"):
        Lookback(cast(int, value), LookbackUnit.TRADING_DAYS)


def test_invalid_enum_values_raise_safe_value_errors() -> None:
    with pytest.raises(ValueError, match="lookback unit"):
        Lookback(1, cast(LookbackUnit, "days"))
    with pytest.raises(ValueError, match="asset lane"):
        replace(
            _descriptor("momentum_1m").dataset_requirements[0],
            lane=cast(AssetLane, "stock"),
        )


def test_availability_context_copies_sets_and_rejects_invalid_text() -> None:
    datasets = {"stock_daily"}
    pit = {"stock_daily": PitRequirement.KNOWN_AT}
    fields = {"stock_daily": {"market.close"}}
    context = AvailabilityContext(
        lane=AssetLane.STOCK,
        certified_datasets=cast(frozenset[str], datasets),
        certified_history={
            "stock_daily": CertifiedHistoryCoverage(20, 0),
        },
        certified_fields=cast(dict[str, frozenset[str]], fields),
        certified_pit=pit,
    )
    datasets.add("adj_factor")
    pit.clear()
    fields["stock_daily"].add("market.amount")
    assert context.certified_datasets == frozenset({"stock_daily"})
    assert context.certified_pit == {"stock_daily": PitRequirement.KNOWN_AT}
    assert context.certified_fields["stock_daily"] == frozenset({"market.close"})

    with pytest.raises(ValueError, match="UTF-8"):
        replace(context, benchmark_id="\ud800")


def test_semantic_requirement_sets_have_canonical_hash_order() -> None:
    descriptor = _descriptor("momentum_1m")
    reversed_requirements = tuple(
        replace(lane, requirements=tuple(reversed(lane.requirements)))
        for lane in descriptor.dataset_requirements
    )
    reordered = replace(descriptor, dataset_requirements=reversed_requirements)
    reordered_catalog = replace(
        R3_CORE_FACTOR_CATALOG,
        descriptors=(reordered, *R3_CORE_FACTOR_CATALOG.descriptors[1:]),
    )
    assert reordered_catalog.payload_hash == R3_CORE_FACTOR_CATALOG.payload_hash
