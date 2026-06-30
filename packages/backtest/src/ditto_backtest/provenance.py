"""Backtest provenance helpers."""

from __future__ import annotations

from collections.abc import Iterable
from hashlib import sha256

import orjson

__all__ = [
    "aggregate_source_snapshot_id",
    "normalize_source_snapshot_ids",
]


def normalize_source_snapshot_ids(
    snapshot_ids: Iterable[str | None],
) -> tuple[str, ...]:
    """Return non-empty source snapshot IDs in deterministic order."""
    return tuple(
        sorted(
            {
                snapshot_id.strip()
                for snapshot_id in snapshot_ids
                if snapshot_id is not None and snapshot_id.strip() != ""
            },
        ),
    )


def aggregate_source_snapshot_id(snapshot_ids: Iterable[str | None]) -> str | None:
    """Build a stable single snapshot ID from one or more exact source IDs."""
    normalized = normalize_source_snapshot_ids(snapshot_ids)
    if len(normalized) == 0:
        return None
    if len(normalized) == 1:
        return normalized[0]
    digest = sha256(orjson.dumps(normalized)).hexdigest()
    return f"snapshot-set:sha256:{digest}"
