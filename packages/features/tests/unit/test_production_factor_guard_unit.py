"""Production safety guard tests for factor expressions."""

from __future__ import annotations

import pytest
from ditto_features.factors.production_guard import (
    R2_STOCK_SEED_FACTOR_CONTRACT,
    CertifiedSeedFactorContract,
    UnsafeProductionFactorExpressionError,
    validate_certified_seed_factor_contract,
    validate_production_factor_expression,
)


def test_rejects_cross_section_wrapping_inline_time_series_expression() -> None:
    with pytest.raises(
        UnsafeProductionFactorExpressionError,
        match="nests cross-sectional and time-series operators",
    ):
        validate_production_factor_expression(
            "cs_rank(ts_mean(market.close, 20))",
        )


def test_allows_simple_cross_section_expression() -> None:
    validate_production_factor_expression("cs_zscore(roe)")


def test_time_series_intermediate_requires_materialization_marker() -> None:
    with pytest.raises(
        UnsafeProductionFactorExpressionError,
        match="ts_mean_close_20",
    ):
        validate_production_factor_expression("cs_rank(ts_mean_close_20)")

    validate_production_factor_expression(
        "cs_rank(ts_mean_close_20)",
        materialized_columns={"ts_mean_close_20"},
    )


def test_r2_stock_seed_contract_freezes_inputs_and_max_lookback() -> None:
    contract = R2_STOCK_SEED_FACTOR_CONTRACT

    validate_certified_seed_factor_contract(contract)

    assert contract.factor_ids == ("quality_roe", "value_pe", "momentum_1m")
    assert contract.input_dataset_ids == (
        "stock_daily",
        "adj_factor",
        "balance_sheet",
        "income_statement",
    )
    assert contract.max_lookback == 20
    assert contract.knowledge_date_required is True
    assert contract.certification_profile == "r2-modern-a-share-v1"


def test_r2_stock_seed_contract_rejects_incomplete_input_set() -> None:
    invalid = CertifiedSeedFactorContract(
        factor_ids=R2_STOCK_SEED_FACTOR_CONTRACT.factor_ids,
        input_dataset_ids=("stock_daily",),
        max_lookback=20,
        knowledge_date_required=True,
        certification_profile="r2-modern-a-share-v1",
    )

    with pytest.raises(ValueError, match="input dataset"):
        validate_certified_seed_factor_contract(invalid)
