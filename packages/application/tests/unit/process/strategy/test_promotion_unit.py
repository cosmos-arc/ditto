"""Unit tests for the strategy promotion process."""

from __future__ import annotations

from pathlib import Path

import pytest
from ditto_analysis.experiments import (
    REVIEW_PACKET_SCHEMA_VERSION,
    ContentHash,
    GateEvaluation,
    GateLayer,
    GateOutcome,
    ReviewPacket,
    ReviewPacketLineage,
)
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.strategy.promotion import (
    PromotionRequest,
    StrategyPromotionProcess,
)
from ditto_platform.foundation import SQLitePool
from ditto_strategy.governance.models import (
    GOVERNANCE_SCHEMA_VERSION,
    StrategyVersion,
)
from ditto_strategy.governance.service import GovernanceService
from ditto_strategy.storage.sqlite.strategy_governance_store import (
    SQLiteStrategyGovernanceStore,
)


def _governance(tmp_path: Path) -> GovernanceService:
    pool = SQLitePool(str(tmp_path / "governance.sqlite"))
    store = SQLiteStrategyGovernanceStore(pool)
    store.init_schema()
    return GovernanceService(store)


def _seed_approved_version(service: GovernanceService, version: int = 1) -> None:
    service._store.insert_version(
        StrategyVersion(
            strategy_id="strategy-1",
            version=version,
            parent_version=None,
            schema_version=GOVERNANCE_SCHEMA_VERSION,
            spec_hash="a" * 64,
            spec_json={"version": version},
            created_at="2026-07-23T00:00:00Z",
        )
    )
    service.submit_review(
        "strategy-1", version, event_id="e1", actor="r", reason="ok", decided_at="t1"
    )
    service.approve(
        "strategy-1", version, event_id="e2", actor="r", reason="ok", decided_at="t2"
    )


def _packet(
    *,
    holdout_claim_id: str | None = "claim-1",
    hard_outcome: GateOutcome = GateOutcome.PASS,
) -> ReviewPacket:
    return ReviewPacket(
        schema_version=REVIEW_PACKET_SCHEMA_VERSION,
        lineage=ReviewPacketLineage(
            experiment_id="experiment-1",
            candidate_id="candidate-1",
            fold_ids=("fold-1",),
            attempt_ids=("attempt-1",),
        ),
        spec_hash=ContentHash("a" * 64),
        resolved_spec_hash=ContentHash("b" * 64),
        parameter_hash=ContentHash("c" * 64),
        snapshot_hash=ContentHash("d" * 64),
        registry_hash=ContentHash("e" * 64),
        objective_payload_hash=ContentHash("f" * 64),
        gate_evaluations=(
            GateEvaluation(
                rule_id="certified_snapshot",
                layer=GateLayer.HARD,
                outcome=hard_outcome,
                observed="verified",
                policy={"required": True},
            ),
        ),
        comparison_payload_hash=ContentHash("9" * 64),
        r1_impact_payload_hash=None,
        selection_evidence_artifact_id="artifact-1",
        holdout_claim_id=holdout_claim_id,
        candidate_rationale="Captures durable net return after costs.",
    )


def _request(
    packet: ReviewPacket,
    *,
    expected_bundle_hash: str | None = None,
) -> PromotionRequest:
    return PromotionRequest(
        strategy_id="strategy-1",
        version=1,
        packet=packet,
        actor="publisher-1",
        reason="go live",
        decided_at="t3",
        expected_bundle_hash=str(packet.bundle_hash)
        if expected_bundle_hash is None
        else expected_bundle_hash,
    )


def test_promote_publishes_and_switches_active_pointer(tmp_path: Path) -> None:
    governance = _governance(tmp_path)
    _seed_approved_version(governance)
    process = StrategyPromotionProcess(governance)

    packet = _packet()
    result = process.promote(_request(packet))

    assert result.active_pointer.active_version == 1
    assert result.bundle_hash == str(packet.bundle_hash)


def test_promote_rejects_stale_evidence_bundle(tmp_path: Path) -> None:
    governance = _governance(tmp_path)
    _seed_approved_version(governance)
    process = StrategyPromotionProcess(governance)

    with pytest.raises(AppProcessError) as exc:
        process.promote(_request(_packet(), expected_bundle_hash="stale-hash"))

    assert exc.value.details["reason"] == "stale_evidence_bundle"


def test_promote_rejects_when_hard_gate_blocks(tmp_path: Path) -> None:
    governance = _governance(tmp_path)
    _seed_approved_version(governance)
    process = StrategyPromotionProcess(governance)

    packet = _packet(hard_outcome=GateOutcome.FAIL)
    with pytest.raises(AppProcessError) as exc:
        process.promote(_request(packet))

    assert exc.value.details["reason"] == "hard_gate_blocked"


def test_promote_requires_holdout_claim(tmp_path: Path) -> None:
    governance = _governance(tmp_path)
    _seed_approved_version(governance)
    process = StrategyPromotionProcess(governance)

    packet = _packet(holdout_claim_id=None)
    with pytest.raises(AppProcessError) as exc:
        process.promote(_request(packet))

    assert exc.value.details["reason"] == "holdout_missing"
