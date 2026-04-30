"""
Input data preparation for derived materialization.

Provides the ``InputContext`` parameter object, the ``DerivedInputProvider``
protocol (and two built-in implementations), and the ``prepare_input_frame``
helper that validates dependency columns against an input frame.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol, cast

import polars as pl
from ditto_data.models.derived import DerivedInvalidationRecord, DerivedSpecRecord
from ditto_features.materialization import (
    DerivedExecutionPlan,
    DerivedMaterializationRequest,
)
from ditto_kernel.market import CalendarId, GrainId, TimeSpec
from ditto_kernel.strategy import (
    DerivedRole,
    DerivedSpec,
    ExecutionPolicy,
    MaterializationProfile,
)

from ditto_application.exceptions import AppError

__all__ = [
    "DerivedInputProvider",
    "InMemoryDerivedInputProvider",
    "InputContext",
    "MissingDependencyError",
    "UnavailableDerivedInputProvider",
    "earliest_pending_start",
    "hydrate_spec",
    "prepare_input_frame",
]


# ---------------------------------------------------------------------------
# InputContext & DerivedInputProvider
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class InputContext:
    """Encapsulates all parameters needed for input loading."""

    spec: DerivedSpec
    request: DerivedMaterializationRequest
    plan: DerivedExecutionPlan
    dependencies: tuple[str, ...]


class DerivedInputProvider(Protocol):
    """Input seam used by the materialization orchestrator."""

    def load_input(self, context: InputContext) -> pl.DataFrame:
        """Load the raw input frame for one derived request."""
        ...


class InMemoryDerivedInputProvider:
    """Test input provider backed by an in-memory frame mapping."""

    def __init__(self, frames: dict[str, pl.DataFrame]) -> None:
        self._frames = frames

    def load_input(self, context: InputContext) -> pl.DataFrame:
        """Load one in-memory input frame."""
        frame = self._frames.get(context.spec.id)
        if frame is None:
            raise KeyError(f"missing input frame for derived_id={context.spec.id}")
        return frame


class UnavailableDerivedInputProvider:
    """Runtime placeholder until real source loading is wired."""

    def load_input(self, context: InputContext) -> pl.DataFrame:
        """Raise until a runtime source loader is wired."""
        raise NotImplementedError(
            f"Phase 3 input backend not wired for derived_id={context.spec.id}"
        )


# ---------------------------------------------------------------------------
# MissingDependencyError
# ---------------------------------------------------------------------------


class MissingDependencyError(AppError):
    """Raised when required dependency columns are missing from input data."""

    def __init__(self, missing: list[str], available: list[str]) -> None:
        self.missing = missing
        self.available = available
        super().__init__(
            f"Missing required dependency columns: {missing}. "
            + f"Available columns: {available}"
        )


# ---------------------------------------------------------------------------
# Spec hydration
# ---------------------------------------------------------------------------


def hydrate_spec(record: DerivedSpecRecord) -> DerivedSpec:
    """Reconstruct a DerivedSpec from its persisted record."""
    payload = record.spec_json
    return DerivedSpec(
        id=str(payload["id"]),
        version=_require_int_payload(payload, "version"),
        role=DerivedRole(str(payload["role"])),
        materialization_profile=_materialization_profile(
            payload["materialization_profile"]
        ),
        expression=str(payload["expression"]),
        entity_keys=tuple(
            cast(list[str], payload.get("entity_keys", ["instrument_id"]))
        ),
        grain=cast(GrainId, str(payload.get("grain", "1d"))),
        time_keys=None
        if payload.get("time_keys") is None
        else tuple(cast(list[str], payload["time_keys"])),
        calendar=cast(CalendarId, str(payload.get("calendar", "cn_stock"))),
        description=None
        if payload.get("description") is None
        else str(payload["description"]),
        time_spec=_time_spec(payload.get("time_spec")),
        operator_versions=dict(
            cast(dict[str, str], payload.get("operator_versions", {}))
        ),
        universe_id=None
        if payload.get("universe_id") is None
        else str(payload["universe_id"]),
        execution_policy=_execution_policy(payload.get("execution_policy")),
    )


def _materialization_profile(value: object) -> MaterializationProfile:
    return MaterializationProfile(str(value))


def _time_spec(raw: object) -> TimeSpec | None:
    if raw is None:
        return None
    d = cast(dict[str, Any], raw)
    return TimeSpec(
        event_time_key=str(d["event_time_key"]),
        availability_time_key=str(d["availability_time_key"])
        if d.get("availability_time_key")
        else None,
    )


def _execution_policy(raw: object) -> ExecutionPolicy:
    if raw is None:
        return ExecutionPolicy()
    d = cast(dict[str, Any], raw)
    return ExecutionPolicy(
        pit_required=bool(d.get("pit_required", True)),
        normalization_preset=str(d.get("normalization_preset", "default")),
        adj_type=str(d.get("adj_type", "none")),
    )


def _require_int_payload(payload: Mapping[str, object], key: str) -> int:
    value = payload[key]
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{key} must be an int")
    return value


# ---------------------------------------------------------------------------
# Invalidation helpers
# ---------------------------------------------------------------------------


def earliest_pending_start(
    invalidations: Iterable[DerivedInvalidationRecord],
    derived_id: str,
    version: int,
) -> str | None:
    """Return the earliest affected_start among pending invalidations."""
    starts = [
        invalidation.affected_start
        for invalidation in invalidations
        if invalidation.derived_id == derived_id and invalidation.version == version
    ]
    if not starts:
        return None
    return min(starts)


# ---------------------------------------------------------------------------
# Input frame preparation
# ---------------------------------------------------------------------------


def prepare_input_frame(
    *,
    frame: pl.DataFrame,
    spec: DerivedSpec,
    dependencies: tuple[str, ...],
) -> pl.DataFrame:
    """Prepare input data frame, validating all dependencies exist."""
    sort_columns = [*spec.entity_keys, *spec.effective_time_keys]
    prepared = frame.sort(sort_columns)

    missing: list[str] = []
    for dependency in dependencies:
        if dependency not in prepared.columns:
            input_col = _dependency_input_column(dependency)
            if input_col not in prepared.columns:
                missing.append(dependency)

    if missing:
        raise MissingDependencyError(
            missing=missing,
            available=list(prepared.columns),
        )

    return prepared


def _dependency_input_column(dependency: str) -> str:
    if dependency.startswith("market."):
        return dependency.removeprefix("market.")
    return dependency
