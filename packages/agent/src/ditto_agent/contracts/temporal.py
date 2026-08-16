"""Trusted PIT and data-egress context injected by the deterministic host."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Literal

from ditto_agent.contracts._validation import (
    enum_value,
    normalized_text,
    normalized_unique_tuple,
    sha256_hex,
    utc_datetime,
)


class EgressClass(StrEnum):
    """Maximum data-egress class allowed for one tool invocation."""

    CLOUD_ALLOWED = "cloud_allowed"
    LOCAL_ONLY = "local_only"
    PROHIBITED = "prohibited"


@dataclass(frozen=True, slots=True)
class TemporalContextInput:
    """Untrusted temporal inputs supplied to the host validation boundary."""

    decision_time: datetime
    knowledge_cutoff: datetime
    publication_cutoff: datetime
    source_snapshot_id: str
    execution_eligible_at: datetime | Literal["not_applicable"]
    allowed_universe: tuple[str, ...]
    license_class: str
    egress_class: EgressClass
    campaign_authorization_id: str | None = None
    campaign_authority_hash: str | None = None


@dataclass(frozen=True, slots=True, init=False)
class TemporalToolContext:
    """Complete PIT visibility and authority context built only by the host."""

    decision_time: datetime
    knowledge_cutoff: datetime
    publication_cutoff: datetime
    source_snapshot_id: str
    execution_eligible_at: datetime | Literal["not_applicable"]
    allowed_universe: tuple[str, ...]
    license_class: str
    egress_class: EgressClass
    campaign_authorization_id: str | None
    campaign_authority_hash: str | None

    @classmethod
    def from_host(cls, source: TemporalContextInput) -> TemporalToolContext:
        """Build a complete context while rejecting missing or future visibility."""
        decision = utc_datetime(source.decision_time, field="decision_time")
        knowledge = utc_datetime(source.knowledge_cutoff, field="knowledge_cutoff")
        publication = utc_datetime(
            source.publication_cutoff, field="publication_cutoff"
        )
        if not publication <= knowledge <= decision:
            raise ValueError(
                "publication_cutoff must be <= knowledge_cutoff <= decision_time"
            )
        if source.execution_eligible_at == "not_applicable":
            execution: datetime | Literal["not_applicable"] = "not_applicable"
        else:
            execution = utc_datetime(
                source.execution_eligible_at, field="execution_eligible_at"
            )
        if (source.campaign_authorization_id is None) != (
            source.campaign_authority_hash is None
        ):
            message = (
                "campaign authorization id and authority hash must appear together"
            )
            raise ValueError(message)
        instance = object.__new__(cls)
        object.__setattr__(instance, "decision_time", decision)
        object.__setattr__(instance, "knowledge_cutoff", knowledge)
        object.__setattr__(instance, "publication_cutoff", publication)
        object.__setattr__(
            instance,
            "source_snapshot_id",
            normalized_text(source.source_snapshot_id, field="source_snapshot_id"),
        )
        object.__setattr__(instance, "execution_eligible_at", execution)
        object.__setattr__(
            instance,
            "allowed_universe",
            normalized_unique_tuple(
                source.allowed_universe, field="allowed_universe", sort=True
            ),
        )
        object.__setattr__(
            instance,
            "license_class",
            normalized_text(source.license_class, field="license_class"),
        )
        object.__setattr__(
            instance,
            "egress_class",
            enum_value(source.egress_class, EgressClass, field="egress_class"),
        )
        object.__setattr__(
            instance,
            "campaign_authorization_id",
            (
                normalized_text(
                    source.campaign_authorization_id,
                    field="campaign_authorization_id",
                )
                if source.campaign_authorization_id is not None
                else None
            ),
        )
        object.__setattr__(
            instance,
            "campaign_authority_hash",
            (
                sha256_hex(
                    source.campaign_authority_hash, field="campaign_authority_hash"
                )
                if source.campaign_authority_hash is not None
                else None
            ),
        )
        return instance

    def canonical_payload(self) -> dict[str, object]:
        """Return every trusted context field for hash and replay identities."""
        return {
            "decision_time": self.decision_time,
            "knowledge_cutoff": self.knowledge_cutoff,
            "publication_cutoff": self.publication_cutoff,
            "source_snapshot_id": self.source_snapshot_id,
            "execution_eligible_at": self.execution_eligible_at,
            "allowed_universe": self.allowed_universe,
            "license_class": self.license_class,
            "egress_class": self.egress_class,
            "campaign_authorization_id": self.campaign_authorization_id,
            "campaign_authority_hash": self.campaign_authority_hash,
        }


__all__ = ["EgressClass", "TemporalContextInput", "TemporalToolContext"]
