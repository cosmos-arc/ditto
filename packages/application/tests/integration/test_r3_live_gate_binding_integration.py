"""Integration coverage for binding verified R2 live evidence into an R3 packet."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import cast

import pytest
from ditto_analysis.experiments import (
    CandidateId,
    ContentHash,
    ExperimentId,
    GateOutcome,
    HardGateEvidenceView,
    LogicalTrialIdentity,
    ObjectiveMetric,
    PromotionObjective,
    ResearchMetricDirection,
    ResearchMetricId,
    ResearchMetricValue,
    TrialFamilyDeclaration,
    TrialKind,
    collect_hard_gate_evidence,
)
from ditto_analysis.storage.sqlite.experiments import (
    ResearchExperimentDatabase,
    SQLiteExperimentReader,
)
from ditto_application.processes.experiments.coordinator import SchedulerTickState
from ditto_application.processes.experiments.evidence import (
    ReviewPacketInput,
    assemble_review_packet,
)
from ditto_application.processes.experiments.evidence_collector import (
    project_r2_live_gate_fact,
)
from ditto_application.processes.experiments.r2_live_gate_evidence import (
    FileR2LiveGateEvidenceReader,
    R2LiveGateEvidenceSource,
)
from packages.application.tests.integration import (
    r3_evidence_closure_support as golden_support,
)
from packages.application.tests.integration import (
    test_r3_evidence_closure_golden as closure_golden,
)
from packages.application.tests.integration.r2_live_gate_binding_support import (
    ready_source,
)


def _objective() -> PromotionObjective:
    candidate_id = CandidateId("candidate-live")
    return PromotionObjective(
        primary=ObjectiveMetric(
            ResearchMetricId.NET_RETURN,
            ResearchMetricDirection.MAXIMIZE,
        ),
        hard_constraints=(),
        tie_break_order=(),
        baseline_candidate_id=candidate_id,
        economic_rationale="Verify the exact live evidence binding.",
        trial_family=TrialFamilyDeclaration(
            "family-live",
            (
                LogicalTrialIdentity(
                    ExperimentId("experiment-live"),
                    candidate_id,
                    1,
                    ContentHash("1" * 64),
                    TrialKind.CURRENT,
                ),
            ),
        ),
    )


def _packet(source: R2LiveGateEvidenceSource):
    live_fact = project_r2_live_gate_fact(FileR2LiveGateEvidenceReader(source))
    hard_evidence = collect_hard_gate_evidence(
        HardGateEvidenceView(
            certified_snapshot=True,
            snapshot_id="snapshot-live-1",
            eligible_month_count=96,
            pit_policy="sample_time",
            purge_embargo_configured=True,
            reproduction_fingerprints=(ContentHash("2" * 64),),
            cost_config_hashes=(ContentHash("3" * 64),),
            baseline_candidate_id="candidate-live",
            trial_count=1,
            expected_trial_count=1,
            holdout_claim_id="claim-live",
            artifact_complete=True,
            artifact_missing=(),
            r2_live_gate=live_fact,
        )
    )
    return assemble_review_packet(
        ReviewPacketInput(
            experiment_id="experiment-live",
            candidate_id="candidate-live",
            fold_ids=("fold-live",),
            attempt_ids=("attempt-live",),
            spec_hash=ContentHash("4" * 64),
            resolved_spec_hash=ContentHash("5" * 64),
            parameter_hash=ContentHash("6" * 64),
            snapshot_hash=ContentHash("7" * 64),
            registry_hash=ContentHash("8" * 64),
            objective=_objective(),
            objective_payload_hash=ContentHash("9" * 64),
            hard_evidence=hard_evidence,
            metric_values={
                ResearchMetricId.NET_RETURN: ResearchMetricValue(
                    ResearchMetricId.NET_RETURN,
                    0.12,
                )
            },
            comparison_payload_hash=None,
            r1_impact_payload_hash=None,
            selection_evidence_artifact_id="selection-live",
            holdout_claim_id="claim-live",
            candidate_rationale="Exact verified R2 live evidence is attached.",
            selection_trace_artifact_refs=(),
            selection_exposure=None,
        )
    )


def test_verified_live_report_is_bound_into_the_persistable_packet(
    tmp_path: Path,
) -> None:
    source = ready_source(tmp_path)

    packet = _packet(source)

    gate = next(
        item for item in packet.gate_evaluations if item.rule_id == "r2_live_gate"
    )
    assert gate.outcome is GateOutcome.PASS
    assert gate.observed["report_uri"] == source.report_uri
    assert gate.observed["report_hash"] == str(source.expected_report_hash)
    assert gate.observed["checked_at"] == "2026-07-31T12:00:00+00:00"
    assert gate.observed["status"] == "ready"
    assert gate.observed["reason_codes"] == ()
    assert gate.observed["provider_entitlement_evidence_refs"] == (
        {
            "artifact_uri": source.provider_entitlement_artifacts[0].artifact_uri,
            "content_hash": str(
                source.provider_entitlement_artifacts[0].expected_content_hash
            ),
        },
    )
    assert gate.observed["performance_evidence_refs"]
    assert gate.observed["recoverability_evidence_refs"]
    assert gate.observed["idempotency_evidence_refs"]
    bundle_hash = packet.bundle_hash
    observed = cast("dict[str, object]", gate.observed)
    with pytest.raises(TypeError):
        observed["report_hash"] = "forged"
    assert packet.bundle_hash == bundle_hash


def test_artifact_byte_drift_cannot_produce_a_live_pass_packet(tmp_path: Path) -> None:
    source = ready_source(tmp_path)
    source.recoverability_artifacts[0].path.write_bytes(b"drifted")

    packet = _packet(source)

    gate = next(
        item for item in packet.gate_evaluations if item.rule_id == "r2_live_gate"
    )
    assert gate.outcome is GateOutcome.NOT_EVALUATED
    assert gate.observed == {
        "status": "not_evaluated",
        "reason_code": "r2_live_evidence_unavailable",
    }


def test_verified_live_gate_survives_real_collector_persistence_and_reopen(
    tmp_path: Path,
) -> None:
    """Bind exact live bytes through the real collector and SQLite readback."""
    source = ready_source(tmp_path / "r2-live")
    database, reader, writer, launch, assembler, artifact_service = (
        closure_golden._store(
            tmp_path,
            lane=golden_support.ETF_GOLDEN_LANE,
        )
    )
    coordinator, store, _collector, selection = (
        closure_golden._coordinator_with_collector(
            reader,
            writer,
            launch,
            assembler,
            artifact_service,
            r2_live_gate_evidence_reader=FileR2LiveGateEvidenceReader(source),
        )
    )
    selection_projection = store.load_snapshot(launch.experiment_id).projection
    coordinator.claim_holdout_candidate(
        closure_golden._application_request(
            launch,
            selection.ledger,
            expected_revision=selection_projection.revision,
            occurred_at=closure_golden.NOW + timedelta(seconds=40),
        ),
    )
    dispatch = coordinator.tick(
        occurred_at=closure_golden.NOW + timedelta(seconds=41)
    ).dispatches[0]
    coordinator.start_attempt(
        dispatch,
        occurred_at=closure_golden.NOW + timedelta(seconds=42),
    )
    coordinator.complete_attempt(
        dispatch.attempt.spec.attempt_id,
        occurred_at=closure_golden.NOW + timedelta(seconds=43),
    )

    result = coordinator.tick(occurred_at=closure_golden.NOW + timedelta(seconds=44))
    row = (
        database.get_connection()
        .execute(
            "SELECT reproduction_fingerprint FROM research_artifact "
            "WHERE artifact_kind='review_packet'"
        )
        .fetchone()
    )
    assert row is not None
    bundle_hash = row["reproduction_fingerprint"]
    packet = reader.get_review_packet(bundle_hash)
    assert result.state is SchedulerTickState.COMPLETED
    assert packet is not None
    gate = next(
        item for item in packet.gate_evaluations if item.rule_id == "r2_live_gate"
    )
    assert gate.outcome is GateOutcome.PASS
    assert gate.observed["report_hash"] == source.expected_report_hash
    assert gate.observed["checked_at"] == "2026-07-31T12:00:00+00:00"
    assert gate.observed["provider_entitlement_evidence_refs"]
    assert gate.observed["performance_evidence_refs"]
    assert gate.observed["recoverability_evidence_refs"]
    assert gate.observed["idempotency_evidence_refs"]
    assert str(packet.bundle_hash) == bundle_hash

    database.close_all()
    reopened_database = ResearchExperimentDatabase(tmp_path)
    reopened_database.initialize()
    reopened_reader = SQLiteExperimentReader(reopened_database)
    assert reopened_reader.get_review_packet(bundle_hash) == packet
    reopened_database.close_all()
