"""Canonical persistence codecs for immutable selection values."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import cast

import orjson
from ditto_kernel.identity import InstrumentId

from ditto_strategy.errors import StrategySpecError
from ditto_strategy.selection.canonical import canonical_spec_payload
from ditto_strategy.selection.contracts import (
    EtfSelectionSpec,
    SelectionAssetKind,
    SelectionCandidate,
    SelectionConditionOperator,
    SelectionExclusion,
    SelectionExclusionReason,
    SelectionFactorCondition,
    SelectionFactorContribution,
    SelectionFactorWeight,
    SelectionLimitState,
    SelectionRun,
    SelectionRunStatus,
    StockSelectionSpec,
    canonical_run_payload,
    canonical_spec_hash,
)

__all__ = [
    "decode_selection_policy",
    "decode_selection_run",
    "encode_selection_policy",
    "encode_selection_run",
]


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


def encode_selection_policy(
    value: StockSelectionSpec | EtfSelectionSpec,
) -> bytes:
    """Encode one validated selection policy as its canonical spec payload."""
    return orjson.dumps(canonical_spec_payload(value), option=orjson.OPT_SORT_KEYS)


def _policy_spec(
    payload: Mapping[str, object],
) -> StockSelectionSpec | EtfSelectionSpec:
    asset_kind = SelectionAssetKind(
        _text(payload["asset_kind"], field_name="asset_kind")
    )
    factor_weights = tuple(
        SelectionFactorWeight(
            _text(
                _mapping(item, field_name="factor_weights")["name"],
                field_name="factor_weights.name",
            ),
            _number(
                _mapping(item, field_name="factor_weights")["weight"],
                field_name="factor_weights.weight",
            ),
        )
        for item in _array(payload["factor_weights"], field_name="factor_weights")
    )
    filter_groups = tuple(
        tuple(
            SelectionFactorCondition(
                _text(
                    _mapping(condition, field_name="filter_groups")["factor_name"],
                    field_name="filter_groups.factor_name",
                ),
                SelectionConditionOperator(
                    _text(
                        _mapping(condition, field_name="filter_groups")["operator"],
                        field_name="filter_groups.operator",
                    )
                ),
                _number(
                    _mapping(condition, field_name="filter_groups")["value"],
                    field_name="filter_groups.value",
                ),
            )
            for condition in _array(group, field_name="filter_groups")
        )
        for group in _array(
            payload.get("filter_groups", []),
            field_name="filter_groups",
        )
    )
    excluded_limit_states = tuple(
        SelectionLimitState(_text(item, field_name="excluded_limit_states"))
        for item in _array(
            payload["excluded_limit_states"], field_name="excluded_limit_states"
        )
    )
    if asset_kind is SelectionAssetKind.STOCK:
        return StockSelectionSpec(
            spec_id=_text(payload["spec_id"], field_name="spec_id"),
            spec_version=_text(payload["spec_version"], field_name="spec_version"),
            top_k=_integer(payload["top_k"], field_name="top_k"),
            min_average_turnover=_number(
                payload["min_average_turnover"], field_name="min_average_turnover"
            ),
            min_listing_days=_integer(
                payload["min_listing_days"], field_name="min_listing_days"
            ),
            factor_weights=factor_weights,
            excluded_limit_states=excluded_limit_states,
            filter_groups=filter_groups,
        )
    max_tracking_error = payload.get("max_tracking_error")
    return EtfSelectionSpec(
        spec_id=_text(payload["spec_id"], field_name="spec_id"),
        spec_version=_text(payload["spec_version"], field_name="spec_version"),
        top_k=_integer(payload["top_k"], field_name="top_k"),
        min_average_turnover=_number(
            payload["min_average_turnover"], field_name="min_average_turnover"
        ),
        min_listing_days=_integer(
            payload["min_listing_days"], field_name="min_listing_days"
        ),
        factor_weights=factor_weights,
        excluded_limit_states=excluded_limit_states,
        filter_groups=filter_groups,
        max_tracking_error=(
            None
            if max_tracking_error is None
            else _number(max_tracking_error, field_name="max_tracking_error")
        ),
    )


def decode_selection_policy(
    value: bytes | bytearray | memoryview | str,
    *,
    expected_spec_hash: str,
) -> StockSelectionSpec | EtfSelectionSpec:
    """Decode one policy snapshot and fail closed on detached identity."""
    try:
        payload = _mapping(orjson.loads(value), field_name="policy")
        spec = _policy_spec(payload)
    except StrategySpecError:
        raise
    except (KeyError, TypeError, ValueError, orjson.JSONDecodeError) as exc:
        raise StrategySpecError(
            "persisted selection policy payload is invalid",
            details={"reason": "invalid_persisted_selection_policy"},
        ) from exc
    if canonical_spec_hash(spec) != expected_spec_hash:
        raise StrategySpecError(
            "persisted selection policy identity mismatch",
            details={
                "reason": "selection_policy_identity_mismatch",
                "expected_spec_hash": expected_spec_hash,
            },
        )
    return spec
