"""Canonical persistence codec for industry-rotation snapshots."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import cast

import orjson

from ditto_strategy.errors import StrategySpecError
from ditto_strategy.industry_rotation.contracts import (
    IndustryRotationContribution,
    IndustryRotationRank,
    IndustryRotationSnapshot,
    IndustryRotationStatus,
    canonical_snapshot_payload,
)

__all__ = ["decode_industry_rotation", "encode_industry_rotation"]


def encode_industry_rotation(value: IndustryRotationSnapshot) -> bytes:
    """Encode one validated snapshot as recursive key-sorted JSON bytes."""
    return orjson.dumps(canonical_snapshot_payload(value), option=orjson.OPT_SORT_KEYS)


def _mapping(value: object, *, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise StrategySpecError(
            f"persisted industry rotation {field_name} must be an object",
            details={"reason": "invalid_persisted_industry_rotation"},
        )
    payload = cast("dict[object, object]", value)
    if any(not isinstance(key, str) for key in payload):
        raise StrategySpecError(
            f"persisted industry rotation {field_name} must use string keys",
            details={"reason": "invalid_persisted_industry_rotation"},
        )
    return cast("dict[str, object]", payload)


def _text(value: object, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"persisted industry rotation {field_name} must be text")
    return value


def _number(value: object, *, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"persisted industry rotation {field_name} must be numeric")
    return float(value)


def _integer(value: object, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"persisted industry rotation {field_name} must be an integer")
    return value


def _array(value: object, *, field_name: str) -> list[object]:
    if not isinstance(value, list):
        raise TypeError(f"persisted industry rotation {field_name} must be a list")
    return cast("list[object]", value)


def _contribution(value: object) -> IndustryRotationContribution:
    payload = _mapping(value, field_name="contribution")
    raw_value = payload["value"]
    return IndustryRotationContribution(
        metric=_text(payload["metric"], field_name="metric"),
        value=None if raw_value is None else _number(raw_value, field_name="value"),
        weight=_number(payload["weight"], field_name="weight"),
        contribution=_number(payload["contribution"], field_name="contribution"),
    )


def _rank(value: object) -> IndustryRotationRank:
    payload = _mapping(value, field_name="rank")
    contributions = _array(payload["contributions"], field_name="contributions")
    missing_inputs = _array(payload["missing_inputs"], field_name="missing_inputs")
    return IndustryRotationRank(
        industry_id=_text(payload["industry_id"], field_name="industry_id"),
        industry_name=_text(payload["industry_name"], field_name="industry_name"),
        rank=_integer(payload["rank"], field_name="rank"),
        score=_number(payload["score"], field_name="score"),
        contributions=tuple(_contribution(item) for item in contributions),
        missing_inputs=tuple(
            _text(item, field_name="missing_inputs") for item in missing_inputs
        ),
    )


def decode_industry_rotation(
    value: bytes | bytearray | memoryview | str,
    *,
    expected_snapshot_id: str | None = None,
) -> IndustryRotationSnapshot:
    """Decode one snapshot and reject detached content identity."""
    try:
        payload = _mapping(orjson.loads(value), field_name="snapshot")
        rankings = _array(payload["rankings"], field_name="rankings")
        source_snapshot_ids = _array(
            payload["source_snapshot_ids"], field_name="source_snapshot_ids"
        )
        missing_inputs = _array(payload["missing_inputs"], field_name="missing_inputs")
        market_context_id = payload["market_context_feature_set_id"]
        snapshot = IndustryRotationSnapshot(
            input_hash=_text(payload["input_hash"], field_name="input_hash"),
            as_of=datetime.fromisoformat(
                _text(payload["as_of"], field_name="as_of").replace("Z", "+00:00")
            ),
            knowledge_cutoff=datetime.fromisoformat(
                _text(
                    payload["knowledge_cutoff"], field_name="knowledge_cutoff"
                ).replace("Z", "+00:00")
            ),
            publication_cutoff=datetime.fromisoformat(
                _text(
                    payload["publication_cutoff"], field_name="publication_cutoff"
                ).replace("Z", "+00:00")
            ),
            source_snapshot_ids=tuple(
                _text(item, field_name="source_snapshot_ids")
                for item in source_snapshot_ids
            ),
            market_context_feature_set_id=(
                None
                if market_context_id is None
                else _text(
                    market_context_id, field_name="market_context_feature_set_id"
                )
            ),
            membership_version=_text(
                payload["membership_version"], field_name="membership_version"
            ),
            algorithm_version=_text(
                payload["algorithm_version"], field_name="algorithm_version"
            ),
            status=IndustryRotationStatus(
                _text(payload["status"], field_name="status")
            ),
            rankings=tuple(_rank(item) for item in rankings),
            missing_inputs=tuple(
                _text(item, field_name="missing_inputs") for item in missing_inputs
            ),
        )
    except StrategySpecError:
        raise
    except (KeyError, TypeError, ValueError, orjson.JSONDecodeError) as exc:
        raise StrategySpecError(
            "persisted industry rotation payload is invalid",
            details={"reason": "invalid_persisted_industry_rotation"},
        ) from exc
    if (
        expected_snapshot_id is not None
        and snapshot.snapshot_id != expected_snapshot_id
    ):
        raise StrategySpecError(
            "persisted industry rotation identity mismatch",
            details={
                "reason": "industry_rotation_identity_mismatch",
                "expected_snapshot_id": expected_snapshot_id,
                "actual_snapshot_id": snapshot.snapshot_id,
            },
        )
    return snapshot
