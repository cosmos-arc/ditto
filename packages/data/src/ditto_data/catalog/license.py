"""Dataset/provider license ledger contracts."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal, Protocol, runtime_checkable

import orjson

__all__ = [
    "DatasetLicenseDraft",
    "DatasetLicenseReader",
    "DatasetLicenseRecord",
    "DatasetLicenseWriter",
    "LicensePermission",
]

type LicensePermission = Literal["allowed", "restricted", "prohibited"]

_SECRET_MARKERS: tuple[str, ...] = (
    "api_key",
    "client_secret",
    "credential",
    "password",
    "secret",
    "token",
)


@dataclass(frozen=True)
class DatasetLicenseDraft:
    """Reviewed provider terms used to derive an immutable ledger record."""

    dataset_id: str
    source: str
    terms_version: str
    effective_from: date
    effective_to: date | None
    local_cache: LicensePermission
    derivative_compute: LicensePermission
    display: LicensePermission
    redistribution: LicensePermission
    notes: str
    reviewed_by: str
    reviewed_at: datetime


@dataclass(frozen=True)
class DatasetLicenseRecord:
    """Immutable review of provider usage rights for one dataset."""

    record_id: str
    dataset_id: str
    source: str
    terms_version: str
    effective_from: date
    effective_to: date | None
    local_cache: LicensePermission
    derivative_compute: LicensePermission
    display: LicensePermission
    redistribution: LicensePermission
    notes: str
    reviewed_by: str
    reviewed_at: datetime

    def __post_init__(self) -> None:
        """Validate ledger values and prevent accidental credential storage."""
        for field in (
            "record_id",
            "dataset_id",
            "source",
            "terms_version",
            "notes",
            "reviewed_by",
        ):
            value = str(getattr(self, field))
            if not value or value.strip() != value:
                msg = f"Invalid license record {field}: {value!r}"
                raise ValueError(msg)
        if self.source != self.source.lower():
            raise ValueError(f"Invalid license record source: {self.source!r}")
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("license effective_to precedes effective_from")
        if self.reviewed_at.tzinfo is None:
            raise ValueError("license reviewed_at must be timezone-aware")
        normalized_notes = self.notes.casefold().replace("-", "_")
        if any(marker in normalized_notes for marker in _SECRET_MARKERS):
            raise ValueError("license notes must not contain secret material")

    @classmethod
    def create(cls, draft: DatasetLicenseDraft) -> DatasetLicenseRecord:
        """Create a deterministic append-only license review record."""
        identity = orjson.dumps(
            [
                draft.dataset_id,
                draft.source,
                draft.terms_version,
                draft.effective_from.isoformat(),
            ]
        )
        digest = hashlib.sha256(identity).hexdigest()
        return cls(
            record_id=(f"license:{draft.source}:{draft.dataset_id}:sha256:{digest}"),
            dataset_id=draft.dataset_id,
            source=draft.source,
            terms_version=draft.terms_version,
            effective_from=draft.effective_from,
            effective_to=draft.effective_to,
            local_cache=draft.local_cache,
            derivative_compute=draft.derivative_compute,
            display=draft.display,
            redistribution=draft.redistribution,
            notes=draft.notes,
            reviewed_by=draft.reviewed_by,
            reviewed_at=draft.reviewed_at,
        )


@runtime_checkable
class DatasetLicenseReader(Protocol):
    """Read append-only provider license reviews."""

    def get_license(self, record_id: str) -> DatasetLicenseRecord | None:
        """Return one immutable license review by ID."""
        ...

    def list_licenses(
        self,
        *,
        dataset_id: str | None = None,
        source: str | None = None,
    ) -> tuple[DatasetLicenseRecord, ...]:
        """List reviews with optional product/provider filters."""
        ...


@runtime_checkable
class DatasetLicenseWriter(Protocol):
    """Append provider license reviews."""

    def append_license(self, record: DatasetLicenseRecord) -> None:
        """Append an immutable reviewed license record idempotently."""
        ...
