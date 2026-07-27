"""Unit tests for the strategy promotion process."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from ditto_analysis.experiments import (
    HARD_GATE_RULE_IDS,
    REVIEW_PACKET_SCHEMA_VERSION,
    REVIEW_PACKET_SCHEMA_VERSION_V1,
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
    gate_evaluations: tuple[GateEvaluation, ...] | None = None,
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
            _hard_gate_evaluations() if gate_evaluations is None else gate_evaluations
        ),
        comparison_payload_hash=ContentHash("9" * 64),
        r1_impact_payload_hash=None,
        selection_evidence_artifact_id="artifact-1",
        holdout_claim_id=holdout_claim_id,
        candidate_rationale="Captures durable net return after costs.",
    )


def _hard_gate_evaluations(
    outcome: GateOutcome = GateOutcome.PASS,
) -> tuple[GateEvaluation, ...]:
    return tuple(
        GateEvaluation(
            rule_id=rule_id,
            layer=GateLayer.HARD,
            outcome=outcome,
            observed="verified",
            policy={"required": True},
        )
        for rule_id in HARD_GATE_RULE_IDS
    )


def _request(
    packet: ReviewPacket,
    *,
    expected_bundle_hash: str | None = None,
    expected_strategy_spec_hash: str = "a" * 64,
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
        expected_strategy_spec_hash=expected_strategy_spec_hash,
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


def test_promote_rejects_legacy_v1_before_any_governance_io() -> None:
    governance = MagicMock(spec=GovernanceService)
    process = StrategyPromotionProcess(governance)
    packet = replace(
        _packet(),
        schema_version=REVIEW_PACKET_SCHEMA_VERSION_V1,
    )

    with pytest.raises(AppProcessError) as exc:
        process.promote(_request(packet))

    assert exc.value.details["reason"] == "review_packet_schema_unsupported"
    governance.assert_not_called()
    assert governance.mock_calls == []


def test_promote_rejects_packet_for_different_strategy_spec_before_write(
    tmp_path: Path,
) -> None:
    governance = _governance(tmp_path)
    _seed_approved_version(governance)
    process = StrategyPromotionProcess(governance)
    state_before = governance._store.get_state("strategy-1", 1)
    packet = _packet()

    with pytest.raises(AppProcessError) as exc:
        process.promote(_request(packet, expected_strategy_spec_hash="9" * 64))

    assert exc.value.details["reason"] == "strategy_spec_hash_mismatch"
    assert governance._store.get_state("strategy-1", 1) == state_before
    assert governance._store.get_active_pointer("strategy-1") is None


def test_promote_rejects_unregistered_target_before_write(tmp_path: Path) -> None:
    governance = _governance(tmp_path)
    process = StrategyPromotionProcess(governance)

    with pytest.raises(AppProcessError) as exc:
        process.promote(_request(_packet()))

    assert exc.value.details["reason"] == "strategy_version_not_found"
    assert governance._store.get_active_pointer("strategy-1") is None


@pytest.mark.parametrize(
    "hard_outcome",
    [GateOutcome.FAIL, GateOutcome.WARN, GateOutcome.NOT_EVALUATED],
)
def test_promote_rejects_when_hard_gate_is_not_explicit_pass(
    tmp_path: Path,
    hard_outcome: GateOutcome,
) -> None:
    governance = _governance(tmp_path)
    _seed_approved_version(governance)
    process = StrategyPromotionProcess(governance)
    state_before = governance._store.get_state("strategy-1", 1)

    packet = _packet(gate_evaluations=_hard_gate_evaluations(hard_outcome))
    with pytest.raises(AppProcessError) as exc:
        process.promote(_request(packet))

    assert exc.value.details["reason"] == "hard_gate_blocked"
    assert governance._store.get_state("strategy-1", 1) == state_before
    assert governance._store.get_active_pointer("strategy-1") is None


def test_promote_rejects_missing_hard_gate_before_governance_write(
    tmp_path: Path,
) -> None:
    governance = _governance(tmp_path)
    _seed_approved_version(governance)
    process = StrategyPromotionProcess(governance)
    state_before = governance._store.get_state("strategy-1", 1)

    packet = _packet(gate_evaluations=_hard_gate_evaluations()[:-1])
    with pytest.raises(AppProcessError) as exc:
        process.promote(_request(packet))

    assert exc.value.details["reason"] == "hard_gate_blocked"
    assert governance._store.get_state("strategy-1", 1) == state_before
    assert governance._store.get_active_pointer("strategy-1") is None


def test_promote_rejects_duplicate_hard_gate_before_governance_write(
    tmp_path: Path,
) -> None:
    governance = _governance(tmp_path)
    _seed_approved_version(governance)
    process = StrategyPromotionProcess(governance)
    state_before = governance._store.get_state("strategy-1", 1)
    hard_gates = _hard_gate_evaluations()

    packet = _packet(gate_evaluations=(*hard_gates, hard_gates[-1]))
    with pytest.raises(AppProcessError) as exc:
        process.promote(_request(packet))

    assert exc.value.details["reason"] == "hard_gate_blocked"
    assert governance._store.get_state("strategy-1", 1) == state_before
    assert governance._store.get_active_pointer("strategy-1") is None


def test_promote_rejects_reordered_hard_gates_before_governance_write(
    tmp_path: Path,
) -> None:
    governance = _governance(tmp_path)
    _seed_approved_version(governance)
    process = StrategyPromotionProcess(governance)
    state_before = governance._store.get_state("strategy-1", 1)
    hard_gates = _hard_gate_evaluations()

    packet = _packet(gate_evaluations=(hard_gates[1], hard_gates[0], *hard_gates[2:]))
    with pytest.raises(AppProcessError) as exc:
        process.promote(_request(packet))

    assert exc.value.details["reason"] == "hard_gate_blocked"
    assert governance._store.get_state("strategy-1", 1) == state_before
    assert governance._store.get_active_pointer("strategy-1") is None


def test_promote_rejects_extra_hard_gate_before_governance_write(
    tmp_path: Path,
) -> None:
    governance = _governance(tmp_path)
    _seed_approved_version(governance)
    process = StrategyPromotionProcess(governance)
    state_before = governance._store.get_state("strategy-1", 1)
    extra_gate = GateEvaluation(
        rule_id="unexpected_hard_gate",
        layer=GateLayer.HARD,
        outcome=GateOutcome.PASS,
        observed="verified",
        policy={"required": True},
    )

    packet = _packet(gate_evaluations=(*_hard_gate_evaluations(), extra_gate))
    with pytest.raises(AppProcessError) as exc:
        process.promote(_request(packet))

    assert exc.value.details["reason"] == "hard_gate_blocked"
    assert governance._store.get_state("strategy-1", 1) == state_before
    assert governance._store.get_active_pointer("strategy-1") is None


def test_promote_rejects_wrong_hard_gate_layer_before_governance_write(
    tmp_path: Path,
) -> None:
    governance = _governance(tmp_path)
    _seed_approved_version(governance)
    process = StrategyPromotionProcess(governance)
    state_before = governance._store.get_state("strategy-1", 1)
    hard_gates = _hard_gate_evaluations()
    wrong_layer = replace(hard_gates[-1], layer=GateLayer.EVIDENCE)

    packet = _packet(gate_evaluations=(*hard_gates, wrong_layer))
    with pytest.raises(AppProcessError) as exc:
        process.promote(_request(packet))

    assert exc.value.details["reason"] == "hard_gate_blocked"
    assert governance._store.get_state("strategy-1", 1) == state_before
    assert governance._store.get_active_pointer("strategy-1") is None


def test_promote_requires_holdout_claim(tmp_path: Path) -> None:
    governance = _governance(tmp_path)
    _seed_approved_version(governance)
    process = StrategyPromotionProcess(governance)

    packet = _packet(holdout_claim_id=None)
    with pytest.raises(AppProcessError) as exc:
        process.promote(_request(packet))

    assert exc.value.details["reason"] == "holdout_missing"
