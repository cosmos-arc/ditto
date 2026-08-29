"""SQLite writer for governed research campaign persistence contracts."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from dataclasses import replace
from typing import cast

from ditto_analysis.errors import (
    AnalysisError,
    ExperimentConflictError,
    ExperimentIntegrityError,
    ExperimentPersistenceError,
)
from ditto_analysis.experiments._time import epoch_us
from ditto_analysis.experiments.campaign_persistence import (
    CampaignEventRecord,
    CampaignManifestRecord,
    CandidateLineageRecord,
    ResearchFeedbackRecord,
    SandboxExecutionRecord,
)
from ditto_analysis.experiments.generated_code import ResearchCodeArtifact
from ditto_analysis.experiments.models import ContentHash, ExperimentId
from ditto_analysis.experiments.persistence import canonical_payload
from ditto_analysis.experiments.research_memory import (
    KnowledgeItem,
    KnowledgeStatusEvent,
)
from ditto_analysis.experiments.search_ledger import (
    OperationalAttempt,
    StatisticalTrial,
)
from ditto_analysis.storage.sqlite.experiments.database import (
    ResearchExperimentDatabase,
)


def _conflict(reason_code: str, **details: object) -> ExperimentConflictError:
    return ExperimentConflictError(
        "immutable campaign persistence identity conflicts with existing content",
        details={"reason_code": reason_code, **details},
    )


def _integrity(message: str, reason_code: str) -> ExperimentIntegrityError:
    return ExperimentIntegrityError(message, details={"reason_code": reason_code})


def _persistence(operation: str, exc: sqlite3.Error) -> ExperimentPersistenceError:
    return ExperimentPersistenceError(
        f"campaign {operation} failed and was rolled back",
        details={
            "reason_code": "campaign_persistence_failed",
            "operation": operation,
            "sqlite_error": type(exc).__name__,
        },
    )


def _json_sequence(values: Sequence[object]) -> str:
    return json.dumps(
        [str(value) for value in values],
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _fold_reservation_detail(record: CampaignEventRecord) -> tuple[str, int]:
    if record.event_type != "candidate_fold_reserved":
        raise _integrity(
            "fold reservation event type is invalid",
            "invalid_fold_reservation_event",
        )
    decoded = cast("object", json.loads(record.detail_payload))
    detail = cast("dict[str, object]", decoded) if isinstance(decoded, dict) else {}
    candidate_id = detail.get("candidate_id")
    count = detail.get("fold_run_count")
    if type(candidate_id) is not str or type(count) is not int or count <= 0:
        raise _integrity(
            "fold reservation detail is invalid",
            "invalid_fold_reservation_event",
        )
    return candidate_id, count


def _fold_accounted_usage(rows: Sequence[sqlite3.Row]) -> int:
    reservations: dict[str, int] = {}
    dispatches: dict[str, int] = {}
    for row in rows:
        decoded = cast("object", json.loads(cast("str", row["detail_json"])))
        if not isinstance(decoded, dict):
            raise _integrity(
                "persisted fold accounting is invalid",
                "invalid_fold_reservation_event",
            )
        persisted_detail = cast("dict[str, object]", decoded)
        candidate_id = persisted_detail.get("candidate_id")
        count = persisted_detail.get("fold_run_count")
        if type(candidate_id) is not str or type(count) is not int or count <= 0:
            raise _integrity(
                "persisted fold accounting is invalid",
                "invalid_fold_reservation_event",
            )
        target = (
            reservations
            if row["event_type"] == "candidate_fold_reserved"
            else dispatches
        )
        target[candidate_id] = count
    return sum(reservations.values()) + sum(
        count
        for candidate_id, count in dispatches.items()
        if candidate_id not in reservations
    )


def _candidate_payload(record: CandidateLineageRecord) -> bytes:
    candidate = record.candidate
    return canonical_payload(
        {
            "schema_id": "r5-research-candidate",
            "schema_version": 1,
            "candidate_id": str(candidate.candidate.candidate_id),
            "ordinal": candidate.candidate.ordinal,
            "is_baseline": candidate.candidate.is_baseline,
            "parameters": candidate.candidate.parameters,
            "search_axis": candidate.search_axis.value,
            "parent_candidate_id": (
                None
                if candidate.parent_candidate_id is None
                else str(candidate.parent_candidate_id)
            ),
            "factor_code_hash": (
                None
                if candidate.factor_code_hash is None
                else str(candidate.factor_code_hash)
            ),
            "model_code_hash": (
                None
                if candidate.model_code_hash is None
                else str(candidate.model_code_hash)
            ),
            "data_requirement_hashes": [
                str(value) for value in candidate.data_requirement_hashes
            ],
        }
    ).json_bytes


def _trial_key(trial: StatisticalTrial) -> ContentHash:
    logical = trial.logical_trial
    return canonical_payload(
        {
            "schema_id": "r5-research-statistical-trial",
            "schema_version": 1,
            "origin_experiment_id": str(logical.origin_experiment_id),
            "candidate_id": str(logical.candidate_id),
            "ordinal": logical.ordinal,
            "parameter_hash": str(logical.parameter_hash),
            "candidate_hash": str(trial.candidate_hash),
            "validation_protocol_hash": str(trial.validation_protocol_hash),
        }
    ).content_hash


class SQLiteCampaignWriter:
    """Persist campaign facts without exposing connections to consumers."""

    def __init__(self, database: ResearchExperimentDatabase) -> None:
        self._database = database

    def _insert_immutable(
        self,
        *,
        operation: str,
        select_sql: str,
        select_parameters: tuple[object, ...],
        insert_sql: str,
        values: tuple[object, ...],
        conflict_reason: str,
    ) -> None:
        connection = self._database.get_connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(select_sql, select_parameters).fetchone()
            if existing is not None:
                if tuple(existing) == values:
                    connection.commit()
                    return
                raise _conflict(conflict_reason)
            connection.execute(insert_sql, values)
            connection.commit()
        except AnalysisError:
            connection.rollback()
            raise
        except sqlite3.Error as exc:
            connection.rollback()
            raise _persistence(operation, exc) from exc

    def add_campaign(self, record: CampaignManifestRecord) -> None:
        """Insert or idempotently replay one immutable campaign manifest."""
        values = (
            str(record.campaign_id),
            str(record.manifest_hash),
            1,
            record.manifest_payload.decode("utf-8"),
            record.search_axis.value,
            str(record.lineage_root),
            record.created_at_epoch_us,
        )
        self._insert_immutable(
            operation="manifest insert",
            select_sql=(
                "SELECT campaign_id, manifest_hash, manifest_schema_version, "
                "manifest_json, search_axis, lineage_root, created_at_epoch_us "
                "FROM research_campaign WHERE campaign_id=?"
            ),
            select_parameters=(str(record.campaign_id),),
            insert_sql=(
                "INSERT INTO research_campaign(campaign_id, manifest_hash, "
                "manifest_schema_version, manifest_json, search_axis, lineage_root, "
                "created_at_epoch_us) VALUES (?, ?, ?, ?, ?, ?, ?)"
            ),
            values=values,
            conflict_reason="campaign_immutable_conflict",
        )

    def append_campaign_event(self, record: CampaignEventRecord) -> None:
        """Append one immutable lifecycle event with a campaign-local ordinal."""
        values = (
            record.event_id,
            str(record.campaign_id),
            record.ordinal,
            record.event_type,
            record.previous_status,
            record.status,
            record.detail_payload.decode("utf-8"),
            record.occurred_at_epoch_us,
        )
        self._insert_immutable(
            operation="event append",
            select_sql=(
                "SELECT event_id, campaign_id, ordinal, event_type, previous_status, "
                "status, detail_json, occurred_at_epoch_us "
                "FROM research_campaign_event WHERE event_id=?"
            ),
            select_parameters=(record.event_id,),
            insert_sql=(
                "INSERT INTO research_campaign_event(event_id, campaign_id, ordinal, "
                "event_type, previous_status, status, detail_json, "
                "occurred_at_epoch_us) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
            ),
            values=values,
            conflict_reason="campaign_event_immutable_conflict",
        )

    def reserve_campaign_fold_budget(
        self,
        record: CampaignEventRecord,
        *,
        fold_run_limit: int,
    ) -> bool:
        """Atomically reserve fold runs on the append-only Campaign stream."""
        if type(fold_run_limit) is not int or fold_run_limit <= 0:
            raise _integrity("fold run limit is invalid", "invalid_fold_run_limit")
        _, requested = _fold_reservation_detail(record)
        connection = self._database.get_connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """
                SELECT campaign_id, event_type, status, detail_json,
                       occurred_at_epoch_us
                FROM research_campaign_event WHERE event_id=?
                """,
                (record.event_id,),
            ).fetchone()
            semantic_values = (
                str(record.campaign_id),
                record.event_type,
                record.status,
                record.detail_payload.decode("utf-8"),
                record.occurred_at_epoch_us,
            )
            if existing is not None:
                if tuple(existing) != semantic_values:
                    raise _conflict("campaign_event_immutable_conflict")
                connection.commit()
                return True

            rows = connection.execute(
                """
                SELECT event_type, detail_json FROM research_campaign_event
                WHERE campaign_id=? AND event_type IN
                      ('candidate_fold_reserved', 'candidate_dispatched')
                """,
                (str(record.campaign_id),),
            ).fetchall()
            used = _fold_accounted_usage(rows)
            if used + requested > fold_run_limit:
                connection.commit()
                return False

            predecessor = connection.execute(
                """
                SELECT ordinal, status FROM research_campaign_event
                WHERE campaign_id=? ORDER BY ordinal DESC LIMIT 1
                """,
                (str(record.campaign_id),),
            ).fetchone()
            persisted = replace(
                record,
                ordinal=0 if predecessor is None else predecessor["ordinal"] + 1,
                previous_status=None if predecessor is None else predecessor["status"],
            )
            connection.execute(
                """
                INSERT INTO research_campaign_event(
                    event_id, campaign_id, ordinal, event_type, previous_status,
                    status, detail_json, occurred_at_epoch_us
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    persisted.event_id,
                    str(persisted.campaign_id),
                    persisted.ordinal,
                    persisted.event_type,
                    persisted.previous_status,
                    persisted.status,
                    persisted.detail_payload.decode("utf-8"),
                    persisted.occurred_at_epoch_us,
                ),
            )
            connection.commit()
            return True
        except AnalysisError:
            connection.rollback()
            raise
        except sqlite3.Error as exc:
            connection.rollback()
            raise _persistence("fold reservation", exc) from exc

    def add_candidate(self, record: CandidateLineageRecord) -> None:
        """Insert an immutable candidate while retaining parent/generation lineage."""
        candidate = record.candidate
        payload = _candidate_payload(record)
        values = (
            str(record.campaign_id),
            str(candidate.candidate.candidate_id),
            (
                None
                if candidate.parent_candidate_id is None
                else str(candidate.parent_candidate_id)
            ),
            candidate.candidate.ordinal,
            record.generation,
            str(candidate.candidate_hash),
            str(candidate.candidate.parameter_hash),
            candidate.search_axis.value,
            1,
            payload.decode("utf-8"),
            record.created_at_epoch_us,
        )
        self._insert_immutable(
            operation="candidate insert",
            select_sql=(
                "SELECT campaign_id, candidate_id, parent_candidate_id, ordinal, "
                "generation, candidate_hash, parameter_hash, search_axis, "
                "candidate_schema_version, candidate_json, created_at_epoch_us "
                "FROM research_candidate_lineage WHERE campaign_id=? AND candidate_id=?"
            ),
            select_parameters=values[:2],
            insert_sql=(
                "INSERT INTO research_candidate_lineage(campaign_id, candidate_id, "
                "parent_candidate_id, ordinal, generation, candidate_hash, "
                "parameter_hash, search_axis, candidate_schema_version, "
                "candidate_json, created_at_epoch_us) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            ),
            values=values,
            conflict_reason="candidate_lineage_immutable_conflict",
        )

    def add_statistical_trial(
        self,
        campaign_id: ExperimentId,
        trial: StatisticalTrial,
        *,
        created_at_epoch_us: int,
    ) -> None:
        """Count one candidate/protocol pair exactly once, independent of retries."""
        key = _trial_key(trial)
        logical = trial.logical_trial
        values = (
            str(key),
            str(campaign_id),
            str(logical.candidate_id),
            str(logical.origin_experiment_id),
            logical.ordinal,
            str(logical.parameter_hash),
            logical.kind.value,
            str(trial.candidate_hash),
            str(trial.validation_protocol_hash),
            str(trial.lineage_root),
            trial.family_id,
            created_at_epoch_us,
        )
        self._insert_immutable(
            operation="statistical trial insert",
            select_sql=(
                "SELECT trial_key, campaign_id, candidate_id, origin_experiment_id, "
                "logical_ordinal, parameter_hash, trial_kind, candidate_hash, "
                "validation_protocol_hash, lineage_root, family_id, "
                "created_at_epoch_us "
                "FROM research_statistical_trial WHERE trial_key=?"
            ),
            select_parameters=(str(key),),
            insert_sql=(
                "INSERT INTO research_statistical_trial(trial_key, campaign_id, "
                "candidate_id, origin_experiment_id, logical_ordinal, parameter_hash, "
                "trial_kind, candidate_hash, validation_protocol_hash, lineage_root, "
                "family_id, created_at_epoch_us) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            ),
            values=values,
            conflict_reason="statistical_trial_immutable_conflict",
        )

    def add_operational_attempt(
        self,
        campaign_id: ExperimentId,
        attempt: OperationalAttempt,
        *,
        created_at_epoch_us: int,
    ) -> None:
        """Append a retry attempt without incrementing the statistical trial count."""
        logical = attempt.logical_trial
        connection = self._database.get_connection()
        trial = connection.execute(
            """
            SELECT trial_key, lineage_root, family_id
            FROM research_statistical_trial
            WHERE campaign_id=? AND origin_experiment_id=? AND candidate_id=?
              AND logical_ordinal=? AND parameter_hash=?
            """,
            (
                str(campaign_id),
                str(logical.origin_experiment_id),
                str(logical.candidate_id),
                logical.ordinal,
                str(logical.parameter_hash),
            ),
        ).fetchone()
        if trial is None:
            raise _integrity(
                "operational attempt references an absent statistical trial",
                "statistical_trial_not_found",
            )
        if (
            trial["lineage_root"] != str(attempt.lineage_root)
            or trial["family_id"] != attempt.family_id
        ):
            raise _integrity(
                "operational attempt resets trial lineage or family",
                "operational_attempt_lineage_mismatch",
            )
        values = (
            str(attempt.attempt_id),
            trial["trial_key"],
            attempt.ordinal,
            (
                None
                if attempt.parent_attempt_id is None
                else str(attempt.parent_attempt_id)
            ),
            str(attempt.lineage_root),
            attempt.family_id,
            created_at_epoch_us,
        )
        self._insert_immutable(
            operation="operational attempt insert",
            select_sql=(
                "SELECT attempt_id, trial_key, ordinal, parent_attempt_id, "
                "lineage_root, "
                "family_id, created_at_epoch_us FROM research_operational_attempt "
                "WHERE attempt_id=?"
            ),
            select_parameters=(str(attempt.attempt_id),),
            insert_sql=(
                "INSERT INTO research_operational_attempt(attempt_id, trial_key, "
                "ordinal, "
                "parent_attempt_id, lineage_root, family_id, created_at_epoch_us) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)"
            ),
            values=values,
            conflict_reason="operational_attempt_immutable_conflict",
        )

    def add_code_artifact(
        self, artifact: ResearchCodeArtifact, *, created_at_epoch_us: int
    ) -> None:
        """Insert content-addressed source, dependency, image, and schema evidence."""
        dependencies = json.dumps(
            list(artifact.dependencies), ensure_ascii=False, separators=(",", ":")
        )
        values = (
            str(artifact.artifact_hash),
            artifact.source_code,
            str(artifact.source_hash),
            str(artifact.canonical_ast_hash),
            str(artifact.dependency_lock_hash),
            dependencies,
            str(artifact.image_digest),
            str(artifact.input_schema_hash),
            str(artifact.output_schema_hash),
            created_at_epoch_us,
        )
        self._insert_immutable(
            operation="code artifact insert",
            select_sql=(
                "SELECT artifact_hash, source_code, source_hash, canonical_ast_hash, "
                "dependency_lock_hash, dependencies_json, image_digest, "
                "input_schema_hash, "
                "output_schema_hash, created_at_epoch_us FROM research_code_artifact "
                "WHERE artifact_hash=?"
            ),
            select_parameters=(str(artifact.artifact_hash),),
            insert_sql=(
                "INSERT INTO research_code_artifact(artifact_hash, source_code, "
                "source_hash, canonical_ast_hash, dependency_lock_hash, "
                "dependencies_json, image_digest, "
                "input_schema_hash, output_schema_hash, created_at_epoch_us) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            ),
            values=values,
            conflict_reason="research_code_immutable_conflict",
        )

    def add_sandbox_execution(self, record: SandboxExecutionRecord) -> None:
        """Insert host-attested sandbox I/O without trusting performance claims."""
        manifest = record.manifest
        limits = manifest.resource_limits
        values = (
            str(manifest.attestation_hash),
            str(record.campaign_id),
            None if record.attempt_id is None else str(record.attempt_id),
            str(manifest.code_artifact_hash),
            str(manifest.runtime_digest),
            limits.cpu_count,
            limits.memory_bytes,
            limits.process_limit,
            limits.temporary_storage_bytes,
            limits.wall_time_seconds,
            limits.output_bytes,
            str(manifest.input_hash),
            None if manifest.output_hash is None else str(manifest.output_hash),
            manifest.seed,
            manifest.exit_status.value,
            manifest.exit_code,
            record.created_at_epoch_us,
        )
        self._insert_immutable(
            operation="sandbox manifest insert",
            select_sql=(
                "SELECT attestation_hash, campaign_id, attempt_id, code_artifact_hash, "
                "runtime_digest, cpu_count, memory_bytes, process_limit, "
                "temporary_storage_bytes, wall_time_seconds, output_bytes, input_hash, "
                "output_hash, seed, exit_status, exit_code, created_at_epoch_us "
                "FROM sandbox_execution_manifest WHERE attestation_hash=?"
            ),
            select_parameters=(str(manifest.attestation_hash),),
            insert_sql=(
                "INSERT INTO sandbox_execution_manifest(attestation_hash, campaign_id, "
                "attempt_id, code_artifact_hash, runtime_digest, cpu_count, "
                "memory_bytes, process_limit, temporary_storage_bytes, "
                "wall_time_seconds, output_bytes, input_hash, output_hash, seed, "
                "exit_status, exit_code, created_at_epoch_us) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            ),
            values=values,
            conflict_reason="sandbox_manifest_immutable_conflict",
        )

    def add_feedback(self, record: ResearchFeedbackRecord) -> None:
        """Insert PIT-visible, host-grounded feedback as an immutable fact."""
        feedback = record.feedback
        values = (
            record.feedback_id,
            str(feedback.campaign_id),
            str(feedback.candidate_id),
            str(feedback.evaluation_result_hash),
            feedback.summary,
            _json_sequence(feedback.evidence_refs),
            epoch_us(feedback.outcome_known_at),
            str(feedback.snapshot_id),
            feedback.source.value,
        )
        self._insert_immutable(
            operation="research feedback insert",
            select_sql=(
                "SELECT feedback_id, campaign_id, candidate_id, "
                "evaluation_result_hash, summary, evidence_refs_json, "
                "outcome_known_at_epoch_us, snapshot_id, source "
                "FROM research_feedback WHERE feedback_id=?"
            ),
            select_parameters=(record.feedback_id,),
            insert_sql=(
                "INSERT INTO research_feedback(feedback_id, campaign_id, candidate_id, "
                "evaluation_result_hash, summary, evidence_refs_json, "
                "outcome_known_at_epoch_us, snapshot_id, source) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
            ),
            values=values,
            conflict_reason="research_feedback_immutable_conflict",
        )

    def add_knowledge(self, item: KnowledgeItem) -> None:
        """Insert one immutable knowledge claim and its initial status."""
        values = (
            item.knowledge_id,
            str(item.campaign_id),
            item.claim,
            item.scope.value,
            item.scope_ref,
            _json_sequence(item.evidence_refs),
            epoch_us(item.outcome_known_at),
            str(item.snapshot_id),
            item.source.value,
            str(item.source_hash),
            item.status.value,
            (
                None
                if item.promotion_receipt_hash is None
                else str(item.promotion_receipt_hash)
            ),
            (
                None
                if item.independent_evidence_hash is None
                else str(item.independent_evidence_hash)
            ),
        )
        self._insert_immutable(
            operation="research knowledge insert",
            select_sql=(
                "SELECT knowledge_id, campaign_id, claim, scope, scope_ref, "
                "evidence_refs_json, outcome_known_at_epoch_us, snapshot_id, source, "
                "source_hash, initial_status, promotion_receipt_hash, "
                "independent_evidence_hash FROM research_knowledge WHERE knowledge_id=?"
            ),
            select_parameters=(item.knowledge_id,),
            insert_sql=(
                "INSERT INTO research_knowledge(knowledge_id, campaign_id, claim, "
                "scope, scope_ref, evidence_refs_json, outcome_known_at_epoch_us, "
                "snapshot_id, "
                "source, source_hash, initial_status, promotion_receipt_hash, "
                "independent_evidence_hash) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            ),
            values=values,
            conflict_reason="research_knowledge_immutable_conflict",
        )

    def append_knowledge_status_event(self, event: KnowledgeStatusEvent) -> None:
        """Append one monotonic status transition with a contiguous ordinal."""
        connection = self._database.get_connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """
                SELECT event_id, knowledge_id, previous_status, status,
                       outcome_known_at_epoch_us, evidence_hash
                FROM research_knowledge_status_event WHERE event_id=?
                """,
                (event.event_id,),
            ).fetchone()
            expected = (
                event.event_id,
                event.knowledge_id,
                event.previous_status.value,
                event.status.value,
                epoch_us(event.outcome_known_at),
                str(event.evidence_hash),
            )
            if existing is not None:
                if tuple(existing) == expected:
                    connection.commit()
                    return
                raise _conflict("knowledge_status_event_immutable_conflict")
            row = connection.execute(
                """
                SELECT COALESCE(MAX(ordinal), 0) + 1
                FROM research_knowledge_status_event WHERE knowledge_id=?
                """,
                (event.knowledge_id,),
            ).fetchone()
            ordinal = int(row[0])
            connection.execute(
                """
                INSERT INTO research_knowledge_status_event(
                    event_id, knowledge_id, ordinal, previous_status, status,
                    outcome_known_at_epoch_us, evidence_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.knowledge_id,
                    ordinal,
                    event.previous_status.value,
                    event.status.value,
                    epoch_us(event.outcome_known_at),
                    str(event.evidence_hash),
                ),
            )
            connection.commit()
        except AnalysisError:
            connection.rollback()
            raise
        except sqlite3.Error as exc:
            connection.rollback()
            raise _persistence("knowledge status append", exc) from exc


__all__ = ["SQLiteCampaignWriter"]
