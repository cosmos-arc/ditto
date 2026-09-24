"""ETF allocation drafts retain exact weights, revision lineage and retry identity."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from ditto_application.etf_paper_contracts import (
    ETFPaperHandoffFacts,
    ETFPaperHandoffRequest,
)
from ditto_application.etf_paper_handoff import ETFPaperHandoff
from ditto_application.exceptions import (
    AppCommandError,
    AppConflictError,
    AppProcessError,
)
from ditto_application.processes.portfolio.etf_allocation import (
    ETFAllocationCommand,
    ETFAllocationRequest,
    ETFAllocationReviewRequest,
    ETFPaperAuthorizationRequest,
)
from ditto_application.queries.etf_candidates import ETFCandidate, ETFField
from ditto_application.queries.etf_paper_handoff_facts import LiveETFPaperHandoffFacts
from ditto_application.queries.metadata import MetadataQueryFacade
from ditto_platform.foundation import SQLitePool
from ditto_strategy.models import ArtifactKind, StrategyArtifactRecord
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


def _receipt_id(version_id: str, idempotency_key: str) -> str:
    return f"{version_id}:review:" + sha256(idempotency_key.encode()).hexdigest()[:32]


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
        assert first.review_status == "research_only"
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
        assert command.review(submit).review_status == "review_pending"
        assert command.review(submit).review_status == "review_pending"
        with pytest.raises(AppConflictError):
            command.review(replace(approve, idempotency_key="submit-one"))
        assert command.review(approve).review_status == "review_approved"
        assert command.review(approve).review_status == "review_approved"
        assert command.review(submit).review_status == "review_approved"
        assert command.review(approve).paper_status == "research_only"
        approved_receipt = artifacts.get_artifact(
            _receipt_id(version.version_id, "approve-one")
        )
        assert approved_receipt is not None
        assert approved_receipt.artifact_type is ArtifactKind.DIAGNOSTICS
        assert "key_hash" in approved_receipt.metadata
        assert "idempotency_key" not in approved_receipt.metadata
        assert command.list_versions("demo")[0].review_status == "review_approved"
        with pytest.raises(AppConflictError):
            command.review(replace(approve, reason="different"))
        with pytest.raises(AppConflictError):
            command.review(replace(approve, version_id="other"))
        with pytest.raises(AppConflictError):
            command.review(
                replace(approve, action="reject", idempotency_key="approve-one")
            )
        revision = command.save(
            replace(
                _request(),
                idempotency_key="revision",
                parent_version_id=version.version_id,
            )
        )
        assert revision.review_status == "research_only"
        with pytest.raises(AppConflictError):
            command.review(replace(approve, version_id=revision.version_id))
        assert (
            command.review(
                replace(
                    submit, version_id=revision.version_id, idempotency_key="submit-two"
                )
            ).review_status
            == "review_pending"
        )
        existing_receipt = artifacts.get_artifact(
            _receipt_id(version.version_id, "approve-one")
        )
        assert existing_receipt is not None
        assert not artifacts.transition_with_receipt(
            revision.version_id, "approved", "review", existing_receipt
        )
        assert (
            next(
                item.review_status
                for item in command.list_versions("demo")
                if item.version_id == revision.version_id
            )
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
        assert rejected.review_status == "rejected"
        with pytest.raises(AppConflictError):
            command.review(
                replace(
                    approve,
                    version_id=revision.version_id,
                    idempotency_key="approve-two",
                )
            )
        assert (
            artifacts.get_artifact(_receipt_id(revision.version_id, "approve-two"))
            is None
        )
    finally:
        pool.close_all()


def test_review_validates_the_idempotency_key_at_the_shared_boundary(
    tmp_path: Path,
) -> None:
    pool = SQLitePool(str(tmp_path / "review-key.sqlite"))
    writer = SQLiteStrategyArtifactWriter(pool)
    writer.init_schema()
    metadata = MagicMock(spec=MetadataQueryFacade)
    metadata.list_etf_candidates.return_value = [_candidate(1), _candidate(2)]
    command = ETFAllocationCommand(
        metadata, StrategyArtifactService(SQLiteStrategyArtifactReader(pool), writer)
    )
    try:
        version = command.save(_request())
        review = ETFAllocationReviewRequest(
            allocation_id="demo",
            version_id=version.version_id,
            action="submit",
            actor="operator",
            reason="checked target",
            idempotency_key="bad key 空格",
        )
        with pytest.raises(AppCommandError, match="Idempotency-Key is invalid"):
            command.review(review)
    finally:
        pool.close_all()


def test_concurrent_identical_review_retries_return_the_committed_result(
    tmp_path: Path,
) -> None:
    pool = SQLitePool(str(tmp_path / "concurrent-review.sqlite"))
    writer = SQLiteStrategyArtifactWriter(pool)
    writer.init_schema()
    artifacts = StrategyArtifactService(SQLiteStrategyArtifactReader(pool), writer)
    metadata = MagicMock(spec=MetadataQueryFacade)
    metadata.list_etf_candidates.return_value = [_candidate(1), _candidate(2)]
    command = ETFAllocationCommand(metadata, artifacts)
    try:
        version = command.save(_request())
        review = ETFAllocationReviewRequest(
            allocation_id="demo",
            version_id=version.version_id,
            action="submit",
            actor="operator",
            reason="checked target",
            idempotency_key="submit-once",
        )
        barrier = Barrier(2)
        transition = artifacts.transition_with_receipt

        def race(
            artifact_id: str,
            status: str,
            expected_current: str,
            receipt: StrategyArtifactRecord,
        ) -> bool:
            barrier.wait(timeout=10)
            return transition(artifact_id, status, expected_current, receipt)

        with patch.object(artifacts, "transition_with_receipt", side_effect=race):
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [executor.submit(command.review, review) for _ in range(2)]
                assert [
                    future.result(timeout=15).review_status for future in futures
                ] == [
                    "review_pending",
                    "review_pending",
                ]
        assert (
            sum(
                record.artifact_id == _receipt_id(version.version_id, "submit-once")
                for record in artifacts.list_by_strategy("etf-allocation:demo")
            )
            == 1
        )
    finally:
        pool.close_all()


def test_paper_handoff_requires_separate_exact_authorization_and_current_facts(
    tmp_path: Path,
) -> None:
    pool = SQLitePool(str(tmp_path / "paper-handoff.sqlite"))
    writer = SQLiteStrategyArtifactWriter(pool)
    writer.init_schema()
    artifacts = StrategyArtifactService(SQLiteStrategyArtifactReader(pool), writer)
    metadata = MagicMock(spec=MetadataQueryFacade)
    metadata.list_etf_candidates.return_value = [_candidate(1), _candidate(2)]
    allocations = ETFAllocationCommand(metadata, artifacts)
    packages = MagicMock()
    packages.publish.return_value = MagicMock()
    packages.finalize.return_value = MagicMock(outcome="completed")
    sessions = MagicMock()
    facts = MagicMock()
    request = ETFPaperHandoffRequest(
        allocation_id="demo",
        version_id="",
        authorization_id="",
        account_id="paper-one",
        session_id="session-one",
        idempotency_key="handoff-one",
        signal_date="2026-09-01",
        decision_date="2026-09-01",
        intended_trade_date="2026-09-02",
        knowledge_cutoff=datetime.fromisoformat("2026-09-01T09:00:00+00:00"),
        source_snapshot_id="snapshot:recorded:market",
    )
    handoff = ETFPaperHandoff(
        allocations=allocations,
        facts=facts,
        packages=packages,
        sessions=sessions,
    )
    try:
        version = allocations.save(_request())
        request = replace(request, version_id=version.version_id)
        review = ETFAllocationReviewRequest(
            allocation_id="demo",
            version_id=version.version_id,
            action="submit",
            actor="reviewer",
            reason="reviewed",
            idempotency_key="submit",
        )
        allocations.review(review)
        allocations.review(replace(review, action="approve", idempotency_key="approve"))
        with pytest.raises(AppConflictError, match="target authorization"):
            handoff.handoff(request)
        approval = ETFPaperAuthorizationRequest(
            allocation_id="demo",
            version_id=version.version_id,
            account_id=request.account_id,
            session_id=request.session_id,
            intended_trade_date=request.intended_trade_date,
            actor="operator",
            reason="send to Paper",
            idempotency_key="paper-authorize",
        )
        receipt = allocations.authorize_paper(approval)
        assert allocations.authorize_paper(approval).artifact_id == receipt.artifact_id
        with pytest.raises(AppConflictError):
            allocations.authorize_paper(replace(approval, reason="different"))
        request = replace(request, authorization_id=receipt.artifact_id)
        with pytest.raises(AppCommandError, match="research decision"):
            handoff.handoff(replace(request, signal_date="2026-09-02"))
        with pytest.raises(AppCommandError, match="saved target cutoff"):
            handoff.handoff(
                replace(
                    request,
                    knowledge_cutoff=datetime.fromisoformat(
                        "2026-09-01T08:00:00+00:00"
                    ),
                )
            )
        with pytest.raises(AppConflictError, match="target authorization"):
            handoff.handoff(replace(request, account_id="other"))
        facts.resolve.return_value = ETFPaperHandoffFacts(
            signal_date=request.signal_date,
            knowledge_cutoff=request.knowledge_cutoff,
            source_snapshot_id=request.source_snapshot_id,
            current_positions={},
            investable_instrument_ids=frozenset({1}),
            signal_ledger_hash="ledger-before",
        )
        with pytest.raises(AppConflictError, match="choose alternatives"):
            handoff.handoff(request)
        packages.publish.assert_not_called()
        facts.resolve.return_value = replace(
            facts.resolve.return_value, investable_instrument_ids=frozenset({1, 2})
        )
        handoff.handoff(request)
        published = packages.publish.call_args.args[0]
        assert published.origin_version_id == version.version_id
        assert published.execution_scope == "paper"
        assert published.target.positions == {1: 0.4, 2: 0.4}
        assert sessions.start.call_count == 1
    finally:
        pool.close_all()


@pytest.mark.pit
def test_paper_handoff_fact_admission_excludes_future_publication() -> None:
    cutoff = datetime.fromisoformat("2026-09-02T08:00:00+00:00")
    field = ETFField(
        value="none",
        unit=None,
        observed_on="2026-09-02",
        published_at="2026-09-02T07:00:00Z",
        source="recorded",
        source_snapshot_id="snapshot:recorded:market",
        eligibility="display_allowed",
        missing_reason=None,
    )
    candidate = replace(
        _candidate(1),
        fields={
            "price_close": replace(field, value=10.0),
            "trading_restriction": field,
            "asset_class": replace(field, value="etf"),
            "trading_currency": replace(field, value="CNY"),
        },
    )
    metadata = MagicMock(spec=MetadataQueryFacade)
    metadata.list_etf_candidates.return_value = [candidate]
    admission = MagicMock()
    admission.assess.return_value = SimpleNamespace(allowed=True)
    snapshots = MagicMock()
    snapshots.get_snapshot.return_value = SimpleNamespace(
        snapshot_id="snapshot:recorded:market",
        dataset_id="etf_reference",
        created_at=datetime.fromisoformat("2026-09-02T06:00:00+00:00"),
    )
    ledger = MagicMock()
    ledger.get_paper.return_value = SimpleNamespace(
        events=(),
        snapshot=SimpleNamespace(
            valuation_complete=True,
            total_value=Decimal("1000"),
            positions=(),
        ),
    )
    facts = LiveETFPaperHandoffFacts(
        metadata=metadata,
        admission=admission,
        snapshots=snapshots,
        ledger=ledger,
    )
    request = ETFPaperHandoffRequest(
        allocation_id="demo",
        version_id="one",
        authorization_id="receipt",
        account_id="paper",
        session_id="session",
        idempotency_key="one",
        signal_date="2026-09-02",
        decision_date="2026-09-02",
        intended_trade_date="2026-09-03",
        knowledge_cutoff=cutoff,
        source_snapshot_id="snapshot:recorded:market",
    )
    assert facts.resolve(request).investable_instrument_ids == frozenset({1})
    at_cutoff = replace(
        candidate,
        fields={
            **candidate.fields,
            "trading_restriction": replace(field, published_at="2026-09-02T08:00:00Z"),
        },
    )
    metadata.list_etf_candidates.return_value = [at_cutoff]
    assert facts.resolve(request).investable_instrument_ids == frozenset({1})
    future = replace(
        candidate,
        fields={
            **candidate.fields,
            "trading_restriction": replace(field, published_at="2026-09-02T08:00:01Z"),
        },
    )
    metadata.list_etf_candidates.return_value = [future]
    assert facts.resolve(request).investable_instrument_ids == frozenset()
    snapshots.get_snapshot.return_value.created_at = datetime.fromisoformat(
        "2026-09-02T08:00:01+00:00"
    )
    with pytest.raises(AppProcessError, match="future"):
        facts.resolve(request)
