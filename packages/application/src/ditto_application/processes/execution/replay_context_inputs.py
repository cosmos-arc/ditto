"""Adapt exact product evidence into backtest-owned replay context references."""

from __future__ import annotations

import hashlib
from dataclasses import asdict
from datetime import datetime
from typing import Any, Protocol, cast

import orjson
from ditto_backtest.context_inputs import (
    ContextInputKind,
    ReplayContextInputRef,
    normalize_context_input_refs,
)
from ditto_features.technical_analysis.contracts import (
    TechnicalAnalysisSnapshot,
    canonical_snapshot_hash,
)

from ditto_application.exceptions import AppProcessError

__all__ = [
    "ReplayableMarketContext",
    "build_replay_context_inputs",
    "decode_replay_context_inputs",
    "replay_context_inputs_payload",
]

_CONTEXT_REF_FIELDS = {
    "context_kind",
    "context_id",
    "content_hash",
    "as_of",
    "knowledge_cutoff",
    "publication_cutoff",
    "source_snapshot_ids",
}


class ReplayableMarketContext(Protocol):
    """Structural query projection consumed by the replay adapter."""

    @property
    def status(self) -> str:
        """Return the fail-closed market-context status."""
        ...

    @property
    def feature_set_id(self) -> str:
        """Return the canonical market-context identity."""
        ...

    @property
    def as_of(self) -> datetime:
        """Return the market-context observation cutoff."""
        ...

    @property
    def knowledge_cutoff(self) -> datetime:
        """Return the latest knowledge time admitted by the context."""
        ...

    @property
    def publication_cutoff(self) -> datetime:
        """Return the latest publication time admitted by the context."""
        ...

    @property
    def source_snapshot_ids(self) -> tuple[str, ...]:
        """Return the exact source snapshots used to derive the context."""
        ...


def _error(message: str, *, reason: str, **details: object) -> AppProcessError:
    return AppProcessError(message, details={"reason": reason, **details})


def _timestamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _market_hash(value: ReplayableMarketContext) -> str:
    encoded = orjson.dumps(
        asdict(cast("Any", value)),
        option=orjson.OPT_SORT_KEYS | orjson.OPT_UTC_Z,
    )
    return hashlib.sha256(encoded).hexdigest()


def _market_ref(value: ReplayableMarketContext) -> ReplayContextInputRef:
    if value.status == "blocked":
        raise _error(
            "blocked MarketContext cannot enter a backtest manifest",
            reason="replay_context_blocked",
            context_kind=ContextInputKind.MARKET_CONTEXT.value,
        )
    try:
        return ReplayContextInputRef(
            context_kind=ContextInputKind.MARKET_CONTEXT,
            context_id=value.feature_set_id,
            content_hash=_market_hash(value),
            as_of=_timestamp(value.as_of),
            knowledge_cutoff=_timestamp(value.knowledge_cutoff),
            publication_cutoff=_timestamp(value.publication_cutoff),
            source_snapshot_ids=value.source_snapshot_ids,
        )
    except ValueError as exc:
        raise _error(
            "MarketContext replay lineage is invalid",
            reason="replay_context_lineage_invalid",
        ) from exc


def _technical_ref(value: TechnicalAnalysisSnapshot) -> ReplayContextInputRef:
    if value.status == "blocked":
        raise _error(
            "blocked technical analysis cannot enter a backtest manifest",
            reason="replay_context_blocked",
            context_kind=ContextInputKind.TECHNICAL_ANALYSIS.value,
        )
    digest = canonical_snapshot_hash(value)
    if value.snapshot_id != f"technical-analysis:sha256:{digest}":
        raise _error(
            "technical analysis snapshot content identity has drifted",
            reason="replay_context_identity_mismatch",
            context_id=value.snapshot_id,
        )
    try:
        return ReplayContextInputRef(
            context_kind=ContextInputKind.TECHNICAL_ANALYSIS,
            context_id=value.snapshot_id,
            content_hash=digest,
            as_of=_timestamp(value.as_of),
            knowledge_cutoff=_timestamp(value.knowledge_cutoff),
            publication_cutoff=_timestamp(value.publication_cutoff),
            source_snapshot_ids=value.source_snapshot_ids,
        )
    except ValueError as exc:
        raise _error(
            "technical analysis replay lineage is invalid",
            reason="replay_context_lineage_invalid",
            context_id=value.snapshot_id,
        ) from exc


def build_replay_context_inputs(
    *,
    market_context: ReplayableMarketContext | None,
    technical_snapshots: tuple[TechnicalAnalysisSnapshot, ...],
) -> tuple[ReplayContextInputRef, ...]:
    """Build one canonical replay set with a single exact temporal boundary."""
    refs = (() if market_context is None else (_market_ref(market_context),)) + tuple(
        _technical_ref(value) for value in technical_snapshots
    )
    temporal_boundaries = {
        (item.as_of, item.knowledge_cutoff, item.publication_cutoff) for item in refs
    }
    if len(temporal_boundaries) > 1:
        raise _error(
            "replay context inputs do not share one temporal boundary",
            reason="replay_context_temporal_mismatch",
        )
    try:
        return normalize_context_input_refs(refs)
    except ValueError as exc:
        raise _error(
            "replay context input set is invalid",
            reason="replay_context_lineage_invalid",
        ) from exc


def replay_context_inputs_payload(
    values: tuple[ReplayContextInputRef, ...],
) -> list[dict[str, object]]:
    """Project one exact canonical context set into transport-safe JSON."""
    try:
        refs = normalize_context_input_refs(values)
    except ValueError as exc:
        raise _error(
            "replay context input set is invalid",
            reason="invalid_replay_context_inputs",
        ) from exc
    boundaries = {
        (item.as_of, item.knowledge_cutoff, item.publication_cutoff) for item in refs
    }
    if len(boundaries) > 1:
        raise _error(
            "replay context inputs do not share one temporal boundary",
            reason="invalid_replay_context_inputs",
        )
    return [
        {
            "context_kind": item.context_kind.value,
            "context_id": item.context_id,
            "content_hash": item.content_hash,
            "as_of": item.as_of,
            "knowledge_cutoff": item.knowledge_cutoff,
            "publication_cutoff": item.publication_cutoff,
            "source_snapshot_ids": list(item.source_snapshot_ids),
        }
        for item in refs
    ]


def _decode_context_input(raw: object) -> ReplayContextInputRef:
    if type(raw) is not dict:
        raise _error(
            "context input must be an object",
            reason="invalid_replay_context_inputs",
        )
    item = cast("dict[str, object]", raw)
    if set(item) != _CONTEXT_REF_FIELDS:
        raise _error(
            "context input fields do not match the contract",
            reason="invalid_replay_context_inputs",
        )
    raw_snapshots = item.get("source_snapshot_ids")
    if type(raw_snapshots) is not list or not all(
        type(snapshot) is str for snapshot in cast("list[object]", raw_snapshots)
    ):
        raise _error(
            "source_snapshot_ids must be an array of strings",
            reason="invalid_replay_context_inputs",
        )
    string_fields = {
        field_name: item.get(field_name)
        for field_name in _CONTEXT_REF_FIELDS - {"source_snapshot_ids"}
    }
    if any(type(field_value) is not str for field_value in string_fields.values()):
        raise _error(
            "context input identity and timestamps must be strings",
            reason="invalid_replay_context_inputs",
        )
    try:
        return ReplayContextInputRef(
            context_kind=ContextInputKind(
                cast("str", string_fields.get("context_kind"))
            ),
            context_id=cast("str", string_fields.get("context_id")),
            content_hash=cast("str", string_fields.get("content_hash")),
            as_of=cast("str", string_fields.get("as_of")),
            knowledge_cutoff=cast("str", string_fields.get("knowledge_cutoff")),
            publication_cutoff=cast("str", string_fields.get("publication_cutoff")),
            source_snapshot_ids=tuple(cast("list[str]", raw_snapshots)),
        )
    except (TypeError, ValueError) as exc:
        raise _error(
            "context input values are invalid",
            reason="invalid_replay_context_inputs",
        ) from exc


def decode_replay_context_inputs(value: object) -> tuple[ReplayContextInputRef, ...]:
    """Decode and revalidate replay refs without accepting partial identities."""
    if type(value) is not list:
        raise _error(
            "replay context inputs must be an array",
            reason="invalid_replay_context_inputs",
        )
    refs = tuple(_decode_context_input(raw) for raw in cast("list[object]", value))
    try:
        normalized = normalize_context_input_refs(refs)
        boundaries = {
            (item.as_of, item.knowledge_cutoff, item.publication_cutoff)
            for item in normalized
        }
        if len(boundaries) > 1:
            raise _error(
                "context inputs have mixed temporal boundaries",
                reason="invalid_replay_context_inputs",
            )
        return normalized
    except (TypeError, ValueError) as exc:
        raise _error(
            "replay context input set is invalid",
            reason="invalid_replay_context_inputs",
        ) from exc
