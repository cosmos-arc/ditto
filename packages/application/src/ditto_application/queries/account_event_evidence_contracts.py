"""Privacy-scoped application contracts for Manual Account event evidence."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from ditto_application.queries.evidence_contracts import (
    EvidenceArtifactReference,
    EvidencePayloadReadModel,
    EvidenceTemporalContext,
)

__all__ = [
    "AccountEventEvidenceQueryPort",
    "AccountEventEvidenceReadModel",
    "AccountEventEvidenceRedaction",
]


class AccountEventEvidenceRedaction(StrEnum):
    """Host-selected maximum detail for a Manual Account evidence payload."""

    CLOUD_REDACTED = "cloud_redacted"
    LOCAL_DETAIL = "local_detail"


@dataclass(frozen=True, slots=True)
class AccountEventEvidenceReadModel:
    """One exact as-of Manual ledger projection with an explicit privacy class."""

    account_id: str
    as_of: str
    ledger_hash: str
    redaction: AccountEventEvidenceRedaction
    temporal_context: EvidenceTemporalContext
    payload: EvidencePayloadReadModel
    artifact_refs: tuple[EvidenceArtifactReference, ...]
    lineage: tuple[str, ...]


class AccountEventEvidenceQueryPort(Protocol):
    """Read Manual Account event evidence under host-only temporal/privacy scope."""

    def get_evidence(
        self,
        *,
        account_id: str,
        as_of: str,
        redaction: AccountEventEvidenceRedaction,
        context: EvidenceTemporalContext,
    ) -> AccountEventEvidenceReadModel:
        """Return one immutable redacted Manual Account ledger."""
        ...
