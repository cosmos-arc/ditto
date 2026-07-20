"""Neutral read contracts shared by research certification consumers and adapters."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Protocol, cast
from unicodedata import category, normalize

from ditto_application.exceptions import AppProcessError

__all__ = [
    "ExperimentSnapshotIdentity",
    "ResearchCertificationProbe",
    "ResearchCertificationRequest",
    "ResearchCertificationResult",
    "ResearchDatasetRequirement",
    "ResearchSnapshotEvidence",
    "is_canonical_content_hash",
    "is_canonical_identity",
]

_CONTENT_HASH_LENGTH = 64


def is_canonical_identity(value: object) -> bool:
    """Return whether a value is one canonical non-empty identity string."""
    if type(value) is not str or not value or value != value.strip():
        return False
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return normalize("NFC", value) == value and all(
        not category(char).startswith("C") for char in value
    )


def is_canonical_content_hash(value: object) -> bool:
    """Return whether a value is one lowercase SHA-256 digest."""
    return (
        type(value) is str
        and len(value) == _CONTENT_HASH_LENGTH
        and all(char in "0123456789abcdef" for char in value)
    )


@dataclass(frozen=True, slots=True)
class ResearchDatasetRequirement:
    """One exact dataset and snapshot evidence requirement."""

    dataset_id: str
    expected_snapshot_ids: tuple[str, ...]
    requires_pit_universe: bool = False
    certified_from: date | None = None

    def __post_init__(self) -> None:
        """Reject unbound or ambiguous certification requirements."""
        raw_snapshot_ids = cast("object", self.expected_snapshot_ids)
        if type(raw_snapshot_ids) is not tuple:
            raise AppProcessError(
                "research dataset requirement is invalid",
                details={
                    "code": "SPEC_INVALID",
                    "reason": "invalid_dataset_requirement",
                },
            )
        snapshot_ids = cast("tuple[object, ...]", raw_snapshot_ids)
        if (
            not is_canonical_identity(self.dataset_id)
            or not snapshot_ids
            or not all(is_canonical_identity(item) for item in snapshot_ids)
            or len(set(snapshot_ids)) != len(snapshot_ids)
            or type(self.requires_pit_universe) is not bool
            or (
                self.certified_from is not None
                and type(self.certified_from) is not date
            )
        ):
            raise AppProcessError(
                "research dataset requirement is invalid",
                details={
                    "code": "SPEC_INVALID",
                    "reason": "invalid_dataset_requirement",
                },
            )
        object.__setattr__(
            self,
            "expected_snapshot_ids",
            tuple(sorted(cast("tuple[str, ...]", snapshot_ids))),
        )

    def as_payload(self) -> Mapping[str, object]:
        """Return the canonical scalar representation used by gates and hashes."""
        return {
            "dataset_id": self.dataset_id,
            "expected_snapshot_ids": list(self.expected_snapshot_ids),
            "requires_pit_universe": self.requires_pit_universe,
            "certified_from": (
                None if self.certified_from is None else self.certified_from.isoformat()
            ),
        }


@dataclass(frozen=True, slots=True)
class ExperimentSnapshotIdentity:
    """Application-owned certified snapshot identity used by planning."""

    snapshot_id: str
    manifest_hash: str

    def __post_init__(self) -> None:
        """Reject snapshot identities that cannot be reproduced byte-for-byte."""
        if not is_canonical_identity(self.snapshot_id) or not is_canonical_content_hash(
            self.manifest_hash
        ):
            raise AppProcessError(
                "experiment snapshot identity is invalid",
                details={
                    "code": "SPEC_INVALID",
                    "reason": "invalid_research_snapshot_identity",
                },
            )


@dataclass(frozen=True, slots=True)
class ResearchCertificationRequest:
    """Exact interval/profile input for the read-only certification probe."""

    profile: str
    required_from: date
    required_to: date
    requirements: tuple[ResearchDatasetRequirement, ...]
    snapshot_identity: ExperimentSnapshotIdentity


@dataclass(frozen=True, slots=True)
class ResearchSnapshotEvidence:
    """Authoritative catalog facts for one immutable research dataset snapshot."""

    snapshot_id: str
    dataset_id: str
    manifest_hash: str
    source_snapshot_ids: tuple[str, ...]
    snapshot_start: date
    snapshot_end: date
    known_at_policy: str
    builder_version: str


@dataclass(frozen=True, slots=True)
class ResearchCertificationResult:
    """Scalar-only result returned by a certification read adapter."""

    ready: bool
    profile: str
    dataset_ids: tuple[str, ...]
    report_ids: tuple[str, ...]
    reason_codes: tuple[str, ...]
    snapshot_evidence: ResearchSnapshotEvidence | None


class ResearchCertificationProbe(Protocol):
    """Read-only certification boundary used by experiment preflight."""

    def assess(
        self,
        request: ResearchCertificationRequest,
    ) -> ResearchCertificationResult:
        """Read exact certification evidence without mutation."""
        ...
