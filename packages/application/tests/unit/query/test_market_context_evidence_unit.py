from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

import pytest
from ditto_application.catalog_freshness import aggregate_source_snapshot_ids
from ditto_application.exceptions import AppQueryError
from ditto_application.queries.evidence_contracts import EvidenceTemporalContext
from ditto_application.queries.market_context import (
    MarketContextFacade,
    MarketContextMetric,
    MarketContextRequest,
    MarketContextView,
)
from ditto_application.queries.market_context_evidence import (
    MarketContextEvidenceQueryFacade,
)
from ditto_data.catalog.certification import (
    CertificationReader,
    CertificationReviewEvent,
)


class _Report:
    def __init__(
        self,
        *,
        dataset_id: str,
        report_id: str,
        snapshot_ids: tuple[str, ...],
        generated_at: datetime,
        content_hash: str,
    ) -> None:
        self.dataset_id = dataset_id
        self.profile = "research_daily"
        self.report_id = report_id
        self.generated_at = generated_at
        self.content_hash = content_hash
        self.evidence = type("Evidence", (), {"snapshot_ids": snapshot_ids})()


class _CertificationReader:
    def __init__(self, reports: tuple[_Report, ...]) -> None:
        self._reports = reports

    def list_reports(self, dataset_id: str, profile: str) -> tuple[_Report, ...]:
        assert profile == "research_daily"
        return tuple(item for item in self._reports if item.dataset_id == dataset_id)

    def list_events(self, report_id: str) -> tuple[CertificationReviewEvent, ...]:
        report = next(item for item in self._reports if item.report_id == report_id)
        approved_at = report.generated_at.replace(minute=report.generated_at.minute + 5)
        return (
            CertificationReviewEvent(
                event_id=1,
                report_id=report.report_id,
                dataset_id=report.dataset_id,
                profile=report.profile,
                action="approved",
                actor="data-owner",
                occurred_at=approved_at,
            ),
        )


class _MarketContextFacade:
    def __init__(self) -> None:
        self.requests: list[MarketContextRequest] = []

    def get_context(self, request: MarketContextRequest) -> MarketContextView:
        self.requests.append(request)
        snapshot_set_id = aggregate_source_snapshot_ids(request.source_snapshot_ids)
        assert snapshot_set_id is not None
        return MarketContextView(
            as_of=request.as_of,
            knowledge_cutoff=request.knowledge_cutoff,
            publication_cutoff=request.publication_cutoff,
            source_snapshot_ids=request.source_snapshot_ids,
            source_snapshot_set_id=snapshot_set_id,
            status="ready",
            feature_set_id="market-regime:sha256:test",
            feature_version="market-regime.v1",
            regime_label="risk_on",
            regime_score=0.28,
            drivers=(),
            metrics=(
                MarketContextMetric(
                    name="advance_decline_breadth",
                    category="a_share",
                    value=0.42,
                    unit="ratio",
                    trend="rising",
                    freshness="fresh",
                    evidence_ref="dataset://stock_daily/breadth@2026-08-31",
                ),
            ),
            impacts=(),
            missing_inputs=(),
            data_conflicts=(),
            uncertainties=(),
            evidence_refs=("dataset://stock_daily/breadth@2026-08-31",),
        )


def _context(source_snapshot_id: str) -> EvidenceTemporalContext:
    return EvidenceTemporalContext(
        decision_time=datetime(2026, 8, 31, 9, tzinfo=UTC),
        knowledge_cutoff=datetime(2026, 8, 31, 8, tzinfo=UTC),
        publication_cutoff=datetime(2026, 8, 31, 7, tzinfo=UTC),
        source_snapshot_id=source_snapshot_id,
    )


def _facade() -> tuple[MarketContextEvidenceQueryFacade, _MarketContextFacade]:
    reports = (
        _Report(
            dataset_id="stock_daily",
            report_id="report-stock",
            snapshot_ids=("snapshot-stock",),
            generated_at=datetime(2026, 8, 31, 6, tzinfo=UTC),
            content_hash="1" * 64,
        ),
        _Report(
            dataset_id="index_daily",
            report_id="report-index",
            snapshot_ids=("snapshot-index",),
            generated_at=datetime(2026, 8, 31, 6, 10, tzinfo=UTC),
            content_hash="2" * 64,
        ),
        _Report(
            dataset_id="global_index_daily",
            report_id="report-global",
            snapshot_ids=("snapshot-global",),
            generated_at=datetime(2026, 8, 31, 6, 20, tzinfo=UTC),
            content_hash="4" * 64,
        ),
        _Report(
            dataset_id="macro_indicators",
            report_id="report-future-macro",
            snapshot_ids=("snapshot-future-macro",),
            generated_at=datetime(2026, 8, 31, 8, 30, tzinfo=UTC),
            content_hash="3" * 64,
        ),
    )
    market = _MarketContextFacade()
    facade = MarketContextEvidenceQueryFacade(
        certification_reader=cast(CertificationReader, _CertificationReader(reports)),
        market_context=cast(MarketContextFacade, market),
        certification_profile="research_daily",
    )
    return facade, market


def test_market_context_evidence_resolves_only_certifications_visible_at_cutoff() -> (
    None
):
    facade, market = _facade()
    source_ids = ("snapshot-global", "snapshot-index", "snapshot-stock")
    snapshot_set_id = aggregate_source_snapshot_ids(source_ids)
    assert snapshot_set_id is not None

    result = facade.get_evidence(context=_context(snapshot_set_id))

    assert result.status == "ready"
    assert result.source_snapshot_ids == source_ids
    assert result.payload.value["regime_label"] == "risk_on"
    assert result.payload.value["metrics"] == (
        {
            "category": "a_share",
            "evidence_ref": "dataset://stock_daily/breadth@2026-08-31",
            "freshness": "fresh",
            "name": "advance_decline_breadth",
            "trend": "rising",
            "unit": "ratio",
            "value": 0.42,
        },
    )
    assert tuple(item.artifact_id for item in result.artifact_refs) == (
        "report-global",
        "report-index",
        "report-stock",
    )
    assert market.requests == [
        MarketContextRequest(
            as_of=datetime(2026, 8, 31, 9, tzinfo=UTC),
            knowledge_cutoff=datetime(2026, 8, 31, 8, tzinfo=UTC),
            publication_cutoff=datetime(2026, 8, 31, 7, tzinfo=UTC),
            source_snapshot_ids=source_ids,
        )
    ]


def test_market_context_evidence_rejects_host_snapshot_set_mismatch() -> None:
    facade, market = _facade()

    with pytest.raises(AppQueryError, match="snapshot_set"):
        facade.get_evidence(context=_context("snapshot-set:sha256:wrong"))

    assert market.requests == []
