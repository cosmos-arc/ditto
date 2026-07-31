"""Stable factor-column names and declarative signal-spec construction."""

from __future__ import annotations

from ditto_features.derived_types import (
    DerivedRole,
    DerivedSpec,
    MaterializationProfile,
)
from ditto_kernel.strategy import ExecutionPolicy

__all__ = [
    "build_signal_spec",
    "factor_normalized_column",
    "factor_value_column",
]


def factor_value_column(index: int) -> str:
    """Return the stable materialized value column for one compiled factor."""
    return f"factor_{index}"


def factor_normalized_column(index: int) -> str:
    """Return the stable rank-normalized column for one compiled factor."""
    return f"rank_{factor_value_column(index)}"


def build_signal_spec(
    expr_str: str,
    index: int,
    *,
    derived_id: str | None = None,
    version: int = 1,
) -> DerivedSpec:
    """
    Build a signal DerivedSpec from a declarative factor expression.

    The stable defaults remain role=SIGNAL, profile=SERIES,
    entity_keys=("instrument_id",), grain="1d", and calendar="cn_stock".
    """
    return DerivedSpec(
        id=derived_id if derived_id is not None else f"signal_{index}",
        version=version,
        role=DerivedRole.SIGNAL,
        materialization_profile=MaterializationProfile.SERIES,
        expression=expr_str,
        entity_keys=("instrument_id",),
        grain="1d",
        calendar="cn_stock",
        execution_policy=ExecutionPolicy(),
    )
