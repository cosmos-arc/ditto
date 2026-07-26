"""Unit tests for evidence-gated strategy version publish command."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from ditto_analysis.experiments import ContentHash
from ditto_analysis.experiments.evidence import (
    REVIEW_PACKET_SCHEMA_VERSION,
    ReviewPacket,
    ReviewPacketLineage,
)
from ditto_analysis.experiments.gates import GateEvaluation, GateLayer, GateOutcome
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


def test_publish_strategy_version_handler_promotes() -> None:
    reader = MagicMock(spec=ReviewPacketReader)
    reader.get_review_packet.return_value = _packet()
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


def test_publish_strategy_version_handler_packet_not_found() -> None:
    reader = MagicMock(spec=ReviewPacketReader)
    reader.get_review_packet.return_value = None
    process = MagicMock(spec=StrategyPromotionProcess)
    handler = PublishStrategyVersionHandler(process=process, reader=reader)

    with pytest.raises(AppCommandError) as info:
        handler.handle(_command())

    assert info.value.details["code"] == "REVIEW_PACKET_NOT_FOUND"


def test_publish_strategy_version_handler_maps_process_error() -> None:
    reader = MagicMock(spec=ReviewPacketReader)
    reader.get_review_packet.return_value = _packet()
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
