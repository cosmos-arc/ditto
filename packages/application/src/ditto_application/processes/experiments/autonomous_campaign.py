"""Governed autonomous Campaign coordination over immutable research facts."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import cast

from ditto_analysis.experiments.campaign import (
    ResearchCampaignManifest,
    ResearchCandidateSpec,
)
from ditto_analysis.experiments.campaign_persistence import (
    CampaignEventRecord,
    CampaignManifestRecord,
    CampaignReaderProtocol,
    CampaignWriterProtocol,
    CandidateLineageRecord,
)
from ditto_analysis.experiments.metric_schema import R3_RESEARCH_METRIC_SCHEMA
from ditto_analysis.experiments.models import CandidateId, ExperimentId
from ditto_analysis.experiments.search_ledger import (
    OperationalAttempt,
    StatisticalTrial,
)

from ditto_application.agent_campaign_contracts import (
    CampaignCandidateProposalCommand,
    CampaignCandidateReceipt,
)
from ditto_application.exceptions import AppProcessError
from ditto_application.mutation_idempotency import canonical_request_hash
from ditto_application.processes.experiments._autonomous_campaign_contracts import (
    NO_IMPROVEMENT_GENERATION_LIMIT,
    TERMINAL_CAMPAIGN_STATUSES,
    CampaignAuthorizationProof,
    CampaignCoordinatorState,
    CampaignCoordinatorStatus,
    CampaignEvaluationObservation,
    CampaignManifestView,
    CampaignScheduledTrial,
    CampaignTrialRetryRequest,
    CampaignTrialScheduleRequest,
    CampaignTrialSchedulerPort,
    campaign_epoch_us,
    campaign_error,
    campaign_event_id,
    campaign_tool_is_forbidden,
    datetime_from_epoch_us,
    decode_campaign_detail,
    require_content_hash,
    require_text,
    require_utc,
)
from ditto_application.processes.experiments._autonomous_campaign_support import (
    AutonomousCampaignSupport,
)

__all__ = [
    "AutonomousCampaignCoordinator",
    "CampaignAuthorizationProof",
    "CampaignCoordinatorState",
    "CampaignCoordinatorStatus",
    "CampaignEvaluationObservation",
    "CampaignScheduledTrial",
    "CampaignTrialRetryRequest",
    "CampaignTrialScheduleRequest",
    "CampaignTrialSchedulerPort",
]


class AutonomousCampaignCoordinator(AutonomousCampaignSupport):
    """Coordinate bounded proposals while the trusted host owns all decisions."""

    def __init__(
        self,
        *,
        reader: CampaignReaderProtocol,
        writer: CampaignWriterProtocol,
        scheduler: CampaignTrialSchedulerPort,
    ) -> None:
        self._reader = reader
        self._writer = writer
        self._scheduler = scheduler

    def authorize(
        self,
        manifest: ResearchCampaignManifest,
        proof: CampaignAuthorizationProof,
        *,
        occurred_at: datetime,
    ) -> CampaignCoordinatorState:
        """Freeze an exact manifest/authority pair and seed its baseline lineage."""
        now = require_utc(occurred_at, "occurred_at")
        if (
            type(manifest) is not ResearchCampaignManifest
            or type(proof) is not CampaignAuthorizationProof
        ):
            raise campaign_error(
                "campaign authorization inputs are invalid",
                code="CAMPAIGN_AUTHORIZATION_INVALID",
                reason="campaign_authorization_integrity_invalid",
            )
        if not proof.verify_integrity():
            raise campaign_error(
                "campaign authorization proof was modified",
                code="CAMPAIGN_AUTHORIZATION_INVALID",
                reason="campaign_authorization_integrity_invalid",
            )
        if any(campaign_tool_is_forbidden(tool) for tool in manifest.allowed_tools):
            raise campaign_error(
                "campaign authority includes a forbidden capability",
                code="CAMPAIGN_AUTHORITY_FORBIDDEN",
                reason="campaign_authority_forbidden",
            )
        expected = self._manifest_authority(manifest)
        observed = (
            proof.campaign_manifest_hash,
            proof.search_axis,
            tuple(proof.allowed_tools),
            proof.source_snapshot_id,
            proof.candidate_limit,
            proof.fold_run_limit,
            proof.generation_limit,
            proof.concurrent_sandbox_limit,
            proof.wall_time_limit_seconds,
            proof.temporary_storage_limit_bytes,
            proof.model_spend_limit_usd_micros,
        )
        if observed != expected or now < proof.authorized_at or now > proof.expires_at:
            raise campaign_error(
                "campaign authority does not exactly match the manifest",
                code="CAMPAIGN_AUTHORITY_MISMATCH",
                reason="campaign_authority_mismatch",
            )
        existing = self._reader.get_campaign(manifest.campaign_id)
        if existing is not None and existing.manifest_hash != manifest.manifest_hash:
            raise campaign_error(
                "campaign identity is already bound to another manifest",
                code="CAMPAIGN_AUTHORITY_MISMATCH",
                reason="campaign_authority_mismatch",
            )
        epoch = (
            campaign_epoch_us(now) if existing is None else existing.created_at_epoch_us
        )
        event_time = datetime_from_epoch_us(epoch)
        self._writer.add_campaign(
            CampaignManifestRecord.from_manifest(manifest, created_at_epoch_us=epoch)
        )
        self._writer.add_candidate(
            CandidateLineageRecord(
                campaign_id=manifest.campaign_id,
                candidate=manifest.baseline_candidate,
                generation=0,
                created_at_epoch_us=epoch,
            )
        )
        self._append_event(
            manifest.campaign_id,
            event_type="campaign_created",
            status=CampaignCoordinatorStatus.DRAFT,
            detail={"manifest_hash": str(manifest.manifest_hash)},
            occurred_at=event_time,
            identity={"manifest_hash": str(manifest.manifest_hash)},
        )
        self._append_event(
            manifest.campaign_id,
            event_type="campaign_authorized",
            status=CampaignCoordinatorStatus.AUTHORIZED,
            detail={
                "proof": proof.canonical_payload(),
                "verification_hash": proof.verification_hash,
            },
            occurred_at=event_time,
            identity={"authorization_hash": proof.authorization_hash},
        )
        return self.get_state(manifest.campaign_id)

    def propose_candidate(
        self,
        command: CampaignCandidateProposalCommand,
        *,
        occurred_at: datetime,
    ) -> CampaignCandidateReceipt:
        """Commit or exactly replay one authorized candidate proposal."""
        if type(command) is not CampaignCandidateProposalCommand:
            raise campaign_error(
                "command must be CampaignCandidateProposalCommand",
                code="CAMPAIGN_INPUT_INVALID",
                reason="campaign_input_invalid",
            )
        campaign_id = ExperimentId(command.campaign_id)
        now = require_utc(occurred_at, "occurred_at")
        _, view, proof = self._authorized(campaign_id, now)
        self._validate_command_authority(command, proof)
        self._require_proposable(campaign_id)
        candidate_record = self._prepare_candidate(
            command,
            campaign_id=campaign_id,
            view=view,
            occurred_at=now,
        )
        event = self._dispatch_candidate(
            command,
            campaign_id=campaign_id,
            candidate_record=candidate_record,
            view=view,
            occurred_at=now,
        )
        return self._receipt(command, candidate_record, event)

    def _require_proposable(self, campaign_id: ExperimentId) -> None:
        state = self.get_state(campaign_id)
        if state.status.value in TERMINAL_CAMPAIGN_STATUSES:
            raise campaign_error(
                "campaign is terminal",
                code="CAMPAIGN_TERMINAL",
                reason="campaign_terminal",
            )
        if state.status is CampaignCoordinatorStatus.PAUSED_BUDGET:
            raise campaign_error(
                "campaign budget is exhausted",
                code="CAMPAIGN_BUDGET_EXHAUSTED",
                reason="campaign_candidate_budget_exhausted",
            )

    def _prepare_candidate(
        self,
        command: CampaignCandidateProposalCommand,
        *,
        campaign_id: ExperimentId,
        view: CampaignManifestView,
        occurred_at: datetime,
    ) -> CandidateLineageRecord:
        candidates = self._reader.list_candidates(campaign_id)
        parent = next(
            (
                item
                for item in candidates
                if str(item.candidate.candidate.candidate_id)
                == command.parent_candidate_id
            ),
            None,
        )
        if parent is None:
            raise campaign_error(
                "candidate parent is absent",
                code="CAMPAIGN_LINEAGE_INVALID",
                reason="campaign_parent_not_found",
            )
        candidate_id = CandidateId(
            "candidate-"
            + canonical_request_hash(self._candidate_material(command))[:24]
        )
        existing = next(
            (
                item
                for item in candidates
                if item.candidate.candidate.candidate_id == candidate_id
            ),
            None,
        )
        generation = parent.generation + 1
        if existing is not None:
            if (
                existing.candidate.parent_candidate_id
                != parent.candidate.candidate.candidate_id
            ):
                raise campaign_error(
                    "candidate identity was rebound to another parent",
                    code="CAMPAIGN_LINEAGE_INVALID",
                    reason="campaign_candidate_identity_conflict",
                )
            return existing
        self._enforce_candidate_creation_budget(
            command,
            campaign_id=campaign_id,
            candidate_count=len(candidates),
            generation=generation,
            view=view,
            occurred_at=occurred_at,
        )
        candidate = self._build_candidate(
            command,
            candidate_id=candidate_id,
            ordinal=len(candidates) + 1,
            generation=generation,
            search_axis=view.search_axis,
        )
        record = CandidateLineageRecord(
            campaign_id=campaign_id,
            candidate=candidate,
            generation=generation,
            created_at_epoch_us=campaign_epoch_us(occurred_at),
        )
        self._writer.add_candidate(record)
        return record

    def _enforce_candidate_creation_budget(
        self,
        command: CampaignCandidateProposalCommand,
        *,
        campaign_id: ExperimentId,
        candidate_count: int,
        generation: int,
        view: CampaignManifestView,
        occurred_at: datetime,
    ) -> None:
        if candidate_count >= view.candidate_limit:
            reason = "campaign_candidate_budget_exhausted"
        elif generation > view.generation_limit:
            reason = "campaign_generation_budget_exhausted"
        else:
            return
        self._pause_budget(
            campaign_id,
            reason=reason,
            occurred_at=occurred_at,
            identity={"request_hash": command.request_hash},
        )
        raise campaign_error(
            "campaign candidate creation budget is exhausted",
            code="CAMPAIGN_BUDGET_EXHAUSTED",
            reason=reason,
        )

    def _dispatch_candidate(
        self,
        command: CampaignCandidateProposalCommand,
        *,
        campaign_id: ExperimentId,
        candidate_record: CandidateLineageRecord,
        view: CampaignManifestView,
        occurred_at: datetime,
    ) -> CampaignEventRecord:
        candidate = candidate_record.candidate
        candidate_id = candidate.candidate.candidate_id
        dispatch_id = campaign_event_id(
            "candidate-dispatched",
            {"campaign_id": command.campaign_id, "candidate_id": str(candidate_id)},
        )
        existing_dispatch = self._find_event(campaign_id, dispatch_id)
        if existing_dispatch is not None:
            return existing_dispatch
        trial = self._trial(
            campaign_id,
            candidate,
            view.validation_protocol_hash,
            view.lineage_root,
        )
        existing_trial, existing_attempt = self._candidate_ledger_facts(
            campaign_id,
            candidate_id,
        )
        fold_run_count = self._schedule_trial(
            campaign_id,
            candidate,
            trial,
            fold_run_limit=view.fold_run_limit,
            occurred_at=occurred_at,
        )
        created_epoch = candidate_record.created_at_epoch_us
        if existing_trial is None:
            self._writer.add_statistical_trial(
                campaign_id,
                trial,
                created_at_epoch_us=created_epoch,
            )
        if existing_attempt is None:
            self._writer.add_operational_attempt(
                campaign_id,
                self._attempt(trial, ordinal=1, retry_id="initial", parent=None),
                created_at_epoch_us=created_epoch,
            )
        event = self._append_event(
            campaign_id,
            event_type="candidate_dispatched",
            status=CampaignCoordinatorStatus.RUNNING,
            detail={
                "candidate_id": str(candidate_id),
                "candidate_hash": str(candidate.candidate_hash),
                "generation": candidate_record.generation,
                "request_hash": command.request_hash,
                "fold_run_count": fold_run_count,
            },
            occurred_at=occurred_at,
            identity={"candidate_id": str(candidate_id)},
        )
        return event

    def _candidate_ledger_facts(
        self,
        campaign_id: ExperimentId,
        candidate_id: CandidateId,
    ) -> tuple[StatisticalTrial | None, OperationalAttempt | None]:
        ledger = self._reader.get_search_ledger(campaign_id)
        if ledger is None:
            return None, None
        trial = next(
            (
                item
                for item in ledger.statistical_trials
                if item.logical_trial.candidate_id == candidate_id
            ),
            None,
        )
        attempt = next(
            (
                item
                for item in ledger.operational_attempts
                if item.logical_trial.candidate_id == candidate_id and item.ordinal == 1
            ),
            None,
        )
        return trial, attempt

    def _schedule_trial(
        self,
        campaign_id: ExperimentId,
        candidate: ResearchCandidateSpec,
        trial: StatisticalTrial,
        *,
        fold_run_limit: int,
        occurred_at: datetime,
    ) -> int:
        remaining = fold_run_limit - self._fold_run_count(campaign_id)
        if remaining <= 0:
            self._pause_fold_budget(campaign_id, candidate, occurred_at)
        try:
            scheduled = self._scheduler.schedule_trial(
                CampaignTrialScheduleRequest(
                    campaign_id=campaign_id,
                    candidate=candidate,
                    trial=trial,
                    fold_run_budget_remaining=remaining,
                ),
                now_epoch_us=campaign_epoch_us(occurred_at),
            )
            self._validate_lease(
                scheduled.lease,
                campaign_id,
                campaign_epoch_us(occurred_at),
            )
        except AppProcessError as exc:
            if exc.details.get("reason") == "campaign_lease_lost":
                self._pause_for_lost_lease(campaign_id, candidate, occurred_at)
            raise
        if scheduled.fold_run_count > remaining:
            self._pause_fold_budget(campaign_id, candidate, occurred_at)
        return scheduled.fold_run_count

    def _pause_fold_budget(
        self,
        campaign_id: ExperimentId,
        candidate: ResearchCandidateSpec,
        occurred_at: datetime,
    ) -> None:
        self._pause_budget(
            campaign_id,
            reason="campaign_fold_budget_exhausted",
            occurred_at=occurred_at,
            identity={"candidate_id": str(candidate.candidate.candidate_id)},
        )
        raise campaign_error(
            "campaign fold budget is exhausted",
            code="CAMPAIGN_BUDGET_EXHAUSTED",
            reason="campaign_fold_budget_exhausted",
        )

    def _pause_for_lost_lease(
        self,
        campaign_id: ExperimentId,
        candidate: ResearchCandidateSpec,
        occurred_at: datetime,
    ) -> None:
        self._append_event(
            campaign_id,
            event_type="campaign_paused",
            status=CampaignCoordinatorStatus.PAUSED,
            detail={"reason": "campaign_lease_lost"},
            occurred_at=occurred_at,
            identity={
                "candidate_id": str(candidate.candidate.candidate_id),
                "reason": "lease",
            },
        )

    def retry_candidate(
        self,
        campaign_id: ExperimentId,
        candidate_id: CandidateId,
        *,
        authorization_hash: str,
        retry_id: str,
        occurred_at: datetime,
    ) -> CampaignCoordinatorState:
        """Schedule one operational retry without incrementing trial count."""
        now = require_utc(occurred_at, "occurred_at")
        _, _, proof = self._authorized(campaign_id, now)
        if (
            require_content_hash(authorization_hash, "authorization_hash")
            != proof.authorization_hash
        ):
            raise campaign_error(
                "campaign authorization hash drifted",
                code="CAMPAIGN_AUTHORITY_MISMATCH",
                reason="campaign_authority_mismatch",
            )
        retry_identity = require_text(retry_id, "retry_id")
        if self.get_state(campaign_id).status.value in TERMINAL_CAMPAIGN_STATUSES:
            raise campaign_error(
                "campaign is terminal",
                code="CAMPAIGN_TERMINAL",
                reason="campaign_terminal",
            )
        ledger = self._reader.get_search_ledger(campaign_id)
        if ledger is None:
            raise campaign_error(
                "candidate trial is absent",
                code="CAMPAIGN_TRIAL_NOT_FOUND",
                reason="campaign_trial_not_found",
            )
        trial = next(
            (
                item
                for item in ledger.statistical_trials
                if item.logical_trial.candidate_id == candidate_id
            ),
            None,
        )
        if trial is None:
            raise campaign_error(
                "candidate trial is absent",
                code="CAMPAIGN_TRIAL_NOT_FOUND",
                reason="campaign_trial_not_found",
            )
        attempts = tuple(
            item
            for item in ledger.operational_attempts
            if item.logical_trial == trial.logical_trial
        )
        event_identity = {
            "candidate_id": str(candidate_id),
            "retry_id": retry_identity,
        }
        event_id = campaign_event_id("candidate-retried", event_identity)
        if self._find_event(campaign_id, event_id) is not None:
            return self.get_state(campaign_id)
        attempt_id = self._attempt_id(trial, retry_identity)
        existing_attempt = next(
            (
                item
                for item in ledger.operational_attempts
                if item.attempt_id == attempt_id
            ),
            None,
        )
        if existing_attempt is None:
            ordinal = len(attempts) + 1
            parent = max(attempts, key=lambda item: item.ordinal).attempt_id
            attempt = self._attempt(
                trial,
                ordinal=ordinal,
                retry_id=retry_identity,
                parent=parent,
            )
            lease = self._scheduler.schedule_retry(
                CampaignTrialRetryRequest(
                    campaign_id=campaign_id,
                    trial=trial,
                    retry_id=retry_identity,
                    next_attempt_ordinal=ordinal,
                ),
                now_epoch_us=campaign_epoch_us(now),
            )
            self._validate_lease(lease, campaign_id, campaign_epoch_us(now))
            candidate_record = next(
                item
                for item in self._reader.list_candidates(campaign_id)
                if item.candidate.candidate.candidate_id == candidate_id
            )
            self._writer.add_operational_attempt(
                campaign_id,
                attempt,
                created_at_epoch_us=candidate_record.created_at_epoch_us,
            )
        else:
            ordinal = existing_attempt.ordinal
        self._append_event(
            campaign_id,
            event_type="candidate_retried",
            status=CampaignCoordinatorStatus.RUNNING,
            detail={
                "candidate_id": str(candidate_id),
                "retry_id": retry_identity,
                "attempt_ordinal": ordinal,
            },
            occurred_at=now,
            identity=event_identity,
        )
        return self.get_state(campaign_id)

    def record_evaluation(
        self,
        campaign_id: ExperimentId,
        observation: CampaignEvaluationObservation,
        *,
        occurred_at: datetime,
    ) -> CampaignCoordinatorState:
        """Record trusted evaluation evidence and apply the host stopping rule."""
        now = require_utc(occurred_at, "occurred_at")
        _, view, _ = self._authorized(campaign_id, now)
        if self.get_state(campaign_id).status.value in TERMINAL_CAMPAIGN_STATUSES:
            raise campaign_error(
                "campaign is terminal",
                code="CAMPAIGN_TERMINAL",
                reason="campaign_terminal",
            )
        if type(observation) is not CampaignEvaluationObservation:
            raise campaign_error(
                "observation must be CampaignEvaluationObservation",
                code="CAMPAIGN_EVALUATION_INVALID",
                reason="campaign_evaluation_invalid",
            )
        candidate_record = next(
            (
                item
                for item in self._reader.list_candidates(campaign_id)
                if item.candidate.candidate.candidate_id
                == observation.result.candidate_id
            ),
            None,
        )
        if (
            candidate_record is None
            or observation.result.candidate_hash
            != candidate_record.candidate.candidate_hash
            or observation.result.validation_protocol_hash
            != view.validation_protocol_hash
        ):
            raise campaign_error(
                "evaluation does not match the immutable candidate protocol",
                code="CAMPAIGN_EVALUATION_INVALID",
                reason="campaign_evaluation_identity_mismatch",
            )
        event_identity = {
            "candidate_id": str(observation.result.candidate_id),
            "metrics_artifact_hash": str(observation.result.metrics_artifact_hash),
        }
        event_id = campaign_event_id("candidate-evaluated", event_identity)
        if self._find_event(campaign_id, event_id) is not None:
            return self.get_state(campaign_id)
        previous = self.get_state(campaign_id).best_primary_metric_value
        improved = observation.result.constraints_passed and self._improved(
            view.primary_metric_id,
            observation.primary_metric_value,
            previous,
        )
        self._append_event(
            campaign_id,
            event_type="candidate_evaluated",
            status=CampaignCoordinatorStatus.RUNNING,
            detail={
                **event_identity,
                "candidate_hash": str(observation.result.candidate_hash),
                "generation": candidate_record.generation,
                "primary_metric_value": observation.primary_metric_value,
                "constraints_passed": observation.result.constraints_passed,
                "generation_complete": observation.generation_complete,
                "improved": improved,
            },
            occurred_at=now,
            identity=event_identity,
        )
        state = self.get_state(campaign_id)
        if state.no_improvement_generations >= NO_IMPROVEMENT_GENERATION_LIMIT:
            self._append_event(
                campaign_id,
                event_type="campaign_completed",
                status=CampaignCoordinatorStatus.COMPLETED,
                detail={"reason": "two_generations_without_improvement"},
                occurred_at=now,
                identity={"stopping_rule": "two_generations_without_improvement"},
            )
        return self.get_state(campaign_id)

    def cancel(
        self,
        campaign_id: ExperimentId,
        *,
        authorization_hash: str,
        occurred_at: datetime,
    ) -> CampaignCoordinatorState:
        """Request and durably complete idempotent Campaign cancellation."""
        now = require_utc(occurred_at, "occurred_at")
        provided_hash = require_content_hash(authorization_hash, "authorization_hash")
        state = self.get_state(campaign_id)
        if state.status is CampaignCoordinatorStatus.CANCELLED:
            if state.authorization_hash != provided_hash:
                raise campaign_error(
                    "campaign authorization hash drifted",
                    code="CAMPAIGN_AUTHORITY_MISMATCH",
                    reason="campaign_authority_mismatch",
                )
            return state
        _, _, proof = self._authorized(campaign_id, now)
        if provided_hash != proof.authorization_hash:
            raise campaign_error(
                "campaign authorization hash drifted",
                code="CAMPAIGN_AUTHORITY_MISMATCH",
                reason="campaign_authority_mismatch",
            )
        if state.status.value in TERMINAL_CAMPAIGN_STATUSES:
            return state
        self._append_event(
            campaign_id,
            event_type="campaign_cancel_requested",
            status=CampaignCoordinatorStatus.CANCEL_REQUESTED,
            detail={"authorization_hash": proof.authorization_hash},
            occurred_at=now,
            identity={"authorization_hash": proof.authorization_hash},
        )
        self._scheduler.cancel_campaign(
            campaign_id, now_epoch_us=campaign_epoch_us(now)
        )
        self._append_event(
            campaign_id,
            event_type="campaign_cancelled",
            status=CampaignCoordinatorStatus.CANCELLED,
            detail={"authorization_hash": proof.authorization_hash},
            occurred_at=now,
            identity={"authorization_hash": proof.authorization_hash},
        )
        return self.get_state(campaign_id)

    def get_state(self, campaign_id: ExperimentId) -> CampaignCoordinatorState:
        """Reconstruct status, budgets, and stopping projection from durable facts."""
        record = self._reader.get_campaign(campaign_id)
        if record is None:
            raise campaign_error(
                "campaign was not found",
                code="CAMPAIGN_NOT_FOUND",
                reason="campaign_not_found",
            )
        view = self._view(record)
        events = self._reader.list_campaign_events(campaign_id)
        status = (
            CampaignCoordinatorStatus.DRAFT
            if not events
            else CampaignCoordinatorStatus(events[-1].status)
        )
        authorization_hash: str | None = None
        direction = R3_RESEARCH_METRIC_SCHEMA.definition(
            view.primary_metric_id
        ).direction
        for event in events:
            detail = decode_campaign_detail(event.detail_payload)
            if event.event_type == "campaign_authorized":
                raw_proof = detail.get("proof")
                if isinstance(raw_proof, Mapping):
                    proof_payload = cast("Mapping[str, object]", raw_proof)
                    value = proof_payload.get("authorization_hash")
                    if type(value) is str:
                        authorization_hash = value
        best, no_improvement = self._evaluation_projection(events, direction)
        ledger = self._reader.get_search_ledger(campaign_id)
        return CampaignCoordinatorState(
            campaign_id=campaign_id,
            status=status,
            authorization_hash=authorization_hash,
            best_primary_metric_value=best,
            no_improvement_generations=no_improvement,
            statistical_trial_count=(
                0 if ledger is None else ledger.statistical_trial_count
            ),
            operational_attempt_count=(
                0 if ledger is None else ledger.operational_attempt_count
            ),
            revision=len(events),
        )
