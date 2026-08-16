"""Lossless/PIT round trips for every governed-campaign SQLite fact family."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from ditto_analysis.errors import ExperimentPersistenceError
from ditto_analysis.experiments.campaign import ResearchCandidateSpec, SearchAxis
from ditto_analysis.experiments.campaign_persistence import (
    CampaignEventRecord,
    CampaignManifestRecord,
    CandidateLineageRecord,
    ResearchFeedbackRecord,
    SandboxExecutionRecord,
)
from ditto_analysis.experiments.generated_code import (
    ResearchCodeArtifact,
    SandboxExecutionManifest,
    SandboxExitStatus,
    SandboxResourceLimits,
)
from ditto_analysis.experiments.models import (
    AttemptId,
    CandidateId,
    ContentHash,
    ExperimentId,
    SnapshotId,
)
from ditto_analysis.experiments.research_memory import (
    KnowledgeItem,
    KnowledgeScope,
    KnowledgeSource,
    KnowledgeStatus,
    KnowledgeStatusEvent,
    ResearchFeedback,
)
from ditto_analysis.experiments.search_ledger import (
    OperationalAttempt,
    StatisticalTrial,
)
from ditto_analysis.experiments.specs import CandidateSpec
from ditto_analysis.experiments.trial_family import LogicalTrialIdentity, TrialKind
from ditto_analysis.storage.sqlite.experiments import (
    ResearchExperimentDatabase,
    SQLiteCampaignReader,
    SQLiteCampaignWriter,
)

KNOWN_AT = datetime(2026, 8, 12, 8, tzinfo=UTC)


def _hash(character: str) -> ContentHash:
    return ContentHash(character * 64)


def _campaign_record(
    campaign_id: str = "campaign-round-trip",
) -> CampaignManifestRecord:
    payload = json.dumps(
        {
            "campaign_id": campaign_id,
            "lineage_root": "d" * 64,
            "schema_id": "r5-research-campaign-manifest",
            "schema_version": 1,
            "search_axis": SearchAxis.FACTOR_CODE.value,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return CampaignManifestRecord(
        campaign_id=ExperimentId(campaign_id),
        manifest_hash=ContentHash(hashlib.sha256(payload).hexdigest()),
        manifest_payload=payload,
        search_axis=SearchAxis.FACTOR_CODE,
        lineage_root=_hash("d"),
        created_at_epoch_us=1_786_521_600_000_000,
    )


def _candidate_record() -> CandidateLineageRecord:
    return CandidateLineageRecord(
        campaign_id=_campaign_record().campaign_id,
        candidate=ResearchCandidateSpec(
            candidate=CandidateSpec(
                candidate_id=CandidateId("candidate-round-trip"),
                ordinal=1,
                is_baseline=True,
                parameters={"lookback": 20, "winsorize": True},
            ),
            search_axis=SearchAxis.FACTOR_CODE,
            parent_candidate_id=None,
            factor_code_hash=_hash("a"),
            model_code_hash=None,
            data_requirement_hashes=(_hash("b"),),
        ),
        generation=0,
        created_at_epoch_us=1_786_521_600_000_000,
    )


def _storage(tmp_path: Path) -> tuple[SQLiteCampaignWriter, SQLiteCampaignReader]:
    database = ResearchExperimentDatabase(tmp_path)
    database.initialize()
    return SQLiteCampaignWriter(database), SQLiteCampaignReader(database)


def test_campaign_event_candidate_and_search_ledger_round_trip(tmp_path: Path) -> None:
    writer, reader = _storage(tmp_path)
    campaign = _campaign_record()
    candidate = _candidate_record()
    event = CampaignEventRecord(
        event_id="campaign-event-0",
        campaign_id=campaign.campaign_id,
        ordinal=0,
        event_type="campaign_created",
        previous_status=None,
        status="draft",
        detail_payload=b'{"source":"test"}',
        occurred_at_epoch_us=campaign.created_at_epoch_us,
    )
    logical = LogicalTrialIdentity(
        origin_experiment_id=campaign.campaign_id,
        candidate_id=candidate.candidate.candidate.candidate_id,
        ordinal=1,
        parameter_hash=candidate.candidate.candidate.parameter_hash,
        kind=TrialKind.CURRENT,
    )
    trial = StatisticalTrial(
        logical_trial=logical,
        candidate_hash=candidate.candidate.candidate_hash,
        validation_protocol_hash=_hash("c"),
        lineage_root=campaign.lineage_root,
        family_id="family-round-trip",
    )
    attempt = OperationalAttempt(
        attempt_id=AttemptId("attempt-round-trip"),
        logical_trial=logical,
        ordinal=1,
        parent_attempt_id=None,
        lineage_root=campaign.lineage_root,
        family_id=trial.family_id,
    )

    writer.add_campaign(campaign)
    writer.append_campaign_event(event)
    writer.add_candidate(candidate)
    writer.add_statistical_trial(
        campaign.campaign_id,
        trial,
        created_at_epoch_us=campaign.created_at_epoch_us,
    )
    writer.add_operational_attempt(
        campaign.campaign_id,
        attempt,
        created_at_epoch_us=campaign.created_at_epoch_us,
    )

    assert reader.get_campaign(campaign.campaign_id) == campaign
    assert reader.list_campaign_events(campaign.campaign_id) == (event,)
    assert reader.list_candidates(campaign.campaign_id) == (candidate,)
    ledger = reader.get_search_ledger(campaign.campaign_id)
    assert ledger is not None
    assert ledger.statistical_trials == (trial,)
    assert ledger.operational_attempts == (attempt,)
    assert ledger.statistical_trial_count == 1


def test_campaign_event_stream_rejects_noncontiguous_status_transition(
    tmp_path: Path,
) -> None:
    writer, _ = _storage(tmp_path)
    campaign = _campaign_record()
    writer.add_campaign(campaign)

    with pytest.raises(ExperimentPersistenceError):
        writer.append_campaign_event(
            CampaignEventRecord(
                event_id="campaign-event-gap",
                campaign_id=campaign.campaign_id,
                ordinal=1,
                event_type="campaign_started",
                previous_status="draft",
                status="running",
                detail_payload=b"{}",
                occurred_at_epoch_us=campaign.created_at_epoch_us,
            )
        )


def test_statistical_trial_rejects_candidate_relational_hash_drift(
    tmp_path: Path,
) -> None:
    writer, _ = _storage(tmp_path)
    campaign = _campaign_record()
    candidate = _candidate_record()
    logical = LogicalTrialIdentity(
        origin_experiment_id=campaign.campaign_id,
        candidate_id=candidate.candidate.candidate.candidate_id,
        ordinal=1,
        parameter_hash=candidate.candidate.candidate.parameter_hash,
        kind=TrialKind.CURRENT,
    )
    drifted = StatisticalTrial(
        logical_trial=logical,
        candidate_hash=_hash("e"),
        validation_protocol_hash=_hash("c"),
        lineage_root=campaign.lineage_root,
        family_id="family-round-trip",
    )
    writer.add_campaign(campaign)
    writer.add_candidate(candidate)

    with pytest.raises(ExperimentPersistenceError):
        writer.add_statistical_trial(
            campaign.campaign_id,
            drifted,
            created_at_epoch_us=campaign.created_at_epoch_us,
        )


def test_code_and_sandbox_attestation_round_trip(tmp_path: Path) -> None:
    writer, reader = _storage(tmp_path)
    campaign = _campaign_record()
    source = "def fit(frame):\n    return frame\n"
    artifact = ResearchCodeArtifact(
        source_code=source,
        source_hash=ContentHash(hashlib.sha256(source.encode()).hexdigest()),
        canonical_ast_hash=_hash("a"),
        dependency_lock_hash=_hash("b"),
        dependencies=("numpy==2.3.2", "polars==1.32.2"),
        image_digest=_hash("c"),
        input_schema_hash=_hash("e"),
        output_schema_hash=_hash("f"),
    )
    manifest = SandboxExecutionManifest(
        code_artifact_hash=artifact.artifact_hash,
        runtime_digest=_hash("1"),
        resource_limits=SandboxResourceLimits(),
        input_hash=_hash("2"),
        output_hash=_hash("3"),
        seed=42,
        exit_status=SandboxExitStatus.SUCCEEDED,
        exit_code=0,
        attestation_hash=_hash("4"),
    )
    execution = SandboxExecutionRecord(
        campaign_id=campaign.campaign_id,
        attempt_id=None,
        manifest=manifest,
        created_at_epoch_us=campaign.created_at_epoch_us,
    )

    writer.add_campaign(campaign)
    writer.add_code_artifact(artifact, created_at_epoch_us=1)
    writer.add_sandbox_execution(execution)

    assert reader.get_code_artifact(artifact.artifact_hash) == artifact
    assert reader.get_sandbox_execution(manifest.attestation_hash) == execution


def test_feedback_and_knowledge_reads_fail_closed_at_known_at(tmp_path: Path) -> None:
    writer, reader = _storage(tmp_path)
    campaign = _campaign_record()
    candidate = _candidate_record()
    feedback = ResearchFeedbackRecord(
        feedback_id="feedback-round-trip",
        feedback=ResearchFeedback(
            campaign_id=campaign.campaign_id,
            candidate_id=candidate.candidate.candidate.candidate_id,
            evaluation_result_hash=_hash("5"),
            summary="Turnover exceeded the preregistered constraint.",
            evidence_refs=(_hash("6"),),
            outcome_known_at=KNOWN_AT,
            snapshot_id=SnapshotId("snapshot-round-trip"),
            source=KnowledgeSource.HOST_VALIDATION,
        ),
    )
    knowledge = KnowledgeItem(
        knowledge_id="knowledge-round-trip",
        campaign_id=campaign.campaign_id,
        claim="The feature decays after ten sessions.",
        scope=KnowledgeScope.CAMPAIGN_LOCAL,
        scope_ref=None,
        evidence_refs=(_hash("7"),),
        outcome_known_at=KNOWN_AT,
        snapshot_id=SnapshotId("snapshot-round-trip"),
        source=KnowledgeSource.HOST_VALIDATION,
        source_hash=_hash("8"),
        status=KnowledgeStatus.ACTIVE,
        promotion_receipt_hash=None,
        independent_evidence_hash=None,
    )
    contradicted = KnowledgeStatusEvent(
        event_id="knowledge-event-round-trip",
        knowledge_id=knowledge.knowledge_id,
        previous_status=KnowledgeStatus.ACTIVE,
        status=KnowledgeStatus.CONTRADICTED,
        outcome_known_at=KNOWN_AT + timedelta(hours=1),
        evidence_hash=_hash("9"),
    )

    writer.add_campaign(campaign)
    writer.add_candidate(candidate)
    writer.add_feedback(feedback)
    writer.add_knowledge(knowledge)
    writer.append_knowledge_status_event(contradicted)

    before = KNOWN_AT - timedelta(microseconds=1)
    assert reader.list_feedback_visible_at(campaign.campaign_id, before) == ()
    assert reader.list_knowledge_visible_at(campaign.campaign_id, before) == ()
    assert reader.list_feedback_visible_at(campaign.campaign_id, KNOWN_AT) == (
        feedback,
    )
    assert reader.list_knowledge_visible_at(campaign.campaign_id, KNOWN_AT) == (
        knowledge,
    )
    assert reader.get_knowledge_visible_at(knowledge.knowledge_id, before) is None
    assert (
        reader.get_knowledge_visible_at(knowledge.knowledge_id, KNOWN_AT) == knowledge
    )
    after = reader.list_knowledge_visible_at(
        campaign.campaign_id, KNOWN_AT + timedelta(hours=1)
    )
    assert len(after) == 1
    assert after[0].status is KnowledgeStatus.CONTRADICTED
    assert (
        reader.get_knowledge_visible_at(
            knowledge.knowledge_id,
            KNOWN_AT + timedelta(hours=1),
        )
        == after[0]
    )
    assert reader.list_knowledge_status_events(knowledge.knowledge_id) == (
        contradicted,
    )


def test_scope_read_includes_only_own_local_matching_family_and_global(
    tmp_path: Path,
) -> None:
    writer, reader = _storage(tmp_path)
    current = _campaign_record()
    other = _campaign_record("campaign-other")
    writer.add_campaign(current)
    writer.add_campaign(other)

    def item(
        knowledge_id: str,
        campaign_id: ExperimentId,
        scope: KnowledgeScope,
        *,
        scope_ref: str | None = None,
        known_at: datetime = KNOWN_AT,
    ) -> KnowledgeItem:
        promoted = scope is not KnowledgeScope.CAMPAIGN_LOCAL
        return KnowledgeItem(
            knowledge_id=knowledge_id,
            campaign_id=campaign_id,
            claim=f"Verified claim {knowledge_id}",
            scope=scope,
            scope_ref=scope_ref,
            evidence_refs=(_hash("7"),),
            outcome_known_at=known_at,
            snapshot_id=SnapshotId("snapshot-scope"),
            source=KnowledgeSource.HOST_VALIDATION,
            source_hash=_hash("8"),
            status=KnowledgeStatus.ACTIVE,
            promotion_receipt_hash=_hash("9") if promoted else None,
            independent_evidence_hash=_hash("a") if promoted else None,
        )

    for knowledge in (
        item("local-current", current.campaign_id, KnowledgeScope.CAMPAIGN_LOCAL),
        item("local-other", other.campaign_id, KnowledgeScope.CAMPAIGN_LOCAL),
        item(
            "family-current",
            other.campaign_id,
            KnowledgeScope.STRATEGY_FAMILY,
            scope_ref="family-current",
        ),
        item(
            "family-other",
            other.campaign_id,
            KnowledgeScope.STRATEGY_FAMILY,
            scope_ref="family-other",
        ),
        item("global-visible", other.campaign_id, KnowledgeScope.GLOBAL),
        item(
            "global-future",
            other.campaign_id,
            KnowledgeScope.GLOBAL,
            known_at=KNOWN_AT + timedelta(microseconds=1),
        ),
    ):
        writer.add_knowledge(knowledge)

    visible = reader.list_knowledge_visible_for_scope(
        current.campaign_id,
        "family-current",
        KNOWN_AT,
    )

    assert tuple(value.knowledge_id for value in visible) == (
        "family-current",
        "global-visible",
        "local-current",
    )


def test_cross_table_authority_and_pit_guards_fail_closed(tmp_path: Path) -> None:
    writer, _reader = _storage(tmp_path)
    campaign = _campaign_record()
    candidate = _candidate_record()
    writer.add_campaign(campaign)

    mismatched_axis = CandidateLineageRecord(
        campaign_id=campaign.campaign_id,
        candidate=ResearchCandidateSpec(
            candidate=candidate.candidate.candidate,
            search_axis=SearchAxis.MODEL_CODE,
            parent_candidate_id=None,
            factor_code_hash=None,
            model_code_hash=_hash("a"),
            data_requirement_hashes=candidate.candidate.data_requirement_hashes,
        ),
        generation=0,
        created_at_epoch_us=candidate.created_at_epoch_us,
    )
    with pytest.raises(ExperimentPersistenceError):
        writer.add_candidate(mismatched_axis)

    writer.add_candidate(candidate)
    logical = LogicalTrialIdentity(
        origin_experiment_id=campaign.campaign_id,
        candidate_id=candidate.candidate.candidate.candidate_id,
        ordinal=1,
        parameter_hash=candidate.candidate.candidate.parameter_hash,
        kind=TrialKind.CURRENT,
    )
    reset_trial = StatisticalTrial(
        logical_trial=logical,
        candidate_hash=candidate.candidate.candidate_hash,
        validation_protocol_hash=_hash("c"),
        lineage_root=_hash("e"),
        family_id="family-reset",
    )
    with pytest.raises(ExperimentPersistenceError):
        writer.add_statistical_trial(
            campaign.campaign_id, reset_trial, created_at_epoch_us=1
        )

    knowledge = KnowledgeItem(
        knowledge_id="knowledge-guard",
        campaign_id=campaign.campaign_id,
        claim="A claim with monotonic status evidence.",
        scope=KnowledgeScope.CAMPAIGN_LOCAL,
        scope_ref=None,
        evidence_refs=(_hash("7"),),
        outcome_known_at=KNOWN_AT,
        snapshot_id=SnapshotId("snapshot-guard"),
        source=KnowledgeSource.HOST_VALIDATION,
        source_hash=_hash("8"),
        status=KnowledgeStatus.ACTIVE,
        promotion_receipt_hash=None,
        independent_evidence_hash=None,
    )
    writer.add_knowledge(knowledge)
    writer.append_knowledge_status_event(
        KnowledgeStatusEvent(
            event_id="knowledge-guard-1",
            knowledge_id=knowledge.knowledge_id,
            previous_status=KnowledgeStatus.ACTIVE,
            status=KnowledgeStatus.CONTRADICTED,
            outcome_known_at=KNOWN_AT + timedelta(hours=2),
            evidence_hash=_hash("9"),
        )
    )
    with pytest.raises(ExperimentPersistenceError):
        writer.append_knowledge_status_event(
            KnowledgeStatusEvent(
                event_id="knowledge-guard-2",
                knowledge_id=knowledge.knowledge_id,
                previous_status=KnowledgeStatus.CONTRADICTED,
                status=KnowledgeStatus.REVOKED,
                outcome_known_at=KNOWN_AT + timedelta(hours=1),
                evidence_hash=_hash("f"),
            )
        )
