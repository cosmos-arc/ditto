"""Canonical persistence codec for immutable SelectionRun values."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import cast

import orjson
from ditto_kernel.identity import InstrumentId

from ditto_strategy.errors import StrategySpecError
from ditto_strategy.selection.contracts import (
    SelectionAssetKind,
    SelectionCandidate,
    SelectionExclusion,
    SelectionExclusionReason,
    SelectionFactorContribution,
    SelectionRun,
    SelectionRunStatus,
    canonical_run_payload,
)

__all__ = ["decode_selection_run", "encode_selection_run"]


def encode_selection_run(value: SelectionRun) -> bytes:
    """Encode one validated run as recursive key-sorted JSON bytes."""
    return orjson.dumps(canonical_run_payload(value), option=orjson.OPT_SORT_KEYS)


def _mapping(value: object, *, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise StrategySpecError(
            f"persisted selection {field_name} must be an object",
            details={
                "reason": "invalid_persisted_selection_run",
                "field_name": field_name,
            },
        )
    payload = cast("dict[object, object]", value)
    if any(not isinstance(key, str) for key in payload):
        raise StrategySpecError(
            f"persisted selection {field_name} must use string keys",
            details={
                "reason": "invalid_persisted_selection_run",
                "field_name": field_name,
            },
        )
    return cast("dict[str, object]", payload)


def _text(value: object, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"persisted selection {field_name} must be text")
    return value


def _number(value: object, *, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"persisted selection {field_name} must be numeric")
    return float(value)


def _integer(value: object, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"persisted selection {field_name} must be an integer")
    return value


def _array(value: object, *, field_name: str) -> list[object]:
    if not isinstance(value, list):
        raise TypeError(f"persisted selection {field_name} must be a list")
    return cast("list[object]", value)


def _contribution(value: object) -> SelectionFactorContribution:
    payload = _mapping(value, field_name="factor_contribution")
    return SelectionFactorContribution(
        factor_name=_text(payload["factor_name"], field_name="factor_name"),
        value=_number(payload["value"], field_name="value"),
        weight=_number(payload["weight"], field_name="weight"),
        contribution=_number(payload["contribution"], field_name="contribution"),
    )


def _candidate(value: object) -> SelectionCandidate:
    payload = _mapping(value, field_name="candidate")
    contributions = _array(
        payload["factor_contributions"], field_name="factor_contributions"
    )
    industry_id = payload["industry_id"]
    return SelectionCandidate(
        instrument_id=InstrumentId(
            _integer(payload["instrument_id"], field_name="instrument_id")
        ),
        instrument_name=_text(payload["instrument_name"], field_name="instrument_name"),
        industry_id=(
            None
            if industry_id is None
            else _text(industry_id, field_name="industry_id")
        ),
        rank=_integer(payload["rank"], field_name="rank"),
        score=_number(payload["score"], field_name="score"),
        factor_contributions=tuple(_contribution(item) for item in contributions),
    )


def _exclusion(value: object) -> SelectionExclusion:
    payload = _mapping(value, field_name="exclusion")
    return SelectionExclusion(
        instrument_id=InstrumentId(
            _integer(payload["instrument_id"], field_name="instrument_id")
        ),
        instrument_name=_text(payload["instrument_name"], field_name="instrument_name"),
        reason_code=SelectionExclusionReason(
            _text(payload["reason_code"], field_name="reason_code")
        ),
        stage=_text(payload["stage"], field_name="stage"),
        detail=_text(payload["detail"], field_name="detail"),
    )


def _decode_payload(payload: Mapping[str, object]) -> SelectionRun:
    candidates = _array(payload["candidates"], field_name="candidates")
    exclusions = _array(payload["exclusions"], field_name="exclusions")
    source_snapshot_ids = _array(
        payload["source_snapshot_ids"], field_name="source_snapshot_ids"
    )
    missing_inputs = _array(payload["missing_inputs"], field_name="missing_inputs")
    industry_rotation_snapshot_id = payload["industry_rotation_snapshot_id"]
    return SelectionRun(
        input_hash=_text(payload["input_hash"], field_name="input_hash"),
        spec_hash=_text(payload["spec_hash"], field_name="spec_hash"),
        asset_kind=SelectionAssetKind(
            _text(payload["asset_kind"], field_name="asset_kind")
        ),
        spec_id=_text(payload["spec_id"], field_name="spec_id"),
        spec_version=_text(payload["spec_version"], field_name="spec_version"),
        seed=_integer(payload["seed"], field_name="seed"),
        as_of=datetime.fromisoformat(
            _text(payload["as_of"], field_name="as_of").replace("Z", "+00:00")
        ),
        knowledge_cutoff=datetime.fromisoformat(
            _text(payload["knowledge_cutoff"], field_name="knowledge_cutoff").replace(
                "Z", "+00:00"
            )
        ),
        publication_cutoff=datetime.fromisoformat(
            _text(
                payload["publication_cutoff"], field_name="publication_cutoff"
            ).replace("Z", "+00:00")
        ),
        universe_snapshot_id=_text(
            payload["universe_snapshot_id"], field_name="universe_snapshot_id"
        ),
        industry_rotation_snapshot_id=(
            None
            if industry_rotation_snapshot_id is None
            else _text(
                industry_rotation_snapshot_id,
                field_name="industry_rotation_snapshot_id",
            )
        ),
        source_snapshot_ids=tuple(
            _text(item, field_name="source_snapshot_ids")
            for item in source_snapshot_ids
        ),
        status=SelectionRunStatus(_text(payload["status"], field_name="status")),
        candidates=tuple(_candidate(item) for item in candidates),
        exclusions=tuple(_exclusion(item) for item in exclusions),
        missing_inputs=tuple(
            _text(item, field_name="missing_inputs") for item in missing_inputs
        ),
    )


def decode_selection_run(
    value: bytes | bytearray | memoryview | str,
    *,
    expected_run_id: str | None = None,
) -> SelectionRun:
    """Decode one run and fail closed if its content identity detached."""
    try:
        payload = _mapping(orjson.loads(value), field_name="run")
        run = _decode_payload(payload)
    except StrategySpecError:
        raise
    except (KeyError, TypeError, ValueError, orjson.JSONDecodeError) as exc:
        raise StrategySpecError(
            "persisted selection run payload is invalid",
            details={"reason": "invalid_persisted_selection_run"},
        ) from exc
    if expected_run_id is not None and run.run_id != expected_run_id:
        raise StrategySpecError(
            "persisted selection run identity mismatch",
            details={
                "reason": "selection_run_identity_mismatch",
                "expected_run_id": expected_run_id,
                "actual_run_id": run.run_id,
            },
        )
    return run
