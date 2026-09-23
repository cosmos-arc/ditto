"""ETF allocation drafts retain exact weights, revision lineage and retry identity."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from ditto_application.exceptions import AppCommandError, AppConflictError
from ditto_application.processes.portfolio.etf_allocation import (
    ETFAllocationCommand,
    ETFAllocationRequest,
    ETFAllocationReviewRequest,
)
from ditto_application.queries.etf_candidates import ETFCandidate, ETFField
from ditto_application.queries.metadata import MetadataQueryFacade
from ditto_platform.foundation import SQLitePool
from ditto_strategy.storage.sqlite.services.strategy_artifact_service import (
    StrategyArtifactService,
)
from ditto_strategy.storage.sqlite.strategy_artifact_store import (
    SQLiteStrategyArtifactReader,
    SQLiteStrategyArtifactWriter,
)


def _candidate(instrument_id: int) -> ETFCandidate:
    tracking = ETFField(
        value="CSI300",
        unit=None,
        observed_on="2026-09-01",
        published_at="2026-09-01T07:00:00Z",
        source="recorded",
        source_snapshot_id="snapshot:recorded:etf",
        eligibility="RECORDED_REFERENCE_ONLY",
        missing_reason=None,
    )
    return ETFCandidate(
        instrument_id=instrument_id,
        ticker=f"51030{instrument_id}.SH",
        name=f"ETF {instrument_id}",
        exchange="SH",
        is_active=True,
        fields={"tracking_index": tracking},
    )


def _request() -> ETFAllocationRequest:
    return ETFAllocationRequest(
        allocation_id="demo",
        idempotency_key="one",
        parent_version_id=None,
        asof="2026-09-01",
        knowledge_cutoff="2026-09-01T09:00:00+00:00",
        source_snapshot_id="snapshot:recorded:etf",
        instrument_ids=(1, 2),
        mode="equal",
        cash_weight=Decimal("0.2"),
        max_position_weight=Decimal("0.5"),
        manual_weights={},
        reason="broad exposure",
    )


def test_save_revise_restore_and_reject_invalid_weights(tmp_path: Path) -> None:
    pool = SQLitePool(str(tmp_path / "allocation.sqlite"))
    writer = SQLiteStrategyArtifactWriter(pool)
    writer.init_schema()
    metadata = MagicMock(spec=MetadataQueryFacade)
    metadata.list_etf_candidates.return_value = [_candidate(1), _candidate(2)]
    service = ETFAllocationCommand(
        metadata, StrategyArtifactService(SQLiteStrategyArtifactReader(pool), writer)
    )
    try:
        first = service.save(_request())
        assert first.weights == {1: "0.40000000", 2: "0.40000000"}
        assert first.tracking_exposure == {"CSI300": "0.80000000"}
        assert first.paper_status == "research_only"
        assert service.save(_request()) == first
        metadata.list_etf_candidates.side_effect = RuntimeError("snapshot unavailable")
        assert service.save(_request()) == first
        with pytest.raises(AppConflictError):
            service.save(replace(_request(), reason="changed"))
        metadata.list_etf_candidates.side_effect = None
        assert len(service.list_versions("demo")) == 1
        manual = replace(
            _request(),
            idempotency_key="two",
            parent_version_id=first.version_id,
            mode="manual",
            manual_weights={1: Decimal("0.3"), 2: Decimal("0.5")},
        )
        second = service.save(manual)
        assert second.parent_version_id == first.version_id
        assert second.weights == {1: "0.3", 2: "0.5"}
        assert len(service.list_versions("demo")) == 2
        with pytest.raises(AppConflictError):
            service.save(replace(manual, reason="different"))
        with pytest.raises(AppCommandError, match="must equal one"):
            service.save(
                replace(
                    manual,
                    idempotency_key="three",
                    manual_weights={1: Decimal("0.2"), 2: Decimal("0.5")},
                )
            )
        metadata.list_etf_candidates.return_value = [_candidate(1)]
        with pytest.raises(AppCommandError, match="not visible at this snapshot"):
            service.save(
                replace(
                    manual,
                    idempotency_key="future",
                    parent_version_id=second.version_id,
                )
            )
        assert len(service.list_versions("demo")) == 2
    finally:
        pool.close_all()


def test_exact_version_review_is_explicit_durable_and_idempotent(
    tmp_path: Path,
) -> None:
    pool = SQLitePool(str(tmp_path / "review.sqlite"))
    writer = SQLiteStrategyArtifactWriter(pool)
    writer.init_schema()
    artifacts = StrategyArtifactService(SQLiteStrategyArtifactReader(pool), writer)
    metadata = MagicMock(spec=MetadataQueryFacade)
    metadata.list_etf_candidates.return_value = [_candidate(1), _candidate(2)]
    command = ETFAllocationCommand(metadata, artifacts)
    try:
        version = command.save(_request())
        approve = ETFAllocationReviewRequest(
            allocation_id="demo",
            version_id=version.version_id,
            action="approve",
            actor="operator",
            reason="checked target",
            idempotency_key="approve-one",
        )
        with pytest.raises(AppConflictError):
            command.review(approve)
        submit = replace(approve, action="submit", idempotency_key="submit-one")
        assert command.review(submit).paper_status == "review_pending"
        assert command.review(submit).paper_status == "review_pending"
        assert command.review(approve).paper_status == "review_approved"
        assert command.review(approve).paper_status == "review_approved"
        assert command.list_versions("demo")[0].paper_status == "review_approved"
        with pytest.raises(AppConflictError):
            command.review(replace(approve, reason="different"))
        with pytest.raises(AppConflictError):
            command.review(replace(approve, version_id="other"))
        revision = command.save(
            replace(
                _request(),
                idempotency_key="revision",
                parent_version_id=version.version_id,
            )
        )
        assert revision.paper_status == "research_only"
        with pytest.raises(AppConflictError):
            command.review(replace(approve, version_id=revision.version_id))
        assert (
            command.review(
                replace(
                    submit, version_id=revision.version_id, idempotency_key="submit-two"
                )
            ).paper_status
            == "review_pending"
        )
        rejected = command.review(
            replace(
                approve,
                version_id=revision.version_id,
                action="reject",
                idempotency_key="reject-two",
            )
        )
        assert rejected.paper_status == "rejected"
        with pytest.raises(AppConflictError):
            command.review(
                replace(
                    approve,
                    version_id=revision.version_id,
                    idempotency_key="approve-two",
                )
            )
    finally:
        pool.close_all()
