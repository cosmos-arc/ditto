"""Immutable research judgments bound to explicit run comparisons."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast

import orjson

__all__ = ["ResearchJudgment"]

_SCHEMA_VERSION = 1


def _text(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{field_name} must be a non-empty unpadded string")
    return value


def _utc(value: object, *, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{field_name} must be a timezone-aware datetime")
    return value.astimezone(UTC)


def _run_ids(values: object) -> tuple[str, ...]:
    if not isinstance(values, tuple) or not values:
        raise ValueError("run_ids must be a non-empty tuple")
    raw_values = cast("tuple[object, ...]", values)
    ids = tuple(_text(item, field_name="run id") for item in raw_values)
    if len(set(ids)) != len(ids):
        raise ValueError("run_ids must reference unique runs")
    return ids


def _strategy_version(value: object) -> int:
    if type(value) is not int or value < 1:
        raise ValueError("strategy_version must be a positive integer")
    return value


@dataclass(frozen=True, slots=True)
class ResearchJudgment:
    """
    One saved research conclusion bound to explicit run identities.

    The judgment pins the exact compared runs (and optionally the strategy
    version chosen for follow-up verification), so reopening it later never
    re-resolves against newer data: the runs keep their own artifacts.
    """

    run_ids: tuple[str, ...]
    judgment: str
    created_at: datetime
    strategy_id: str | None = None
    strategy_version: int | None = None
    schema_version: int = _SCHEMA_VERSION

    def __post_init__(self) -> None:
        """Fail closed on erased runs, judgment text, or half strategy refs."""
        if (
            type(self.schema_version) is not int
            or self.schema_version != _SCHEMA_VERSION
        ):
            raise ValueError("unsupported Research Judgment schema_version")
        if (self.strategy_id is None) != (self.strategy_version is None):
            raise ValueError("strategy_id and strategy_version must be set together")
        object.__setattr__(self, "run_ids", _run_ids(self.run_ids))
        object.__setattr__(
            self, "judgment", _text(self.judgment, field_name="judgment")
        )
        if self.strategy_id is not None:
            object.__setattr__(
                self,
                "strategy_id",
                _text(self.strategy_id, field_name="strategy_id"),
            )
            object.__setattr__(
                self, "strategy_version", _strategy_version(self.strategy_version)
            )
        object.__setattr__(
            self, "created_at", _utc(self.created_at, field_name="created_at")
        )

    @property
    def canonical_payload(self) -> dict[str, object]:
        """
        Return the complete deterministic record preimage.

        created_at stays out of the preimage: one exact user record keeps one
        identity regardless of when the retry landed, while an edited judgment
        is new content and therefore a new entry. The optional strategy
        reference rides in the preimage only when present, mirroring
        NextDayPlan.source_judgment_id.
        """
        payload: dict[str, object] = {
            "schema_version": self.schema_version,
            # run 顺序是记录者组织的比较成员序，按输入原序冻结。
            "run_ids": list(self.run_ids),
            "judgment": self.judgment,
        }
        if self.strategy_id is not None and self.strategy_version is not None:
            payload["strategy_id"] = self.strategy_id
            payload["strategy_version"] = self.strategy_version
        return payload

    @property
    def content_hash(self) -> str:
        """Return the full SHA-256 hash of the canonical record payload."""
        encoded = orjson.dumps(self.canonical_payload, option=orjson.OPT_SORT_KEYS)
        return hashlib.sha256(encoded).hexdigest()

    @property
    def judgment_id(self) -> str:
        """Return the stable content-addressed Research Judgment identity."""
        return f"research-judgment:sha256:{self.content_hash}"
