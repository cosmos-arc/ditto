"""Typed SQLite reader for governed research campaign facts."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import cast

from ditto_analysis.errors import ExperimentIntegrityError, ExperimentPersistenceError
from ditto_analysis.experiments._time import datetime_from_epoch_us, epoch_us
from ditto_analysis.experiments._validation import require_utc_datetime
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
    SearchLedger,
    StatisticalTrial,
)
from ditto_analysis.experiments.specs import CandidateSpec, FrozenValue
from ditto_analysis.experiments.trial_family import (
    LogicalTrialIdentity,
    TrialFamilyDeclaration,
    TrialKind,
)
from ditto_analysis.storage.sqlite.experiments.database import (
    ResearchExperimentDatabase,
)


def _integrity(message: str, field: str) -> ExperimentIntegrityError:
    return ExperimentIntegrityError(
        message,
        details={"reason_code": "persisted_campaign_payload_invalid", "field": field},
    )


def _json_object(payload: str, field: str) -> dict[str, object]:
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise _integrity("persisted campaign payload is not JSON", field) from exc
    if not isinstance(value, dict):
        raise _integrity("persisted campaign payload is not an object", field)
    return cast("dict[str, object]", value)


def _json_hashes(payload: str, field: str) -> tuple[ContentHash, ...]:
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise _integrity("persisted hash sequence is not JSON", field) from exc
    if not isinstance(value, list):
        raise _integrity("persisted hash sequence is malformed", field)
    raw_values = cast("list[object]", value)
    if any(type(item) is not str for item in raw_values):
        raise _integrity("persisted hash sequence is malformed", field)
    return tuple(ContentHash(item) for item in cast("list[str]", raw_values))


def _logical_trial(row: sqlite3.Row) -> LogicalTrialIdentity:
    return LogicalTrialIdentity(
        origin_experiment_id=ExperimentId(row["origin_experiment_id"]),
        candidate_id=CandidateId(row["candidate_id"]),
        ordinal=row["logical_ordinal"],
        parameter_hash=ContentHash(row["parameter_hash"]),
        kind=TrialKind(row["trial_kind"]),
    )


def _knowledge_item(row: sqlite3.Row) -> KnowledgeItem:
    return KnowledgeItem(
        knowledge_id=row["knowledge_id"],
        campaign_id=ExperimentId(row["campaign_id"]),
        claim=row["claim"],
        scope=KnowledgeScope(row["scope"]),
        scope_ref=row["scope_ref"],
        evidence_refs=_json_hashes(row["evidence_refs_json"], "evidence_refs_json"),
        outcome_known_at=datetime_from_epoch_us(row["outcome_known_at_epoch_us"]),
        snapshot_id=SnapshotId(row["snapshot_id"]),
        source=KnowledgeSource(row["source"]),
        source_hash=ContentHash(row["source_hash"]),
        status=KnowledgeStatus(row["visible_status"]),
        promotion_receipt_hash=(
            None
            if row["promotion_receipt_hash"] is None
            else ContentHash(row["promotion_receipt_hash"])
        ),
        independent_evidence_hash=(
            None
            if row["independent_evidence_hash"] is None
            else ContentHash(row["independent_evidence_hash"])
        ),
    )


class SQLiteCampaignReader:
    """Read lossless campaign values and enforce PIT cutoffs in the adapter."""

    def __init__(self, database: ResearchExperimentDatabase) -> None:
        self._database = database

    def _one(self, sql: str, parameters: tuple[object, ...]) -> sqlite3.Row | None:
        try:
            return self._database.get_connection().execute(sql, parameters).fetchone()
        except sqlite3.Error as exc:
            raise ExperimentPersistenceError(
                "campaign read failed",
                details={"reason_code": "campaign_read_failed"},
            ) from exc

    def get_campaign(self, campaign_id: ExperimentId) -> CampaignManifestRecord | None:
        """Return an immutable campaign manifest by nominal identity."""
        row = self._one(
            "SELECT * FROM research_campaign WHERE campaign_id=?",
            (str(campaign_id),),
        )
        if row is None:
            return None
        if row["manifest_schema_version"] != 1:
            raise _integrity("campaign manifest schema is unsupported", "manifest_json")
        return CampaignManifestRecord(
            campaign_id=ExperimentId(row["campaign_id"]),
            manifest_hash=ContentHash(row["manifest_hash"]),
            manifest_payload=row["manifest_json"].encode("utf-8"),
            search_axis=SearchAxis(row["search_axis"]),
            lineage_root=ContentHash(row["lineage_root"]),
            created_at_epoch_us=row["created_at_epoch_us"],
        )

    def list_campaigns(self) -> tuple[CampaignManifestRecord, ...]:
        """Return every immutable Campaign newest first."""
        try:
            rows = self._database.get_connection().execute(
                """
                SELECT campaign_id FROM research_campaign
                ORDER BY created_at_epoch_us DESC, campaign_id DESC
                """
            )
        except sqlite3.Error as exc:
            raise ExperimentPersistenceError(
                "campaign list read failed",
                details={"reason_code": "campaign_read_failed"},
            ) from exc
        campaigns: list[CampaignManifestRecord] = []
        for row in rows:
            campaign = self.get_campaign(ExperimentId(row["campaign_id"]))
            if campaign is None:
                raise ExperimentPersistenceError(
                    "listed campaign is not readable",
                    details={"reason_code": "campaign_read_failed"},
                )
            campaigns.append(campaign)
        return tuple(campaigns)

    def list_campaign_events(
        self, campaign_id: ExperimentId
    ) -> tuple[CampaignEventRecord, ...]:
        """Return the complete campaign event stream in ordinal order."""
        rows = self._database.get_connection().execute(
            """
            SELECT * FROM research_campaign_event
            WHERE campaign_id=? ORDER BY ordinal
            """,
            (str(campaign_id),),
        )
        return tuple(
            CampaignEventRecord(
                event_id=row["event_id"],
                campaign_id=ExperimentId(row["campaign_id"]),
                ordinal=row["ordinal"],
                event_type=row["event_type"],
                previous_status=row["previous_status"],
                status=row["status"],
                detail_payload=row["detail_json"].encode("utf-8"),
                occurred_at_epoch_us=row["occurred_at_epoch_us"],
            )
            for row in rows
        )

    @staticmethod
    def _candidate(row: sqlite3.Row) -> CandidateLineageRecord:
        payload = _json_object(row["candidate_json"], "candidate_json")
        parameters = payload.get("parameters")
        if not isinstance(parameters, Mapping):
            raise _integrity(
                "persisted candidate parameters are not an object", "candidate_json"
            )
        hashes = payload.get("data_requirement_hashes")
        if not isinstance(hashes, Sequence) or isinstance(hashes, (str, bytes)):
            raise _integrity(
                "persisted candidate data hashes are malformed", "candidate_json"
            )
        raw_hashes = tuple(cast("Sequence[object]", hashes))
        if any(type(value) is not str for value in raw_hashes):
            raise _integrity(
                "persisted candidate data hashes are malformed", "candidate_json"
            )
        typed_hashes = cast("tuple[str, ...]", raw_hashes)
        candidate = ResearchCandidateSpec(
            candidate=CandidateSpec(
                candidate_id=CandidateId(row["candidate_id"]),
                ordinal=row["ordinal"],
                is_baseline=payload.get("is_baseline") is True,
                parameters=cast("Mapping[str, FrozenValue]", parameters),
            ),
            search_axis=SearchAxis(row["search_axis"]),
            parent_candidate_id=(
                None
                if row["parent_candidate_id"] is None
                else CandidateId(row["parent_candidate_id"])
            ),
            factor_code_hash=(
                None
                if payload.get("factor_code_hash") is None
                else ContentHash(cast("str", payload["factor_code_hash"]))
            ),
            model_code_hash=(
                None
                if payload.get("model_code_hash") is None
                else ContentHash(cast("str", payload["model_code_hash"]))
            ),
            data_requirement_hashes=tuple(ContentHash(value) for value in typed_hashes),
        )
        if (
            str(candidate.candidate_hash) != row["candidate_hash"]
            or str(candidate.candidate.parameter_hash) != row["parameter_hash"]
        ):
            raise _integrity(
                "candidate payload disagrees with relational hashes", "candidate_json"
            )
        return CandidateLineageRecord(
            campaign_id=ExperimentId(row["campaign_id"]),
            candidate=candidate,
            generation=row["generation"],
            created_at_epoch_us=row["created_at_epoch_us"],
        )

    def list_candidates(
        self, campaign_id: ExperimentId
    ) -> tuple[CandidateLineageRecord, ...]:
        """Return immutable candidate lineage in preregistered order."""
        rows = self._database.get_connection().execute(
            """
            SELECT * FROM research_candidate_lineage
            WHERE campaign_id=? ORDER BY ordinal
            """,
            (str(campaign_id),),
        )
        return tuple(self._candidate(row) for row in rows)

    def get_search_ledger(self, campaign_id: ExperimentId) -> SearchLedger | None:
        """Rebuild the statistical-trial/operational-attempt ledger."""
        trial_rows = tuple(
            self._database.get_connection().execute(
                """
                SELECT * FROM research_statistical_trial
                WHERE campaign_id=? ORDER BY logical_ordinal, candidate_id
                """,
                (str(campaign_id),),
            )
        )
        if not trial_rows:
            return None
        trials = tuple(
            StatisticalTrial(
                logical_trial=_logical_trial(row),
                candidate_hash=ContentHash(row["candidate_hash"]),
                validation_protocol_hash=ContentHash(row["validation_protocol_hash"]),
                lineage_root=ContentHash(row["lineage_root"]),
                family_id=row["family_id"],
            )
            for row in trial_rows
        )
        family_ids = {trial.family_id for trial in trials}
        lineage_roots = {trial.lineage_root for trial in trials}
        if len(family_ids) != 1 or len(lineage_roots) != 1:
            raise _integrity(
                "persisted trials reset family or lineage", "research_statistical_trial"
            )
        attempts = tuple(
            OperationalAttempt(
                attempt_id=AttemptId(row["attempt_id"]),
                logical_trial=_logical_trial(row),
                ordinal=row["ordinal"],
                parent_attempt_id=(
                    None
                    if row["parent_attempt_id"] is None
                    else AttemptId(row["parent_attempt_id"])
                ),
                lineage_root=ContentHash(row["attempt_lineage_root"]),
                family_id=row["attempt_family_id"],
            )
            for row in self._database.get_connection().execute(
                """
                SELECT attempt.*, trial.origin_experiment_id, trial.candidate_id,
                       trial.logical_ordinal, trial.parameter_hash, trial.trial_kind,
                       attempt.lineage_root AS attempt_lineage_root,
                       attempt.family_id AS attempt_family_id
                FROM research_operational_attempt attempt
                JOIN research_statistical_trial trial USING(trial_key)
                WHERE trial.campaign_id=?
                ORDER BY trial.logical_ordinal, attempt.ordinal
                """,
                (str(campaign_id),),
            )
        )
        family_id = next(iter(family_ids))
        lineage_root = next(iter(lineage_roots))
        family = TrialFamilyDeclaration(
            family_id=family_id,
            members=tuple(trial.logical_trial for trial in trials),
        )
        return SearchLedger(
            lineage_root=lineage_root,
            trial_family=family,
            statistical_trials=trials,
            operational_attempts=attempts,
        )

    def get_code_artifact(
        self, artifact_hash: ContentHash
    ) -> ResearchCodeArtifact | None:
        """Return a verified content-addressed generated-code artifact."""
        row = self._one(
            "SELECT * FROM research_code_artifact WHERE artifact_hash=?",
            (str(artifact_hash),),
        )
        if row is None:
            return None
        try:
            dependencies = json.loads(row["dependencies_json"])
        except json.JSONDecodeError as exc:
            raise _integrity(
                "persisted dependency lock is not JSON", "dependencies_json"
            ) from exc
        if not isinstance(dependencies, list):
            raise _integrity(
                "persisted dependency lock is not a list", "dependencies_json"
            )
        artifact = ResearchCodeArtifact(
            source_code=row["source_code"],
            source_hash=ContentHash(row["source_hash"]),
            canonical_ast_hash=ContentHash(row["canonical_ast_hash"]),
            dependency_lock_hash=ContentHash(row["dependency_lock_hash"]),
            dependencies=tuple(cast("list[str]", dependencies)),
            image_digest=ContentHash(row["image_digest"]),
            input_schema_hash=ContentHash(row["input_schema_hash"]),
            output_schema_hash=ContentHash(row["output_schema_hash"]),
        )
        if artifact.artifact_hash != artifact_hash:
            raise _integrity(
                "persisted code artifact hash has drifted", "artifact_hash"
            )
        return artifact

    def get_sandbox_execution(
        self, attestation_hash: ContentHash
    ) -> SandboxExecutionRecord | None:
        """Return one typed sandbox attestation without performance fields."""
        row = self._one(
            "SELECT * FROM sandbox_execution_manifest WHERE attestation_hash=?",
            (str(attestation_hash),),
        )
        if row is None:
            return None
        manifest = SandboxExecutionManifest(
            code_artifact_hash=ContentHash(row["code_artifact_hash"]),
            runtime_digest=ContentHash(row["runtime_digest"]),
            resource_limits=SandboxResourceLimits(
                cpu_count=row["cpu_count"],
                memory_bytes=row["memory_bytes"],
                process_limit=row["process_limit"],
                temporary_storage_bytes=row["temporary_storage_bytes"],
                wall_time_seconds=row["wall_time_seconds"],
                output_bytes=row["output_bytes"],
            ),
            input_hash=ContentHash(row["input_hash"]),
            output_hash=(
                None if row["output_hash"] is None else ContentHash(row["output_hash"])
            ),
            seed=row["seed"],
            exit_status=SandboxExitStatus(row["exit_status"]),
            exit_code=row["exit_code"],
            attestation_hash=ContentHash(row["attestation_hash"]),
        )
        return SandboxExecutionRecord(
            campaign_id=ExperimentId(row["campaign_id"]),
            attempt_id=(
                None if row["attempt_id"] is None else AttemptId(row["attempt_id"])
            ),
            manifest=manifest,
            created_at_epoch_us=row["created_at_epoch_us"],
        )

    def list_feedback_visible_at(
        self, campaign_id: ExperimentId, knowledge_cutoff: datetime
    ) -> tuple[ResearchFeedbackRecord, ...]:
        """Return only feedback knowable by the supplied UTC cutoff."""
        cutoff = require_utc_datetime(knowledge_cutoff, "knowledge_cutoff")
        rows = self._database.get_connection().execute(
            """
            SELECT * FROM research_feedback
            WHERE campaign_id=? AND outcome_known_at_epoch_us<=?
            ORDER BY outcome_known_at_epoch_us, feedback_id
            """,
            (str(campaign_id), epoch_us(cutoff)),
        )
        return tuple(
            ResearchFeedbackRecord(
                feedback_id=row["feedback_id"],
                feedback=ResearchFeedback(
                    campaign_id=ExperimentId(row["campaign_id"]),
                    candidate_id=CandidateId(row["candidate_id"]),
                    evaluation_result_hash=ContentHash(row["evaluation_result_hash"]),
                    summary=row["summary"],
                    evidence_refs=_json_hashes(
                        row["evidence_refs_json"], "evidence_refs_json"
                    ),
                    outcome_known_at=datetime_from_epoch_us(
                        row["outcome_known_at_epoch_us"]
                    ),
                    snapshot_id=SnapshotId(row["snapshot_id"]),
                    source=KnowledgeSource(row["source"]),
                ),
            )
            for row in rows
        )

    def list_knowledge_visible_at(
        self, campaign_id: ExperimentId, knowledge_cutoff: datetime
    ) -> tuple[KnowledgeItem, ...]:
        """Return knowledge and status projections visible at the UTC cutoff."""
        cutoff = require_utc_datetime(knowledge_cutoff, "knowledge_cutoff")
        rows = self._database.get_connection().execute(
            """
            SELECT knowledge.*,
                   COALESCE(
                       (
                           SELECT event.status
                           FROM research_knowledge_status_event event
                           WHERE event.knowledge_id=knowledge.knowledge_id
                             AND event.outcome_known_at_epoch_us<=?
                           ORDER BY event.ordinal DESC LIMIT 1
                       ),
                       knowledge.initial_status
                   ) AS visible_status
            FROM research_knowledge knowledge
            WHERE knowledge.campaign_id=?
              AND knowledge.outcome_known_at_epoch_us<=?
            ORDER BY knowledge.outcome_known_at_epoch_us, knowledge.knowledge_id
            """,
            (epoch_us(cutoff), str(campaign_id), epoch_us(cutoff)),
        )
        return tuple(_knowledge_item(row) for row in rows)

    def list_knowledge_visible_for_scope(
        self,
        campaign_id: ExperimentId,
        strategy_family_ref: str | None,
        knowledge_cutoff: datetime,
    ) -> tuple[KnowledgeItem, ...]:
        """Return local, matching-family, and global PIT projections only."""
        cutoff = require_utc_datetime(knowledge_cutoff, "knowledge_cutoff")
        rows = self._database.get_connection().execute(
            """
            SELECT knowledge.*,
                   COALESCE(
                       (
                           SELECT event.status
                           FROM research_knowledge_status_event event
                           WHERE event.knowledge_id=knowledge.knowledge_id
                             AND event.outcome_known_at_epoch_us<=?
                           ORDER BY event.ordinal DESC LIMIT 1
                       ),
                       knowledge.initial_status
                   ) AS visible_status
            FROM research_knowledge knowledge
            WHERE knowledge.outcome_known_at_epoch_us<=?
              AND (
                    (knowledge.scope='campaign-local' AND knowledge.campaign_id=?)
                 OR (knowledge.scope='strategy-family' AND ? IS NOT NULL
                     AND knowledge.scope_ref=?)
                 OR knowledge.scope='global'
              )
            ORDER BY knowledge.outcome_known_at_epoch_us, knowledge.knowledge_id
            """,
            (
                epoch_us(cutoff),
                epoch_us(cutoff),
                str(campaign_id),
                strategy_family_ref,
                strategy_family_ref,
            ),
        )
        return tuple(_knowledge_item(row) for row in rows)

    def get_knowledge_visible_at(
        self,
        knowledge_id: str,
        knowledge_cutoff: datetime,
    ) -> KnowledgeItem | None:
        """Return one exact knowledge projection only when visible at cutoff."""
        cutoff = require_utc_datetime(knowledge_cutoff, "knowledge_cutoff")
        row = (
            self._database.get_connection()
            .execute(
                """
            SELECT knowledge.*,
                   COALESCE(
                       (
                           SELECT event.status
                           FROM research_knowledge_status_event event
                           WHERE event.knowledge_id=knowledge.knowledge_id
                             AND event.outcome_known_at_epoch_us<=?
                           ORDER BY event.ordinal DESC LIMIT 1
                       ),
                       knowledge.initial_status
                   ) AS visible_status
            FROM research_knowledge knowledge
            WHERE knowledge.knowledge_id=?
              AND knowledge.outcome_known_at_epoch_us<=?
            """,
                (epoch_us(cutoff), knowledge_id, epoch_us(cutoff)),
            )
            .fetchone()
        )
        return None if row is None else _knowledge_item(row)

    def list_knowledge_status_events(
        self, knowledge_id: str
    ) -> tuple[KnowledgeStatusEvent, ...]:
        """Return the immutable status stream in persisted ordinal order."""
        rows = self._database.get_connection().execute(
            """
            SELECT * FROM research_knowledge_status_event
            WHERE knowledge_id=? ORDER BY ordinal
            """,
            (knowledge_id,),
        )
        return tuple(
            KnowledgeStatusEvent(
                event_id=row["event_id"],
                knowledge_id=row["knowledge_id"],
                previous_status=KnowledgeStatus(row["previous_status"]),
                status=KnowledgeStatus(row["status"]),
                outcome_known_at=datetime_from_epoch_us(
                    row["outcome_known_at_epoch_us"]
                ),
                evidence_hash=ContentHash(row["evidence_hash"]),
            )
            for row in rows
        )


__all__ = ["SQLiteCampaignReader"]
