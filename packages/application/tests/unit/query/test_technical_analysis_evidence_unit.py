"""Exact technical-analysis evidence facade tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast

import pytest
from ditto_application.catalog_freshness import aggregate_source_snapshot_ids
from ditto_application.exceptions import AppQueryError
from ditto_application.queries.evidence_contracts import EvidenceTemporalContext
from ditto_application.queries.technical_analysis import (
    TechnicalAnalysisFacade,
    TechnicalAnalysisRequest,
)
from ditto_application.queries.technical_analysis_evidence import (
    InstrumentTechnicalEvidenceQuery,
    InstrumentTechnicalEvidenceQueryFacade,
)
from ditto_data.catalog.certification import CertificationReader
from ditto_features.technical_analysis.contracts import (
    TechnicalAnalysisSnapshot,
    TechnicalLevel,
    TechnicalLevelKind,
    TechnicalTimeframe,
)
from ditto_kernel.identity import InstrumentId


@dataclass(frozen=True)
class _Evidence:
    snapshot_ids: tuple[str, ...]


@dataclass(frozen=True)
class _Report:
    dataset_id: str
    report_id: str
    generated_at: datetime
    content_hash: str
    evidence: _Evidence


@dataclass(frozen=True)
class _Event:
    occurred_at: datetime
    action: str


class _Certifications:
    def __init__(self, *reports: _Report) -> None:
        self._reports = reports

    def list_reports(self, dataset_id: str, profile: str) -> list[_Report]:
        del profile
        return [report for report in self._reports if dataset_id == report.dataset_id]

    def list_events(self, report_id: str) -> list[_Event]:
        report = next(item for item in self._reports if item.report_id == report_id)
        return [_Event(report.generated_at, "approved")]


def _snapshot(request: TechnicalAnalysisRequest) -> TechnicalAnalysisSnapshot:
    return TechnicalAnalysisSnapshot(
        snapshot_id="technical-analysis:sha256:" + "a" * 64,
        input_hash="b" * 64,
        spec_hash="c" * 64,
        registry_version="technical-indicator-registry.v1",
        instrument_id=request.instrument_id,
        instrument_name=request.instrument_name,
        as_of=request.as_of,
        knowledge_cutoff=request.knowledge_cutoff,
        publication_cutoff=request.publication_cutoff,
        source_snapshot_ids=request.source_snapshot_ids,
        status="ready",
        last_visible_bar_at=request.as_of,
        last_computed_bar_at=request.as_of,
        readings=(),
        levels=(
            TechnicalLevel(
                timeframe=TechnicalTimeframe.DAILY,
                kind=TechnicalLevelKind.SUPPORT,
                price=97.5,
                confidence=0.75,
                touches=3,
                window=60,
                algorithm_version="support-resistance.v1",
            ),
        ),
        timeframe_summaries=(),
        conflicts=(),
        missing_inputs=(),
        warnings=(),
        selection_run_id=request.selection_run_id,
        research_case_id=request.research_case_id,
        portfolio_snapshot_id=request.portfolio_snapshot_id,
    )


class _TechnicalFacade:
    def __init__(self) -> None:
        self.requests: list[TechnicalAnalysisRequest] = []

    def get_snapshot(
        self,
        request: TechnicalAnalysisRequest,
    ) -> TechnicalAnalysisSnapshot:
        self.requests.append(request)
        return _snapshot(request)


def _context(snapshot_set_id: str) -> EvidenceTemporalContext:
    return EvidenceTemporalContext(
        decision_time=datetime(2026, 8, 31, 9, tzinfo=UTC),
        knowledge_cutoff=datetime(2026, 8, 31, 8, tzinfo=UTC),
        publication_cutoff=datetime(2026, 8, 31, 7, tzinfo=UTC),
        source_snapshot_id=snapshot_set_id,
    )


def _facade() -> tuple[InstrumentTechnicalEvidenceQueryFacade, _TechnicalFacade]:
    report = _Report(
        dataset_id="stock_daily",
        report_id="certification-stock",
        generated_at=datetime(2026, 8, 31, 6, tzinfo=UTC),
        content_hash="d" * 64,
        evidence=_Evidence(("snapshot-stock",)),
    )
    technical = _TechnicalFacade()
    return (
        InstrumentTechnicalEvidenceQueryFacade(
            certification_reader=cast(CertificationReader, _Certifications(report)),
            technical_analysis=cast(TechnicalAnalysisFacade, technical),
            certification_profile="research_daily",
        ),
        technical,
    )


def test_evidence_computes_exact_snapshot_and_preserves_only_recorded_levels() -> None:
    facade, technical = _facade()
    snapshot_set_id = aggregate_source_snapshot_ids(("snapshot-stock",))
    assert snapshot_set_id is not None

    result = facade.get_evidence(
        query=InstrumentTechnicalEvidenceQuery(
            instrument_id=InstrumentId(600519),
            instrument_name="贵州茅台",
            instrument_code="600519.SH",
            selection_run_id="selection-run:sha256:" + "e" * 64,
        ),
        context=_context(snapshot_set_id),
    )

    assert result.snapshot_id == "technical-analysis:sha256:" + "a" * 64
    assert result.payload.value["levels"] == (
        {
            "algorithm_version": "support-resistance.v1",
            "confidence": 0.75,
            "kind": "support",
            "price": 97.5,
            "timeframe": "daily",
            "touches": 3,
            "window": 60,
        },
    )
    assert tuple(item.artifact_kind for item in result.artifact_refs) == (
        "technical_analysis_snapshot",
        "dataset_certification",
    )
    assert technical.requests[0].source_snapshot_ids == ("snapshot-stock",)
    assert technical.requests[0].spec.timeframes == ("daily", "weekly")


def test_evidence_rejects_host_snapshot_mismatch_before_computation() -> None:
    facade, technical = _facade()

    with pytest.raises(AppQueryError, match="snapshot"):
        facade.get_evidence(
            query=InstrumentTechnicalEvidenceQuery(
                instrument_id=InstrumentId(600519),
                instrument_name="贵州茅台",
                instrument_code="600519.SH",
            ),
            context=_context("snapshot-future"),
        )

    assert technical.requests == []


def test_evidence_selects_approved_report_matching_exact_host_snapshot_set() -> None:
    historical = _Report(
        dataset_id="stock_daily",
        report_id="certification-historical",
        generated_at=datetime(2026, 8, 31, 5, tzinfo=UTC),
        content_hash="e" * 64,
        evidence=_Evidence(("snapshot-historical",)),
    )
    latest = _Report(
        dataset_id="stock_daily",
        report_id="certification-latest",
        generated_at=datetime(2026, 8, 31, 6, tzinfo=UTC),
        content_hash="f" * 64,
        evidence=_Evidence(("snapshot-latest",)),
    )
    technical = _TechnicalFacade()
    facade = InstrumentTechnicalEvidenceQueryFacade(
        certification_reader=cast(
            CertificationReader,
            _Certifications(historical, latest),
        ),
        technical_analysis=cast(TechnicalAnalysisFacade, technical),
        certification_profile="research_daily",
    )
    historical_set = aggregate_source_snapshot_ids(("snapshot-historical",))
    assert historical_set is not None

    result = facade.get_evidence(
        query=InstrumentTechnicalEvidenceQuery(
            instrument_id=InstrumentId(600519),
            instrument_name="贵州茅台",
            instrument_code="600519.SH",
        ),
        context=_context(historical_set),
    )

    assert technical.requests[0].source_snapshot_ids == ("snapshot-historical",)
    assert result.artifact_refs[1].artifact_id == "certification-historical"
