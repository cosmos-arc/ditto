"""Certified historical snapshot-set adapter for Agent MarketContext evidence."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from ditto_data.catalog.certification import (
    CertificationReader,
    DatasetCertificationReport,
)

from ditto_application.catalog_freshness import aggregate_source_snapshot_ids
from ditto_application.exceptions import AppConfigurationError, AppQueryError
from ditto_application.queries.evidence_contracts import (
    EvidenceArtifactReference,
    EvidencePayloadReadModel,
    EvidenceTemporalContext,
    MarketContextEvidenceReadModel,
)
from ditto_application.queries.market_context import (
    MarketContextFacade,
    MarketContextRequest,
    MarketContextView,
)

__all__ = ["MarketContextEvidenceQueryFacade"]

_MARKET_CONTEXT_DATASETS = (
    "commodity_daily",
    "fx_daily",
    "global_index_daily",
    "index_daily",
    "index_weight",
    "macro_indicators",
    "stock_daily",
)
_REQUIRED_DATASETS = frozenset({"index_daily", "stock_daily"})


def _error(code: str, reason: str, **details: object) -> AppQueryError:
    return AppQueryError(
        f"market context evidence failed closed: {reason}",
        details={"code": code, "reason": reason, **details},
    )


def _approved_report_at(
    reader: CertificationReader,
    *,
    dataset_id: str,
    profile: str,
    knowledge_cutoff: datetime,
) -> DatasetCertificationReport | None:
    selected: DatasetCertificationReport | None = None
    for report in reader.list_reports(dataset_id, profile):
        if report.generated_at > knowledge_cutoff:
            continue
        visible_events = tuple(
            event
            for event in reader.list_events(report.report_id)
            if event.occurred_at <= knowledge_cutoff
        )
        if visible_events and visible_events[-1].action == "approved":
            selected = report
    return selected


def _payload(view: MarketContextView) -> Mapping[str, object]:
    return {
        "as_of": view.as_of,
        "knowledge_cutoff": view.knowledge_cutoff,
        "publication_cutoff": view.publication_cutoff,
        "source_snapshot_set_id": view.source_snapshot_set_id,
        "source_snapshot_ids": view.source_snapshot_ids,
        "status": view.status,
        "feature_set_id": view.feature_set_id,
        "feature_version": view.feature_version,
        "regime_label": view.regime_label,
        "regime_score": view.regime_score,
        "drivers": view.drivers,
        "metrics": view.metrics,
        "impacts": view.impacts,
        "missing_inputs": view.missing_inputs,
        "data_conflicts": view.data_conflicts,
        "uncertainties": view.uncertainties,
        "evidence_refs": view.evidence_refs,
    }


class MarketContextEvidenceQueryFacade:
    """Resolve the approved PIT certification set before reading MarketContext."""

    def __init__(
        self,
        *,
        certification_reader: CertificationReader,
        market_context: MarketContextFacade,
        certification_profile: str,
    ) -> None:
        if (
            not certification_profile
            or certification_profile.strip() != certification_profile
        ):
            raise AppConfigurationError(
                "market context certification_profile must be canonical"
            )
        self._certification_reader = certification_reader
        self._market_context = market_context
        self._profile = certification_profile

    def get_evidence(
        self,
        *,
        context: EvidenceTemporalContext,
    ) -> MarketContextEvidenceReadModel:
        """Read a context only when the host identity matches certified history."""
        reports = tuple(
            report
            for dataset_id in _MARKET_CONTEXT_DATASETS
            if (
                report := _approved_report_at(
                    self._certification_reader,
                    dataset_id=dataset_id,
                    profile=self._profile,
                    knowledge_cutoff=context.knowledge_cutoff,
                )
            )
            is not None
        )
        certified_datasets = frozenset(report.dataset_id for report in reports)
        missing_core = tuple(sorted(_REQUIRED_DATASETS - certified_datasets))
        if missing_core:
            raise _error(
                "MARKET_CONTEXT_CERTIFICATION_REQUIRED",
                "certified_core_dataset_missing",
                missing_datasets=missing_core,
                profile=self._profile,
            )
        snapshot_ids = tuple(
            sorted(
                {
                    snapshot_id
                    for report in reports
                    for snapshot_id in report.evidence.snapshot_ids
                }
            )
        )
        snapshot_set_id = aggregate_source_snapshot_ids(snapshot_ids)
        if snapshot_set_id is None:
            raise _error(
                "MARKET_CONTEXT_SNAPSHOT_REQUIRED",
                "certified_snapshot_set_empty",
                profile=self._profile,
            )
        if snapshot_set_id != context.source_snapshot_id:
            raise _error(
                "MARKET_CONTEXT_SNAPSHOT_MISMATCH",
                "host_snapshot_set_does_not_match_certified_history",
                expected_snapshot_set_id=snapshot_set_id,
                actual_snapshot_set_id=context.source_snapshot_id,
            )
        view = self._market_context.get_context(
            MarketContextRequest(
                as_of=context.decision_time,
                knowledge_cutoff=context.knowledge_cutoff,
                publication_cutoff=context.publication_cutoff,
                source_snapshot_ids=snapshot_ids,
            )
        )
        if (
            view.source_snapshot_ids != snapshot_ids
            or view.source_snapshot_set_id != snapshot_set_id
        ):
            raise _error(
                "MARKET_CONTEXT_PROVENANCE_MISMATCH",
                "market_context_changed_source_snapshot_set",
            )
        payload = EvidencePayloadReadModel.seal(
            schema_version=1,
            value=_payload(view),
        )
        ordered_reports = tuple(sorted(reports, key=lambda item: item.report_id))
        lineage = tuple(
            dict.fromkeys(
                (
                    f"market-context:{view.feature_set_id}",
                    *(
                        f"certification:{report.report_id}"
                        for report in ordered_reports
                    ),
                    *(f"snapshot:{snapshot_id}" for snapshot_id in snapshot_ids),
                    *view.evidence_refs,
                )
            )
        )
        return MarketContextEvidenceReadModel(
            status=view.status,
            source_snapshot_set_id=snapshot_set_id,
            source_snapshot_ids=snapshot_ids,
            temporal_context=context,
            payload=payload,
            artifact_refs=tuple(
                EvidenceArtifactReference(
                    artifact_id=report.report_id,
                    artifact_kind="dataset_certification",
                    content_hash=report.content_hash,
                )
                for report in ordered_reports
            ),
            lineage=lineage,
        )
