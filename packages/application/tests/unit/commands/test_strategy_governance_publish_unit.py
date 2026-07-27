"""Unit tests for evidence-gated strategy version publish command."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from ditto_analysis.experiments import ContentHash, StrategyVersion
from ditto_analysis.experiments.evidence import (
    REVIEW_PACKET_SCHEMA_VERSION,
    ReviewPacket,
    ReviewPacketLineage,
)
from ditto_analysis.experiments.gates import GateEvaluation, GateLayer, GateOutcome
from ditto_application.commands import strategy_governance as governance_commands
from ditto_application.commands.strategy_governance import (
    PublishStrategyVersionCommand,
    PublishStrategyVersionHandler,
    ReviewPacketReader,
)
from ditto_application.exceptions import AppCommandError, AppProcessError
from ditto_application.processes.strategy.promotion import (
    PromotionResult,
    StrategyPromotionProcess,
)
from ditto_strategy.governance.models import StrategyActivePointer
from ditto_strategy.storage.sqlite.strategy_governance_store import (
    StrategyGovernanceCasConflict,
)

_BUNDLE = "a" * 64


def _packet() -> ReviewPacket:
    return ReviewPacket(
        schema_version=REVIEW_PACKET_SCHEMA_VERSION,
        lineage=ReviewPacketLineage(
            experiment_id="exp-1",
            candidate_id="c1",
            fold_ids=("f1",),
            attempt_ids=("a1",),
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
                outcome=GateOutcome.PASS,
                observed="verified",
                policy={},
            ),
        ),
        comparison_payload_hash=None,
        r1_impact_payload_hash=None,
        selection_evidence_artifact_id=None,
        holdout_claim_id="claim-1",
        candidate_rationale="net return after costs.",
    )


def _command() -> PublishStrategyVersionCommand:
    return PublishStrategyVersionCommand(
        strategy_id="s1",
        version=1,
        bundle_hash=_BUNDLE,
        actor="analyst",
        reason="promotion",
    )


def _reader(
    *,
    packet: ReviewPacket | None,
    strategy_version: str = "s1@1",
    launch_spec_hash: str = "a" * 64,
    strategy_spec_hash: str = "b" * 64,
) -> MagicMock:
    reader = MagicMock(spec=ReviewPacketReader)
    reader.get_review_packet.return_value = packet
    reader.get_launch_spec.return_value = SimpleNamespace(
        strategy_version=StrategyVersion(strategy_version),
        strategy_spec_hash=ContentHash(strategy_spec_hash),
        launch_spec_hash=ContentHash(launch_spec_hash),
    )
    return reader


@pytest.fixture(autouse=True)
def _encode_test_launch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        governance_commands,
        "encode_launch_spec",
        lambda launch: SimpleNamespace(content_hash=launch.launch_spec_hash),
    )


def test_publish_strategy_version_handler_promotes() -> None:
    reader = _reader(packet=_packet())
    process = MagicMock(spec=StrategyPromotionProcess)
    process.promote.return_value = PromotionResult(
        strategy_id="s1",
        version=1,
        bundle_hash=ContentHash(_BUNDLE),
        active_pointer=StrategyActivePointer("s1", 1, 0, "event-1"),
    )
    handler = PublishStrategyVersionHandler(process=process, reader=reader)

    result = handler.handle(_command())

    assert result.strategy_id == "s1"
    assert result.active_version == 1
    process.promote.assert_called_once()
    request = process.promote.call_args.args[0]
    assert request.expected_strategy_spec_hash == "b" * 64


def test_publish_strategy_version_handler_packet_not_found() -> None:
    reader = _reader(packet=None)
    process = MagicMock(spec=StrategyPromotionProcess)
    handler = PublishStrategyVersionHandler(process=process, reader=reader)

    with pytest.raises(AppCommandError) as info:
        handler.handle(_command())

    assert info.value.details["code"] == "REVIEW_PACKET_NOT_FOUND"


def test_publish_strategy_version_handler_experiment_not_found() -> None:
    reader = _reader(packet=_packet())
    reader.get_launch_spec.return_value = None
    process = MagicMock(spec=StrategyPromotionProcess)
    handler = PublishStrategyVersionHandler(process=process, reader=reader)

    with pytest.raises(AppCommandError) as info:
        handler.handle(_command())

    assert info.value.details["reason"] == "evidence_experiment_not_found"
    process.promote.assert_not_called()


def test_publish_strategy_version_handler_maps_process_error() -> None:
    reader = _reader(packet=_packet())
    process = MagicMock(spec=StrategyPromotionProcess)
    process.promote.side_effect = AppProcessError(
        "stale",
        details={"code": "STALE_EVIDENCE_BUNDLE", "reason": "stale_evidence_bundle"},
    )
    handler = PublishStrategyVersionHandler(process=process, reader=reader)

    with pytest.raises(AppCommandError) as info:
        handler.handle(_command())

    assert info.value.details["code"] == "STALE_EVIDENCE_BUNDLE"
    assert info.value.details["strategy_id"] == "s1"


def test_publish_strategy_version_handler_maps_atomic_promotion_conflict() -> None:
    """A concurrent atomic CAS miss must not escape the application boundary."""
    reader = _reader(packet=_packet())
    process = MagicMock(spec=StrategyPromotionProcess)
    process.promote.side_effect = StrategyGovernanceCasConflict(
        "active pointer revision changed"
    )
    handler = PublishStrategyVersionHandler(process=process, reader=reader)

    with pytest.raises(AppCommandError) as info:
        handler.handle(_command())

    assert info.value.details["code"] == "STRATEGY_REVISION_CONFLICT"
    assert info.value.details["strategy_id"] == "s1"
    assert info.value.details["version"] == 1


def test_publish_strategy_version_handler_rejects_cross_version_packet() -> None:
    reader = _reader(packet=_packet(), strategy_version="s1@2")
    process = MagicMock(spec=StrategyPromotionProcess)
    handler = PublishStrategyVersionHandler(process=process, reader=reader)

    with pytest.raises(AppCommandError) as info:
        handler.handle(_command())

    assert info.value.details["reason"] == "evidence_target_mismatch"
    process.promote.assert_not_called()


def test_publish_strategy_version_handler_rejects_launch_spec_hash_drift() -> None:
    reader = _reader(packet=_packet(), launch_spec_hash="9" * 64)
    process = MagicMock(spec=StrategyPromotionProcess)
    handler = PublishStrategyVersionHandler(process=process, reader=reader)

    with pytest.raises(AppCommandError) as info:
        handler.handle(_command())

    assert info.value.details["reason"] == "evidence_target_mismatch"
    process.promote.assert_not_called()
