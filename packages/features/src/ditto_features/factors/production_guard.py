"""Production safety checks for factor expressions."""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass

from ditto_features.errors import FactorValidationError
from ditto_features.expression.analyzer import analyze_expression
from ditto_features.expression.lexer import tokenize
from ditto_features.expression.parser import ExpressionParser
from ditto_features.factors.core_daily import (
    R3_CORE_FACTOR_CATALOG,
    CoreFactorCatalog,
    CoreFactorDescriptor,
    PitRequirement,
    PreprocessingStep,
)
from ditto_features.factors.factor_specs import ALL_FACTOR_SPECS

__all__ = [
    "R2_STOCK_SEED_FACTOR_CONTRACT",
    "CertifiedSeedFactorContract",
    "UnsafeProductionFactorExpressionError",
    "validate_certified_seed_factor_contract",
    "validate_production_factor_expression",
    "validate_r3_core_factor_catalog",
]

_CROSS_SECTION_OPERATORS = frozenset({"cs_rank", "cs_zscore", "cs_demean"})
_CROSS_SECTION_CALL = re.compile(
    r"\b(?P<operator>cs_rank|cs_zscore|cs_demean)\s*\(",
)
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_TIME_SERIES_CALL = re.compile(r"^ts_[A-Za-z0-9_]*\(")

_R2_STOCK_SEED_FACTOR_IDS = ("quality_roe", "value_pe", "momentum_1m")
_R2_STOCK_SEED_INPUT_DATASET_IDS = (
    "stock_daily",
    "adj_factor",
    "balance_sheet",
    "income_statement",
)
_R2_STOCK_SEED_MAX_LOOKBACK = 20
_R2_CERTIFICATION_PROFILE = "r2-modern-a-share-v1"
_R3_CORE_FACTOR_IDS = R3_CORE_FACTOR_CATALOG.factor_ids
_R3_PREPROCESSING_STEPS = R3_CORE_FACTOR_CATALOG.preprocessing.steps
_R3_CORE_PAYLOAD_HASH = R3_CORE_FACTOR_CATALOG.payload_hash


@dataclass(frozen=True, slots=True)
class CertifiedSeedFactorContract:
    """Frozen R2 input boundary for the designated R1 stock seed factors."""

    factor_ids: tuple[str, ...]
    input_dataset_ids: tuple[str, ...]
    max_lookback: int
    knowledge_date_required: bool
    certification_profile: str

    def __post_init__(self) -> None:
        """Reject malformed or ambiguous seed contracts."""
        for field_name in ("factor_ids", "input_dataset_ids"):
            values = getattr(self, field_name)
            if not values or len(set(values)) != len(values):
                raise ValueError(f"invalid seed factor {field_name}: {values!r}")
        if self.max_lookback < 0:
            raise ValueError("seed factor max_lookback cannot be negative")
        if not self.certification_profile.strip():
            raise ValueError("seed factor certification profile cannot be empty")


R2_STOCK_SEED_FACTOR_CONTRACT = CertifiedSeedFactorContract(
    factor_ids=_R2_STOCK_SEED_FACTOR_IDS,
    input_dataset_ids=_R2_STOCK_SEED_INPUT_DATASET_IDS,
    max_lookback=_R2_STOCK_SEED_MAX_LOOKBACK,
    knowledge_date_required=True,
    certification_profile=_R2_CERTIFICATION_PROFILE,
)


class UnsafeProductionFactorExpressionError(FactorValidationError):
    """Raised when a production factor expression is unsafe to run inline."""


def validate_certified_seed_factor_contract(
    contract: CertifiedSeedFactorContract,
) -> None:
    """Fail closed when the fixed R2 stock-seed boundary has drifted."""
    if contract.factor_ids != _R2_STOCK_SEED_FACTOR_IDS:
        raise ValueError(f"R2 stock seed factor IDs changed: {contract.factor_ids!r}")
    if contract.input_dataset_ids != _R2_STOCK_SEED_INPUT_DATASET_IDS:
        raise ValueError(
            f"R2 stock seed input dataset IDs changed: {contract.input_dataset_ids!r}"
        )
    if contract.max_lookback != _R2_STOCK_SEED_MAX_LOOKBACK:
        raise ValueError(f"R2 stock seed max lookback changed: {contract.max_lookback}")
    if not contract.knowledge_date_required:
        raise ValueError("R2 stock seed requires a strict knowledge date")
    if contract.certification_profile != _R2_CERTIFICATION_PROFILE:
        profile = contract.certification_profile
        raise ValueError(f"R2 stock seed certification profile changed: {profile!r}")
    actual_max_lookback = 0
    for factor_id in contract.factor_ids:
        spec = ALL_FACTOR_SPECS.get(factor_id)
        if spec is None:
            raise ValueError(f"R2 stock seed factor is not registered: {factor_id}")
        validate_production_factor_expression(spec.expression)
        expression = ExpressionParser(
            tokenize(spec.expression),
            spec.expression,
        ).parse()
        actual_max_lookback = max(
            actual_max_lookback,
            analyze_expression(expression).lookback,
        )
    if actual_max_lookback != contract.max_lookback:
        drift = f"{actual_max_lookback} != {contract.max_lookback}"
        raise ValueError(f"R2 stock seed compiled max lookback drifted: {drift}")


def validate_production_factor_expression(
    expression: str,
    *,
    materialized_columns: Iterable[str] = (),
) -> None:
    """
    Reject production expressions that inline time-series ops inside cs ops.

    Cross-sectional operators over inline time-series expressions can silently
    produce nulls in the current codegen path. Production configs must
    materialize the time-series result first and reference that column by name.
    """
    materialized = frozenset(materialized_columns)
    for operator, first_arg in _iter_cross_section_first_args(expression):
        compact_arg = _strip_whitespace(first_arg)
        if _is_time_series_call(compact_arg):
            _raise_unsafe_expression(expression, operator, compact_arg)
        if _is_unmaterialized_time_series_identifier(compact_arg, materialized):
            _raise_unsafe_expression(expression, operator, compact_arg)


def validate_r3_core_factor_catalog(catalog: CoreFactorCatalog) -> None:
    """Fail closed when the governed R3 catalog or production seam drifts."""
    for descriptor in catalog.descriptors:
        _validate_r3_core_descriptor(descriptor)

    if catalog.factor_ids != _R3_CORE_FACTOR_IDS:
        raise ValueError(f"R3 core factor IDs changed: {catalog.factor_ids!r}")
    if catalog.preprocessing.steps != _R3_PREPROCESSING_STEPS:
        raise ValueError("R3 preprocessing order changed")
    if catalog.preprocessing.steps != tuple(PreprocessingStep):
        raise ValueError("R3 preprocessing registry is incomplete")
    if catalog.payload_hash != _R3_CORE_PAYLOAD_HASH:
        raise ValueError("R3 core factor catalog payload changed")


def _validate_r3_core_descriptor(descriptor: CoreFactorDescriptor) -> None:
    spec = ALL_FACTOR_SPECS.get(descriptor.factor_id)
    if spec is None:
        raise ValueError(f"unregistered core factor: {descriptor.factor_id}")
    if spec.id != descriptor.factor_id:
        raise ValueError(f"core factor spec ID drifted: {descriptor.factor_id}")
    if descriptor.pit_requirement is PitRequirement.ANNOUNCEMENT_KNOWN_AT and not any(
        dataset_id in descriptor.required_datasets_for(lane)
        for lane in descriptor.lanes
        for dataset_id in (
            "balance_sheet",
            "income_statement",
            "valuation_metrics",
        )
    ):
        raise ValueError(
            f"PIT core factor has no governed PIT dataset: {descriptor.factor_id}"
        )
    if descriptor.benchmark_required:
        if spec.computation_type != "python" or spec.expression:
            raise ValueError(
                "benchmark-relative core factor must use explicit Python computation: "
                + descriptor.factor_id
            )
        return
    for intermediate in descriptor.materialized_intermediates:
        validate_production_factor_expression(intermediate.expression)
    validate_production_factor_expression(
        descriptor.production_expression or spec.expression,
        materialized_columns=(
            item.column_id for item in descriptor.materialized_intermediates
        ),
    )


def _iter_cross_section_first_args(expression: str) -> Iterator[tuple[str, str]]:
    for match in _CROSS_SECTION_CALL.finditer(expression):
        operator = match.group("operator")
        if operator not in _CROSS_SECTION_OPERATORS:
            continue
        open_paren_index = expression.find("(", match.start())
        if open_paren_index == -1:
            continue
        yield operator, _first_argument(expression, open_paren_index + 1)


def _first_argument(expression: str, start_index: int) -> str:
    depth = 0
    for index in range(start_index, len(expression)):
        char = expression[index]
        if char == "(":
            depth += 1
        elif char == ")":
            if depth == 0:
                return expression[start_index:index]
            depth -= 1
        elif char == "," and depth == 0:
            return expression[start_index:index]
    return expression[start_index:]


def _strip_whitespace(value: str) -> str:
    return "".join(value.split())


def _is_time_series_call(value: str) -> bool:
    return _TIME_SERIES_CALL.match(value) is not None


def _is_unmaterialized_time_series_identifier(
    value: str,
    materialized_columns: frozenset[str],
) -> bool:
    return (
        value.startswith("ts_")
        and _IDENTIFIER.match(value) is not None
        and value not in materialized_columns
    )


def _raise_unsafe_expression(
    expression: str,
    operator: str,
    first_arg: str,
) -> None:
    msg = (
        "production factor expression nests cross-sectional and time-series "
        "operators without materialized intermediates: "
        f"{operator}({first_arg}) in {expression!r}"
    )
    raise UnsafeProductionFactorExpressionError(msg)
