"""Canonical JSON preimages and SHA-256 identities for selection contracts."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Protocol, cast

import orjson

__all__ = [
    "canonical_input_hash",
    "canonical_run_hash",
    "canonical_run_payload",
    "canonical_spec_hash",
]

_SCHEMA_VERSION = 1


class _StringValue(Protocol):
    @property
    def value(self) -> str: ...


class _FactorWeight(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def weight(self) -> float: ...


class _SelectionSpec(Protocol):
    @property
    def asset_kind(self) -> _StringValue: ...

    @property
    def excluded_limit_states(self) -> tuple[_StringValue, ...]: ...

    @property
    def factor_weights(self) -> tuple[_FactorWeight, ...]: ...

    @property
    def min_average_turnover(self) -> float: ...

    @property
    def min_listing_days(self) -> int: ...

    @property
    def spec_id(self) -> str: ...

    @property
    def spec_version(self) -> str: ...

    @property
    def top_k(self) -> int: ...


class _EtfSelectionSpec(_SelectionSpec, Protocol):
    @property
    def max_tracking_error(self) -> float | None: ...


class _FactorValue(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def value(self) -> float: ...


class _InstrumentInput(Protocol):
    @property
    def average_turnover(self) -> float | None: ...

    @property
    def declared_missing_inputs(self) -> tuple[str, ...]: ...

    @property
    def factor_values(self) -> tuple[_FactorValue, ...]: ...

    @property
    def industry_id(self) -> str | None: ...

    @property
    def instrument_id(self) -> int: ...

    @property
    def instrument_name(self) -> str: ...

    @property
    def is_st(self) -> bool | None: ...

    @property
    def is_suspended(self) -> bool | None: ...

    @property
    def limit_state(self) -> _StringValue | None: ...

    @property
    def listing_days(self) -> int | None: ...

    @property
    def tracking_error(self) -> float | None: ...


class _SelectionInput(Protocol):
    @property
    def as_of(self) -> datetime: ...

    @property
    def industry_rotation_snapshot_id(self) -> str | None: ...

    @property
    def instruments(self) -> tuple[_InstrumentInput, ...]: ...

    @property
    def knowledge_cutoff(self) -> datetime: ...

    @property
    def publication_cutoff(self) -> datetime: ...

    @property
    def seed(self) -> int: ...

    @property
    def source_snapshot_ids(self) -> tuple[str, ...]: ...

    @property
    def spec(self) -> _SelectionSpec: ...

    @property
    def universe_snapshot_id(self) -> str: ...


class _FactorContribution(Protocol):
    @property
    def contribution(self) -> float: ...

    @property
    def factor_name(self) -> str: ...

    @property
    def value(self) -> float: ...

    @property
    def weight(self) -> float: ...


class _Candidate(Protocol):
    @property
    def factor_contributions(self) -> tuple[_FactorContribution, ...]: ...

    @property
    def industry_id(self) -> str | None: ...

    @property
    def instrument_id(self) -> int: ...

    @property
    def instrument_name(self) -> str: ...

    @property
    def rank(self) -> int: ...

    @property
    def score(self) -> float: ...


class _Exclusion(Protocol):
    @property
    def detail(self) -> str: ...

    @property
    def instrument_id(self) -> int: ...

    @property
    def instrument_name(self) -> str: ...

    @property
    def reason_code(self) -> _StringValue: ...

    @property
    def stage(self) -> str: ...


class _SelectionRun(Protocol):
    @property
    def as_of(self) -> datetime: ...

    @property
    def asset_kind(self) -> _StringValue: ...

    @property
    def candidates(self) -> tuple[_Candidate, ...]: ...

    @property
    def exclusions(self) -> tuple[_Exclusion, ...]: ...

    @property
    def industry_rotation_snapshot_id(self) -> str | None: ...

    @property
    def input_hash(self) -> str: ...

    @property
    def knowledge_cutoff(self) -> datetime: ...

    @property
    def missing_inputs(self) -> tuple[str, ...]: ...

    @property
    def publication_cutoff(self) -> datetime: ...

    @property
    def seed(self) -> int: ...

    @property
    def source_snapshot_ids(self) -> tuple[str, ...]: ...

    @property
    def spec_hash(self) -> str: ...

    @property
    def spec_id(self) -> str: ...

    @property
    def spec_version(self) -> str: ...

    @property
    def status(self) -> _StringValue: ...

    @property
    def universe_snapshot_id(self) -> str: ...


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _spec_payload(value: _SelectionSpec) -> dict[str, object]:
    payload: dict[str, object] = {
        "asset_kind": value.asset_kind.value,
        "excluded_limit_states": [item.value for item in value.excluded_limit_states],
        "factor_weights": [
            {"name": item.name, "weight": item.weight} for item in value.factor_weights
        ],
        "min_average_turnover": value.min_average_turnover,
        "min_listing_days": value.min_listing_days,
        "schema_version": _SCHEMA_VERSION,
        "spec_id": value.spec_id,
        "spec_version": value.spec_version,
        "top_k": value.top_k,
    }
    if value.asset_kind.value == "etf":
        payload["max_tracking_error"] = cast(
            "_EtfSelectionSpec", value
        ).max_tracking_error
    return payload


def _canonical_hash(payload: object) -> str:
    encoded = orjson.dumps(payload, option=orjson.OPT_SORT_KEYS)
    return hashlib.sha256(encoded).hexdigest()


def canonical_spec_hash(value: _SelectionSpec) -> str:
    """Hash the exact stock- or ETF-specific selection policy."""
    return _canonical_hash(_spec_payload(value))


def _instrument_payload(value: _InstrumentInput) -> dict[str, object]:
    return {
        "average_turnover": value.average_turnover,
        "declared_missing_inputs": list(value.declared_missing_inputs),
        "factor_values": [
            {"name": item.name, "value": item.value} for item in value.factor_values
        ],
        "industry_id": value.industry_id,
        "instrument_id": value.instrument_id,
        "instrument_name": value.instrument_name,
        "is_st": value.is_st,
        "is_suspended": value.is_suspended,
        "limit_state": value.limit_state.value if value.limit_state else None,
        "listing_days": value.listing_days,
        "tracking_error": value.tracking_error,
    }


def _input_payload(value: _SelectionInput) -> dict[str, object]:
    return {
        "as_of": _timestamp(value.as_of),
        "industry_rotation_snapshot_id": value.industry_rotation_snapshot_id,
        "instruments": [_instrument_payload(item) for item in value.instruments],
        "knowledge_cutoff": _timestamp(value.knowledge_cutoff),
        "publication_cutoff": _timestamp(value.publication_cutoff),
        "schema_version": _SCHEMA_VERSION,
        "seed": value.seed,
        "source_snapshot_ids": list(value.source_snapshot_ids),
        "spec": _spec_payload(value.spec),
        "universe_snapshot_id": value.universe_snapshot_id,
    }


def canonical_input_hash(value: _SelectionInput) -> str:
    """Hash PIT, source, spec, seed, universe, and instrument facts."""
    return _canonical_hash(_input_payload(value))


def _candidate_payload(value: _Candidate) -> dict[str, object]:
    return {
        "factor_contributions": [
            {
                "contribution": item.contribution,
                "factor_name": item.factor_name,
                "value": item.value,
                "weight": item.weight,
            }
            for item in value.factor_contributions
        ],
        "industry_id": value.industry_id,
        "instrument_id": value.instrument_id,
        "instrument_name": value.instrument_name,
        "rank": value.rank,
        "score": value.score,
    }


def _exclusion_payload(value: _Exclusion) -> dict[str, object]:
    return {
        "detail": value.detail,
        "instrument_id": value.instrument_id,
        "instrument_name": value.instrument_name,
        "reason_code": value.reason_code.value,
        "stage": value.stage,
    }


def canonical_run_payload(value: _SelectionRun) -> dict[str, object]:
    """Return the canonical persisted payload for one selection run."""
    return {
        "as_of": _timestamp(value.as_of),
        "asset_kind": value.asset_kind.value,
        "candidates": [_candidate_payload(item) for item in value.candidates],
        "exclusions": [_exclusion_payload(item) for item in value.exclusions],
        "industry_rotation_snapshot_id": value.industry_rotation_snapshot_id,
        "input_hash": value.input_hash,
        "knowledge_cutoff": _timestamp(value.knowledge_cutoff),
        "missing_inputs": list(value.missing_inputs),
        "schema_version": _SCHEMA_VERSION,
        "seed": value.seed,
        "publication_cutoff": _timestamp(value.publication_cutoff),
        "source_snapshot_ids": list(value.source_snapshot_ids),
        "spec_hash": value.spec_hash,
        "spec_id": value.spec_id,
        "spec_version": value.spec_version,
        "status": value.status.value,
        "universe_snapshot_id": value.universe_snapshot_id,
    }


def canonical_run_hash(value: _SelectionRun) -> str:
    """Hash the complete ordered candidates and exclusions of a saved run."""
    return _canonical_hash(canonical_run_payload(value))
