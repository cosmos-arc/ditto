"""Provider-specific immutable snapshot contracts."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol, runtime_checkable

import orjson

from ditto_data.catalog.contracts import DataAssetRef

__all__ = [
    "ProviderSnapshot",
    "ProviderSnapshotDraft",
    "ProviderSnapshotReader",
    "ProviderSnapshotWriter",
]

_SECRET_MARKERS: tuple[str, ...] = (
    "api_key",
    "authorization",
    "credential",
    "password",
    "secret",
    "token",
)


def _validate_text(field: str, value: str) -> None:
    if not value or value.strip() != value:
        msg = f"Invalid provider snapshot {field}: {value!r}"
        raise ValueError(msg)


def _validate_no_secret_metadata(metadata: tuple[tuple[str, str], ...]) -> None:
    for key, _value in metadata:
        normalized = key.casefold().replace("-", "_")
        if any(marker in normalized for marker in _SECRET_MARKERS):
            msg = f"provider snapshot metadata must not contain secret field {key!r}"
            raise ValueError(msg)


@dataclass(frozen=True)
class ProviderSnapshotDraft:
    """Provider response values used to derive an immutable snapshot ID."""

    dataset_id: str
    source: str
    request_start: str
    request_end: str
    schema_version: str
    checksum: str
    canonical_asset: DataAssetRef
    request_parameters_hash: str
    response_metadata: tuple[tuple[str, str], ...]
    license_record_id: str
    row_count: int
    payload_uri: str | None
    payload_retained: bool
    created_at: datetime


@dataclass(frozen=True)
class ProviderSnapshot:
    """Immutable provider response evidence linked to one canonical asset."""

    snapshot_id: str
    dataset_id: str
    source: str
    request_start: str
    request_end: str
    schema_version: str
    checksum: str
    canonical_asset: DataAssetRef
    request_parameters_hash: str
    response_metadata: tuple[tuple[str, str], ...]
    license_record_id: str
    row_count: int
    payload_uri: str | None
    payload_retained: bool
    created_at: datetime

    def __post_init__(self) -> None:
        """Validate source evidence without persisting provider secrets."""
        for field in (
            "snapshot_id",
            "dataset_id",
            "source",
            "request_start",
            "request_end",
            "schema_version",
            "checksum",
            "request_parameters_hash",
            "license_record_id",
        ):
            _validate_text(field, str(getattr(self, field)))
        if self.source != self.source.lower():
            msg = f"Invalid provider snapshot source: {self.source!r}"
            raise ValueError(msg)
        if self.canonical_asset.dataset_id != self.dataset_id:
            msg = "provider snapshot canonical asset dataset must match dataset_id"
            raise ValueError(msg)
        try:
            request_start = date.fromisoformat(self.request_start)
            request_end = date.fromisoformat(self.request_end)
        except ValueError as error:
            msg = "provider snapshot request interval must use ISO dates"
            raise ValueError(msg) from error
        if request_end < request_start:
            raise ValueError("provider snapshot request_end precedes request_start")
        if self.row_count < 0:
            raise ValueError("provider snapshot row_count must be non-negative")
        if self.created_at.tzinfo is None:
            raise ValueError("provider snapshot created_at must be timezone-aware")
        if len({key for key, _value in self.response_metadata}) != len(
            self.response_metadata
        ):
            raise ValueError("provider snapshot response metadata has duplicate keys")
        _validate_no_secret_metadata(self.response_metadata)
        if self.payload_retained and not self.payload_uri:
            raise ValueError("retained provider snapshot requires payload_uri")

    @classmethod
    def create(cls, draft: ProviderSnapshotDraft) -> ProviderSnapshot:
        """Create a snapshot with a deterministic provider-specific identity."""
        placeholder = cls(
            snapshot_id="pending",
            dataset_id=draft.dataset_id,
            source=draft.source,
            request_start=draft.request_start,
            request_end=draft.request_end,
            schema_version=draft.schema_version,
            checksum=draft.checksum,
            canonical_asset=draft.canonical_asset,
            request_parameters_hash=draft.request_parameters_hash,
            response_metadata=tuple(sorted(draft.response_metadata)),
            license_record_id=draft.license_record_id,
            row_count=draft.row_count,
            payload_uri=draft.payload_uri,
            payload_retained=draft.payload_retained,
            created_at=draft.created_at,
        )
        return cls(
            snapshot_id=placeholder.expected_snapshot_id(),
            dataset_id=placeholder.dataset_id,
            source=placeholder.source,
            request_start=placeholder.request_start,
            request_end=placeholder.request_end,
            schema_version=placeholder.schema_version,
            checksum=placeholder.checksum,
            canonical_asset=placeholder.canonical_asset,
            request_parameters_hash=placeholder.request_parameters_hash,
            response_metadata=placeholder.response_metadata,
            license_record_id=placeholder.license_record_id,
            row_count=placeholder.row_count,
            payload_uri=placeholder.payload_uri,
            payload_retained=placeholder.payload_retained,
            created_at=placeholder.created_at,
        )

    def expected_snapshot_id(self) -> str:
        """Return the identity mandated by the R2 provider snapshot contract."""
        payload = orjson.dumps(
            [
                self.dataset_id,
                self.source,
                self.request_start,
                self.request_end,
                self.schema_version,
                self.checksum,
            ]
        )
        digest = hashlib.sha256(payload).hexdigest()
        return f"snapshot:{self.source}:{self.dataset_id}:sha256:{digest}"


@runtime_checkable
class ProviderSnapshotReader(Protocol):
    """Read immutable provider snapshots."""

    def get_snapshot(self, snapshot_id: str) -> ProviderSnapshot | None:
        """Return one snapshot by deterministic ID."""
        ...

    def list_snapshots(
        self,
        *,
        dataset_id: str | None = None,
        source: str | None = None,
        canonical_asset: DataAssetRef | None = None,
    ) -> tuple[ProviderSnapshot, ...]:
        """List snapshots with optional product/provider/canonical filters."""
        ...


@runtime_checkable
class ProviderSnapshotWriter(Protocol):
    """Append immutable provider snapshots."""

    def append_snapshot(self, snapshot: ProviderSnapshot) -> None:
        """Append immutable snapshot evidence idempotently."""
        ...
