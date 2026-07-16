"""Durable ingestion-evidence policy for quality batch checks."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from ditto_application.catalog_freshness import PersistedIngestionEvidenceVerifier
from ditto_application.processes.ingestion.result_handler import (
    PersistedIngestionDQEvidence,
    persisted_ingestion_dq_evidence,
)

__all__ = ["QualityEvidenceDecision", "verify_batch_ingestion_evidence"]


@dataclass(frozen=True)
class QualityEvidenceDecision:
    """Validated persisted evidence or one stable fail-closed error code."""

    evidence: PersistedIngestionDQEvidence | None = None
    error: str | None = None


def verify_batch_ingestion_evidence(
    payload: Mapping[str, object] | None,
    *,
    dataset: str,
    trade_date: str,
    verifier: PersistedIngestionEvidenceVerifier,
) -> QualityEvidenceDecision:
    """Parse serialized evidence and bind it to durable catalog/log facts."""
    if payload is None:
        return QualityEvidenceDecision()
    evidence = persisted_ingestion_dq_evidence(
        payload,
        dataset=dataset,
        trade_date=trade_date,
    )
    if not evidence.passed:
        return QualityEvidenceDecision(
            error=evidence.error or "PERSISTED_INGESTION_EVIDENCE_INVALID"
        )
    if evidence.evidence is None or evidence.quality_evidence is None:
        return QualityEvidenceDecision(error="PERSISTED_INGESTION_EVIDENCE_INVALID")

    if evidence.evidence.get("kind") == "persisted_asof_catalog_snapshot":
        return _verify_asof_evidence(
            evidence,
            dataset=dataset,
            trade_date=trade_date,
            verifier=verifier,
        )
    return _verify_exact_evidence(
        evidence,
        dataset=dataset,
        trade_date=trade_date,
        verifier=verifier,
    )


def _verify_asof_evidence(
    evidence: PersistedIngestionDQEvidence,
    *,
    dataset: str,
    trade_date: str,
    verifier: PersistedIngestionEvidenceVerifier,
) -> QualityEvidenceDecision:
    asof = evidence.evidence
    if asof is None:
        return QualityEvidenceDecision(error="PIT_COMPONENT_QUALITY_EVIDENCE_INVALID")
    source = asof.get("source")
    quality_evidence = evidence.quality_evidence
    quality_source = (
        quality_evidence.get("source") if quality_evidence is not None else None
    )
    raw_snapshot_ids = asof.get("source_snapshot_ids")
    row_count = asof.get("row_count")
    raw_snapshot_items = (
        cast(list[object], raw_snapshot_ids)
        if isinstance(raw_snapshot_ids, list)
        else []
    )
    snapshot_ids = tuple(item for item in raw_snapshot_items if isinstance(item, str))
    durable = bool(
        isinstance(source, str)
        and quality_source == source
        and isinstance(raw_snapshot_ids, list)
        and len(snapshot_ids) == len(raw_snapshot_items)
        and isinstance(row_count, int)
        and not isinstance(row_count, bool)
        and verifier.verify_asof_snapshot(
            dataset=dataset,
            source=source,
            signal_date=trade_date,
            expected_snapshot_ids=snapshot_ids,
            expected_row_count=row_count,
        )
    )
    if durable:
        return QualityEvidenceDecision(evidence=evidence)
    return QualityEvidenceDecision(error="PIT_COMPONENT_QUALITY_EVIDENCE_INVALID")


def _verify_exact_evidence(
    evidence: PersistedIngestionDQEvidence,
    *,
    dataset: str,
    trade_date: str,
    verifier: PersistedIngestionEvidenceVerifier,
) -> QualityEvidenceDecision:
    quality_evidence = evidence.quality_evidence
    source = quality_evidence.get("source") if quality_evidence is not None else None
    durable = bool(
        isinstance(source, str)
        and evidence.checksum is not None
        and evidence.row_count is not None
        and verifier.verify_exact_date(
            dataset=dataset,
            source=source,
            trade_date=trade_date,
            checksum=evidence.checksum,
            row_count=evidence.row_count,
        )
    )
    if durable:
        return QualityEvidenceDecision(evidence=evidence)
    return QualityEvidenceDecision(error="INGESTION_COMPONENT_QUALITY_EVIDENCE_INVALID")
