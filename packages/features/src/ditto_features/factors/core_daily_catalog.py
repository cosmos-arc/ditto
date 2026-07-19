"""Frozen R3 daily factor catalog definitions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from types import MappingProxyType

from ditto_features.factors.core_daily_contracts import (
    AssetLane,
    CoreFactorCatalog,
    CoreFactorDescriptor,
    CoreFactorSpecContract,
    DatasetInputRequirement,
    LaneDatasetRequirement,
    Lookback,
    LookbackUnit,
    MaterializedIntermediate,
    MissingValuePolicy,
    PitRequirement,
    PreprocessingContract,
    PreprocessingStep,
    StandardizationMethod,
    WinsorizationMethod,
)
from ditto_features.factors.factor_registry import ALL_FACTOR_SPECS
from ditto_features.factors.spec import FactorSpec

__all__ = ["R3_CORE_FACTOR_CATALOG"]

_MARKET_LANES = frozenset({AssetLane.STOCK, AssetLane.ETF})
_STOCK_LANE = frozenset({AssetLane.STOCK})


def _input_requirement(
    dataset_id: str,
    fields: tuple[str, ...],
    value: int,
    unit: LookbackUnit,
    pit: PitRequirement,
) -> DatasetInputRequirement:
    return DatasetInputRequirement(
        dataset_id=dataset_id,
        required_fields=fields,
        lookback=Lookback(value, unit),
        pit_requirement=pit,
    )


_INDUSTRY_REQUIREMENT = _input_requirement(
    "industry_mapping",
    ("industry_id",),
    1,
    LookbackUnit.TRADING_DAYS,
    PitRequirement.KNOWN_AT,
)
_SIZE_REQUIREMENT = _input_requirement(
    "valuation_metrics",
    ("market_cap",),
    1,
    LookbackUnit.TRADING_DAYS,
    PitRequirement.KNOWN_AT,
)
_PREPROCESSING = PreprocessingContract(
    steps=(
        PreprocessingStep.PIT_ALIGNMENT,
        PreprocessingStep.COVERAGE_VALIDATION,
        PreprocessingStep.MISSING_VALUE_POLICY,
        PreprocessingStep.WINSORIZATION,
        PreprocessingStep.NEUTRALIZATION,
        PreprocessingStep.STANDARDIZATION,
        PreprocessingStep.WEIGHTED_SCORING,
    ),
    missing_value_policy=MissingValuePolicy.DROP,
    winsorization=WinsorizationMethod.MAD_3,
    standardization=StandardizationMethod.ZSCORE,
    applicable_lanes=_MARKET_LANES,
    industry_neutralization_lanes=_STOCK_LANE,
    size_neutralization_lanes=_STOCK_LANE,
    industry_input_requirements=(
        LaneDatasetRequirement(AssetLane.STOCK, (_INDUSTRY_REQUIREMENT,)),
    ),
    size_input_requirements=(
        LaneDatasetRequirement(AssetLane.STOCK, (_SIZE_REQUIREMENT,)),
    ),
)

_CORE_FACTOR_IDS = (
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
_CORE_FACTOR_SPECS: Mapping[str, FactorSpec] = MappingProxyType(
    {factor_id: ALL_FACTOR_SPECS[factor_id] for factor_id in _CORE_FACTOR_IDS}
)
_FACTOR_DEPENDENCY_REGISTRY: Mapping[str, FactorSpec] = MappingProxyType(
    ALL_FACTOR_SPECS
)


def _market_descriptor(
    factor_id: str,
    lookback: int,
    *,
    benchmark_required: bool = False,
    adjusted_prices: bool = True,
    market_fields: tuple[str, ...] | None = None,
    materialized_intermediates: tuple[MaterializedIntermediate, ...] = (),
    production_expression: str | None = None,
) -> CoreFactorDescriptor:
    spec = _CORE_FACTOR_SPECS[factor_id]
    spec_contract = CoreFactorSpecContract.from_spec(
        spec,
        _FACTOR_DEPENDENCY_REGISTRY,
    )
    effective_history = max(lookback, spec_contract.effective_lookback)
    fields = market_fields or tuple(
        dependency
        for dependency in spec_contract.leaf_dependencies
        if dependency != "benchmark.close"
    )

    def lane_requirements(
        lane: AssetLane,
        market_dataset: str,
        adjustment_dataset: str,
    ) -> LaneDatasetRequirement:
        requirements = [
            _input_requirement(
                market_dataset,
                fields,
                effective_history,
                LookbackUnit.TRADING_DAYS,
                PitRequirement.KNOWN_AT,
            )
        ]
        if adjusted_prices:
            requirements.append(
                _input_requirement(
                    adjustment_dataset,
                    ("market.adj_factor",),
                    effective_history,
                    LookbackUnit.TRADING_DAYS,
                    PitRequirement.KNOWN_AT,
                )
            )
        return LaneDatasetRequirement(lane, tuple(requirements))

    benchmark_requirement = (
        _input_requirement(
            "index_daily",
            ("benchmark.close",),
            effective_history,
            LookbackUnit.TRADING_DAYS,
            PitRequirement.KNOWN_AT,
        )
        if benchmark_required
        else None
    )
    return CoreFactorDescriptor(
        factor_id=factor_id,
        lanes=_MARKET_LANES,
        dataset_requirements=(
            lane_requirements(AssetLane.STOCK, "stock_daily", "adj_factor"),
            lane_requirements(AssetLane.ETF, "etf_daily", "fund_adj"),
        ),
        lookback=Lookback(lookback, LookbackUnit.TRADING_DAYS),
        pit_requirement=PitRequirement.KNOWN_AT,
        factor_spec=spec_contract,
        benchmark_required=benchmark_required,
        benchmark_requirement=benchmark_requirement,
        materialized_intermediates=tuple(
            replace(
                intermediate,
                lookback=Lookback(
                    max(intermediate.lookback.value, effective_history),
                    intermediate.lookback.unit,
                ),
            )
            for intermediate in materialized_intermediates
        ),
        production_expression=production_expression,
    )


def _stock_descriptor(
    factor_id: str,
    requirements: tuple[DatasetInputRequirement, ...],
    lookback: Lookback,
    *,
    pit_requirement: PitRequirement = PitRequirement.ANNOUNCEMENT_KNOWN_AT,
    neutralize_size: bool = True,
) -> CoreFactorDescriptor:
    return CoreFactorDescriptor(
        factor_id=factor_id,
        lanes=_STOCK_LANE,
        dataset_requirements=(LaneDatasetRequirement(AssetLane.STOCK, requirements),),
        lookback=lookback,
        pit_requirement=pit_requirement,
        factor_spec=CoreFactorSpecContract.from_spec(
            _CORE_FACTOR_SPECS[factor_id],
            _FACTOR_DEPENDENCY_REGISTRY,
        ),
        neutralize_size=neutralize_size,
    )


def _stock_input(
    dataset_id: str,
    fields: tuple[str, ...],
    value: int,
    unit: LookbackUnit,
    pit: PitRequirement,
) -> DatasetInputRequirement:
    return _input_requirement(dataset_id, fields, value, unit, pit)


R3_CORE_FACTOR_CATALOG = CoreFactorCatalog(
    descriptors=(
        _market_descriptor("momentum_1m", 20),
        _market_descriptor("momentum_3m", 60),
        _market_descriptor("reversal_1w", 5),
        _market_descriptor("volatility_factor", 20),
        _market_descriptor("vol_ratio", 60),
        _market_descriptor(
            "liquidity",
            20,
            adjusted_prices=False,
            market_fields=("market.amount",),
            materialized_intermediates=(
                MaterializedIntermediate(
                    column_id="ts_mean_daily_amount_20d",
                    expression="ts_mean(market.amount, 20)",
                    dependencies=("market.amount",),
                    lookback=Lookback(20, LookbackUnit.TRADING_DAYS),
                ),
            ),
            production_expression="cs_rank(ts_mean_daily_amount_20d)",
        ),
        _market_descriptor("relative_strength_60d", 60, benchmark_required=True),
        _stock_descriptor(
            "ep_ttm",
            (
                _stock_input(
                    "stock_daily",
                    ("market.close",),
                    1,
                    LookbackUnit.TRADING_DAYS,
                    PitRequirement.KNOWN_AT,
                ),
                _stock_input(
                    "income_statement",
                    ("fundamentals.net_income_ttm",),
                    4,
                    LookbackUnit.REPORTING_PERIODS,
                    PitRequirement.ANNOUNCEMENT_KNOWN_AT,
                ),
                _stock_input(
                    "balance_sheet",
                    ("fundamentals.total_shares",),
                    1,
                    LookbackUnit.REPORTING_PERIODS,
                    PitRequirement.ANNOUNCEMENT_KNOWN_AT,
                ),
            ),
            Lookback(4, LookbackUnit.REPORTING_PERIODS),
        ),
        _stock_descriptor(
            "bp_ratio",
            (
                _stock_input(
                    "stock_daily",
                    ("market.close",),
                    1,
                    LookbackUnit.TRADING_DAYS,
                    PitRequirement.KNOWN_AT,
                ),
                _stock_input(
                    "balance_sheet",
                    ("fundamentals.total_equity", "fundamentals.total_shares"),
                    1,
                    LookbackUnit.REPORTING_PERIODS,
                    PitRequirement.ANNOUNCEMENT_KNOWN_AT,
                ),
            ),
            Lookback(1, LookbackUnit.REPORTING_PERIODS),
        ),
        _stock_descriptor(
            "quality_roe",
            (
                _stock_input(
                    "balance_sheet",
                    ("fundamentals.equity",),
                    1,
                    LookbackUnit.REPORTING_PERIODS,
                    PitRequirement.ANNOUNCEMENT_KNOWN_AT,
                ),
                _stock_input(
                    "income_statement",
                    ("fundamentals.net_income",),
                    1,
                    LookbackUnit.REPORTING_PERIODS,
                    PitRequirement.ANNOUNCEMENT_KNOWN_AT,
                ),
            ),
            Lookback(1, LookbackUnit.REPORTING_PERIODS),
        ),
        _stock_descriptor(
            "revenue_growth",
            (
                _stock_input(
                    "income_statement",
                    ("fundamentals.revenue",),
                    4,
                    LookbackUnit.REPORTING_PERIODS,
                    PitRequirement.ANNOUNCEMENT_KNOWN_AT,
                ),
            ),
            Lookback(4, LookbackUnit.REPORTING_PERIODS),
        ),
        _stock_descriptor(
            "log_free_float_cap",
            (
                _stock_input(
                    "stock_daily",
                    ("market.close",),
                    1,
                    LookbackUnit.TRADING_DAYS,
                    PitRequirement.KNOWN_AT,
                ),
                _stock_input(
                    "valuation_metrics",
                    ("fundamentals.free_float_shares",),
                    1,
                    LookbackUnit.TRADING_DAYS,
                    PitRequirement.KNOWN_AT,
                ),
            ),
            Lookback(1, LookbackUnit.TRADING_DAYS),
            pit_requirement=PitRequirement.KNOWN_AT,
            neutralize_size=False,
        ),
    ),
    preprocessing=_PREPROCESSING,
)
