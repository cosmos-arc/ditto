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
        {AssetLane.STOCK: ("stock_daily",), AssetLane.ETF: ("etf_daily",)},
        Lookback(20, LookbackUnit.TRADING_DAYS),
        PitRequirement.KNOWN_AT,
    ),
    "momentum_3m": (
        MARKET_LANES,
        {AssetLane.STOCK: ("stock_daily",), AssetLane.ETF: ("etf_daily",)},
        Lookback(60, LookbackUnit.TRADING_DAYS),
        PitRequirement.KNOWN_AT,
    ),
    "reversal_1w": (
        MARKET_LANES,
        {AssetLane.STOCK: ("stock_daily",), AssetLane.ETF: ("etf_daily",)},
        Lookback(5, LookbackUnit.TRADING_DAYS),
        PitRequirement.KNOWN_AT,
    ),
    "volatility_factor": (
        MARKET_LANES,
        {AssetLane.STOCK: ("stock_daily",), AssetLane.ETF: ("etf_daily",)},
        Lookback(20, LookbackUnit.TRADING_DAYS),
        PitRequirement.KNOWN_AT,
    ),
    "vol_ratio": (
        MARKET_LANES,
        {AssetLane.STOCK: ("stock_daily",), AssetLane.ETF: ("etf_daily",)},
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
            AssetLane.STOCK: ("stock_daily", "index_daily"),
            AssetLane.ETF: ("etf_daily", "index_daily"),
        },
        Lookback(60, LookbackUnit.TRADING_DAYS),
        PitRequirement.KNOWN_AT,
    ),
    "ep_ttm": (
        STOCK_LANE,
        {AssetLane.STOCK: ("stock_daily", "income_statement")},
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
    return AvailabilityContext(
        lane=lane,
        certified_datasets=frozenset(datasets),
        certified_history={
            dataset: CertifiedHistoryCoverage(
                trading_days=history,
                reporting_periods=(
                    history if reporting_history is None else reporting_history
                ),
            )
            for dataset in datasets
        },
        benchmark_id=benchmark_id,
        pit_aligned_datasets=frozenset(datasets),
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
            ("stock_daily",),
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
    context = _context("stock_daily", "income_statement")
    unavailable = assess_core_factor_input_availability(
        descriptor,
        replace(context, pit_aligned_datasets=frozenset()),
    )
    assert unavailable.certified_inputs_available is False
    assert unavailable.reason is AvailabilityReason.PIT_ALIGNMENT_MISSING
    assert not hasattr(context, "current_value_fallback")


def test_market_availability_requires_known_at_alignment() -> None:
    context = replace(
        _context("stock_daily", history=20),
        pit_aligned_datasets=frozenset(),
    )
    unavailable = assess_core_factor_input_availability(
        _descriptor("momentum_1m"),
        context,
    )
    assert unavailable.certified_inputs_available is False
    assert unavailable.reason is AvailabilityReason.PIT_ALIGNMENT_MISSING
    assert unavailable.dataset_ids == ("stock_daily",)


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
        history=500,
        reporting_history=4,
    )
    fundamental = replace(
        fundamental,
        certified_history={
            "stock_daily": CertifiedHistoryCoverage(500, 4),
            "income_statement": CertifiedHistoryCoverage(500, 3),
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
        pit_aligned_datasets=frozenset(history),
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
                _context("stock_daily", "income_statement", history=4),
                pit_aligned_datasets=frozenset({"stock_daily", "income_statement"}),
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
            expression="ts_mean(market.volume * market.close, 20)",
            dependencies=("market.volume", "market.close"),
            lookback=Lookback(20, LookbackUnit.TRADING_DAYS),
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
    assert projection.values["decay"] == [(1, 0.04), (5, 0.02)]
    assert projection.values["quantile_return"] == {1: -0.01, 5: 0.08}
    assert projection.values["turnover"] == 0.2
    assert projection.values["cost_drag"] == pytest.approx(0.02)
    assert projection.values["exposure"] is exposure
    assert "coverage" not in projection.computed_metrics
    assert "missingness" not in projection.computed_metrics
