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
from ditto_features.materialization import (
    DerivedExecutionPlan,
    DerivedMaterializationRequest,
)
from ditto_features.models.derived import DerivedInvalidationRecord, DerivedSpecRecord
from ditto_kernel.market import CalendarId, GrainId, TimeSpec
from ditto_kernel.strategy import (
    DerivedRole,
    DerivedSpec,
    ExecutionPolicy,
    MaterializationProfile,
)

from ditto_application.exceptions import AppProcessError

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
            raise AppProcessError(
                f"missing input frame for derived_id={context.spec.id}"
            )
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


class MissingDependencyError(AppProcessError):
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
        id=str(_require_payload(payload, "id", record.derived_id)),
        version=_require_int_payload(payload, "version", record.derived_id),
        role=_derived_role(
            _require_payload(payload, "role", record.derived_id),
            record.derived_id,
        ),
        materialization_profile=_materialization_profile(
            _require_payload(payload, "materialization_profile", record.derived_id),
            record.derived_id,
        ),
        expression=str(_require_payload(payload, "expression", record.derived_id)),
        entity_keys=tuple(
            cast(list[str], payload.get("entity_keys", ["instrument_id"]))
        ),
        grain=cast(GrainId, str(payload.get("grain", "1d"))),
        time_keys=_optional_str_tuple_payload(payload, "time_keys"),
        calendar=cast(CalendarId, str(payload.get("calendar", "cn_stock"))),
        description=_optional_str_payload(payload, "description"),
        time_spec=_time_spec(payload.get("time_spec"), record.derived_id),
        operator_versions=dict(
            cast(dict[str, str], payload.get("operator_versions", {}))
        ),
        universe_id=_optional_str_payload(payload, "universe_id"),
        execution_policy=_execution_policy(payload.get("execution_policy")),
    )


def _derived_role(value: object, derived_id: str) -> DerivedRole:
    normalized = str(value)
    try:
        return DerivedRole(normalized)
    except ValueError:
        msg = (
            f"malformed derived spec payload field role has invalid value: {normalized}"
        )
        raise AppProcessError(
            msg,
            derived_id=derived_id,
            field="role",
            value=normalized,
        ) from None


def _materialization_profile(value: object, derived_id: str) -> MaterializationProfile:
    normalized = str(value)
    try:
        return MaterializationProfile(normalized)
    except ValueError:
        msg = (
            "malformed derived spec payload field materialization_profile "
            f"has invalid value: {normalized}"
        )
        raise AppProcessError(
            msg,
            derived_id=derived_id,
            field="materialization_profile",
            value=normalized,
        ) from None


def _optional_str_payload(payload: Mapping[str, object], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    return str(value)


def _optional_str_tuple_payload(
    payload: Mapping[str, object], key: str
) -> tuple[str, ...] | None:
    value = payload.get(key)
    if value is None:
        return None
    return tuple(cast(list[str], value))


def _time_spec(raw: object, derived_id: str) -> TimeSpec | None:
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise AppProcessError(
            "malformed derived spec payload field time_spec must be a mapping",
            derived_id=derived_id,
            field="time_spec",
        )
    time_spec = cast(Mapping[str, object], raw)
    event_time_key = time_spec.get("event_time_key")
    if event_time_key is None:
        missing_field = "time_spec.event_time_key"
        raise AppProcessError(
            f"malformed derived spec payload missing required field: {missing_field}",
            derived_id=derived_id,
            field=missing_field,
        )
    availability_time_key = time_spec.get("availability_time_key")
    return TimeSpec(
        event_time_key=str(event_time_key),
        availability_time_key=str(availability_time_key)
        if availability_time_key
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


def _require_payload(
    payload: Mapping[str, object], key: str, derived_id: str
) -> object:
    if key not in payload:
        raise AppProcessError(
            f"malformed derived spec payload missing required field: {key}",
            derived_id=derived_id,
            field=key,
        )
    return payload[key]


def _require_int_payload(
    payload: Mapping[str, object], key: str, derived_id: str
) -> int:
    value = _require_payload(payload, key, derived_id)
    if not isinstance(value, int) or isinstance(value, bool):
        raise AppProcessError(
            f"malformed derived spec payload field {key} must be an int",
            derived_id=derived_id,
            field=key,
            value=value,
        )
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
