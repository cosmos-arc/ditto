"""Persistence, authorization, and identity support for Campaign coordination."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import cast

from ditto_analysis.experiments.campaign import (
    ResearchCampaignManifest,
    ResearchCandidateSpec,
    SearchAxis,
)
from ditto_analysis.experiments.campaign_persistence import (
    CampaignEventRecord,
    CampaignManifestRecord,
    CampaignReaderProtocol,
    CampaignWriterProtocol,
    CandidateLineageRecord,
)
from ditto_analysis.experiments.metric_schema import (
    R3_RESEARCH_METRIC_SCHEMA,
    ResearchMetricDirection,
    ResearchMetricId,
)
from ditto_analysis.experiments.models import (
    AttemptId,
    CandidateId,
    ContentHash,
    ExperimentId,
)
from ditto_analysis.experiments.persistence import LeaseFence
from ditto_analysis.experiments.search_ledger import (
    OperationalAttempt,
    StatisticalTrial,
)
from ditto_analysis.experiments.specs import CandidateSpec, FrozenValue
from ditto_analysis.experiments.trial_family import (
    LogicalTrialIdentity,
    TrialKind,
)

from ditto_application.agent_campaign_contracts import (
    CampaignCandidateProposalCommand,
    CampaignCandidateReceipt,
)
from ditto_application.processes.experiments._autonomous_campaign_contracts import (
    TERMINAL_CAMPAIGN_STATUSES,
    CampaignAuthorizationProof,
    CampaignCoordinatorStatus,
    CampaignManifestView,
    campaign_epoch_us,
    campaign_error,
    campaign_event_id,
    datetime_from_epoch_us,
    decode_campaign_detail,
    encode_campaign_detail,
)


class AutonomousCampaignSupport:
    """Private support methods shared by the public coordinator."""

    _reader: CampaignReaderProtocol
    _writer: CampaignWriterProtocol

    def _evaluation_projection(
        self,
        events: Sequence[CampaignEventRecord],
        direction: ResearchMetricDirection,
    ) -> tuple[float | None, int]:
        best: float | None = None
        generation_outcomes: dict[int, bool] = {}
        for event in events:
            if event.event_type != "candidate_evaluated":
                continue
            detail = decode_campaign_detail(event.detail_payload)
            raw_value = detail.get("primary_metric_value")
            if type(raw_value) in {int, float} and detail.get("constraints_passed"):
                value = float(cast("int | float", raw_value))
                if self._direction_improved(direction, value, best):
                    best = value
            generation = detail.get("generation")
            if (
                type(generation) is int
                and generation > 0
                and detail.get("generation_complete") is True
            ):
                previous_outcome = generation_outcomes.get(generation, False)
                generation_outcomes[generation] = (
                    previous_outcome or detail.get("improved") is True
                )
        no_improvement = 0
        for improved in (
            generation_outcomes[generation]
            for generation in sorted(generation_outcomes)
        ):
            no_improvement = 0 if improved else no_improvement + 1
        return best, no_improvement

    @staticmethod
    def _manifest_authority(manifest: ResearchCampaignManifest) -> tuple[object, ...]:
        budget = manifest.budget
        return (
            str(manifest.manifest_hash),
            manifest.search_axis.value,
            tuple(manifest.allowed_tools),
            str(manifest.experiment_plan.snapshot_id),
            budget.experiment_budget.candidate_limit,
            budget.experiment_budget.fold_run_limit,
            budget.generation_limit,
            budget.concurrent_sandbox_limit,
            budget.wall_time_limit_seconds,
            budget.temporary_storage_limit_bytes,
            budget.model_spend_limit_usd_micros,
        )

    def _authorized(
        self,
        campaign_id: ExperimentId,
        now: datetime,
    ) -> tuple[
        CampaignManifestRecord, CampaignManifestView, CampaignAuthorizationProof
    ]:
        record = self._reader.get_campaign(campaign_id)
        if record is None:
            raise campaign_error(
                "campaign was not found",
                code="CAMPAIGN_NOT_FOUND",
                reason="campaign_not_found",
            )
        events = self._reader.list_campaign_events(campaign_id)
        authorization = next(
            (event for event in events if event.event_type == "campaign_authorized"),
            None,
        )
        if authorization is None:
            raise campaign_error(
                "campaign is not authorized",
                code="CAMPAIGN_NOT_AUTHORIZED",
                reason="campaign_not_authorized",
            )
        detail = decode_campaign_detail(authorization.detail_payload)
        raw = detail.get("proof")
        verification = detail.get("verification_hash")
        if not isinstance(raw, Mapping) or type(verification) is not str:
            raise campaign_error(
                "persisted campaign authority is malformed",
                code="CAMPAIGN_INTEGRITY_INVALID",
                reason="campaign_authorization_integrity_invalid",
            )
        proof = self._proof_from_payload(
            cast("Mapping[object, object]", raw), verification
        )
        if not proof.verify_integrity():
            raise campaign_error(
                "persisted campaign authority is invalid",
                code="CAMPAIGN_INTEGRITY_INVALID",
                reason="campaign_authorization_integrity_invalid",
            )
        view = self._view(record)
        elapsed = campaign_epoch_us(now) - record.created_at_epoch_us
        if now > proof.expires_at or elapsed > view.wall_time_limit_seconds * 1_000_000:
            self._pause_budget(
                campaign_id,
                reason="campaign_wall_time_budget_exhausted",
                occurred_at=now,
                identity={"authorization_hash": proof.authorization_hash},
            )
            raise campaign_error(
                "campaign authority has expired",
                code="CAMPAIGN_AUTHORITY_EXPIRED",
                reason="campaign_authority_expired",
            )
        return record, view, proof

    @staticmethod
    def _proof_from_payload(
        raw: Mapping[object, object],
        verification_hash: str,
    ) -> CampaignAuthorizationProof:
        allowed = raw.get("allowed_tools")
        if not isinstance(allowed, Sequence) or isinstance(allowed, (str, bytes)):
            raise campaign_error(
                "persisted allowed_tools is malformed",
                code="CAMPAIGN_INTEGRITY_INVALID",
                reason="campaign_authorization_integrity_invalid",
            )
        values = tuple(cast("Sequence[object]", allowed))
        if any(type(value) is not str for value in values):
            raise campaign_error(
                "persisted allowed_tools is malformed",
                code="CAMPAIGN_INTEGRITY_INVALID",
                reason="campaign_authorization_integrity_invalid",
            )
        return CampaignAuthorizationProof(
            authorization_id=cast("str", raw["authorization_id"]),
            authorization_hash=cast("str", raw["authorization_hash"]),
            authority_hash=cast("str", raw["authority_hash"]),
            authorized_by=cast("str", raw["authorized_by"]),
            authorized_at=datetime.fromisoformat(
                cast("str", raw["authorized_at"]).replace("Z", "+00:00")
            ),
            expires_at=datetime.fromisoformat(
                cast("str", raw["expires_at"]).replace("Z", "+00:00")
            ),
            campaign_manifest_hash=cast("str", raw["campaign_manifest_hash"]),
            search_axis=cast("str", raw["search_axis"]),
            allowed_tools=cast("tuple[str, ...]", values),
            source_snapshot_id=cast("str", raw["source_snapshot_id"]),
            candidate_limit=cast("int", raw["candidate_limit"]),
            fold_run_limit=cast("int", raw["fold_run_limit"]),
            generation_limit=cast("int", raw["generation_limit"]),
            concurrent_sandbox_limit=cast("int", raw["concurrent_sandbox_limit"]),
            wall_time_limit_seconds=cast("int", raw["wall_time_limit_seconds"]),
            temporary_storage_limit_bytes=cast(
                "int", raw["temporary_storage_limit_bytes"]
            ),
            model_spend_limit_usd_micros=cast(
                "int", raw["model_spend_limit_usd_micros"]
            ),
            verification_hash=verification_hash,
        )

    @staticmethod
    def _view(record: CampaignManifestRecord) -> CampaignManifestView:
        root = decode_campaign_detail(record.manifest_payload)
        plan = cast("Mapping[str, object]", root["experiment_plan"])
        budget = cast("Mapping[str, object]", root["budget"])
        tools = cast("Sequence[str]", root["allowed_tools"])
        return CampaignManifestView(
            primary_metric_id=ResearchMetricId(cast("str", root["primary_metric_id"])),
            validation_protocol_hash=ContentHash(
                cast("str", plan["validation_protocol_hash"])
            ),
            snapshot_id=cast("str", plan["snapshot_id"]),
            search_axis=SearchAxis(cast("str", root["search_axis"])),
            lineage_root=ContentHash(cast("str", root["lineage_root"])),
            candidate_limit=cast("int", budget["candidate_limit"]),
            fold_run_limit=cast("int", budget["fold_run_limit"]),
            generation_limit=cast("int", budget["generation_limit"]),
            concurrent_sandbox_limit=cast("int", budget["concurrent_sandbox_limit"]),
            wall_time_limit_seconds=cast("int", budget["wall_time_limit_seconds"]),
            temporary_storage_limit_bytes=cast(
                "int", budget["temporary_storage_limit_bytes"]
            ),
            model_spend_limit_usd_micros=cast(
                "int", budget["model_spend_limit_usd_micros"]
            ),
            allowed_tools=tuple(tools),
        )

    @staticmethod
    def _validate_command_authority(
        command: CampaignCandidateProposalCommand,
        proof: CampaignAuthorizationProof,
    ) -> None:
        if (
            command.authorization_id != proof.authorization_id
            or command.authorization_hash != proof.authorization_hash
            or command.authority_hash != proof.authority_hash
        ):
            raise campaign_error(
                "candidate proposal authority drifted",
                code="CAMPAIGN_AUTHORITY_MISMATCH",
                reason="campaign_authority_mismatch",
            )

    @staticmethod
    def _candidate_material(
        command: CampaignCandidateProposalCommand,
    ) -> dict[str, object]:
        return {
            "campaign_id": command.campaign_id,
            "parent_candidate_id": command.parent_candidate_id,
            "parameters": dict(command.parameters),
            "factor_code_hash": command.factor_code_hash,
            "model_code_hash": command.model_code_hash,
            "data_requirement_hashes": list(command.data_requirement_hashes),
        }

    @staticmethod
    def _build_candidate(
        command: CampaignCandidateProposalCommand,
        *,
        candidate_id: CandidateId,
        ordinal: int,
        generation: int,
        search_axis: SearchAxis,
    ) -> ResearchCandidateSpec:
        factor_hash = (
            None
            if command.factor_code_hash is None
            else ContentHash(command.factor_code_hash)
        )
        model_hash = (
            None
            if command.model_code_hash is None
            else ContentHash(command.model_code_hash)
        )
        candidate = ResearchCandidateSpec(
            candidate=CandidateSpec(
                candidate_id=candidate_id,
                ordinal=ordinal,
                is_baseline=False,
                parameters=cast("Mapping[str, FrozenValue]", command.parameters),
            ),
            search_axis=search_axis,
            parent_candidate_id=CandidateId(command.parent_candidate_id),
            factor_code_hash=factor_hash,
            model_code_hash=model_hash,
            data_requirement_hashes=tuple(
                ContentHash(item) for item in command.data_requirement_hashes
            ),
        )
        if generation <= 0:
            raise campaign_error(
                "proposed candidate generation must be positive",
                code="CAMPAIGN_LINEAGE_INVALID",
                reason="campaign_generation_invalid",
            )
        return candidate

    @staticmethod
    def _trial(
        campaign_id: ExperimentId,
        candidate: ResearchCandidateSpec,
        validation_protocol_hash: ContentHash,
        lineage_root: ContentHash,
    ) -> StatisticalTrial:
        logical = LogicalTrialIdentity(
            origin_experiment_id=campaign_id,
            candidate_id=candidate.candidate.candidate_id,
            ordinal=candidate.candidate.ordinal,
            parameter_hash=candidate.candidate.parameter_hash,
            kind=TrialKind.CURRENT,
        )
        return StatisticalTrial(
            logical_trial=logical,
            candidate_hash=candidate.candidate_hash,
            validation_protocol_hash=validation_protocol_hash,
            lineage_root=lineage_root,
            family_id=f"campaign-family:{lineage_root}",
        )

    @staticmethod
    def _attempt(
        trial: StatisticalTrial,
        *,
        ordinal: int,
        retry_id: str,
        parent: AttemptId | None,
    ) -> OperationalAttempt:
        return OperationalAttempt(
            attempt_id=AutonomousCampaignSupport._attempt_id(trial, retry_id),
            logical_trial=trial.logical_trial,
            ordinal=ordinal,
            parent_attempt_id=parent,
            lineage_root=trial.lineage_root,
            family_id=trial.family_id,
        )

    @staticmethod
    def _attempt_id(trial: StatisticalTrial, retry_id: str) -> AttemptId:
        digest = hashlib.sha256(
            f"{trial.family_id}:{trial.logical_trial.candidate_id}:{retry_id}".encode()
        ).hexdigest()[:24]
        return AttemptId(f"campaign-attempt-{digest}")

    @staticmethod
    def _validate_lease(
        lease: LeaseFence,
        campaign_id: ExperimentId,
        now_epoch_us: int,
    ) -> None:
        if (
            lease.experiment_id != campaign_id
            or lease.lease_until_epoch_us <= now_epoch_us
        ):
            raise campaign_error(
                "campaign scheduler returned a stale lease",
                code="LEASE_LOST",
                reason="campaign_lease_lost",
            )

    @staticmethod
    def _direction_improved(
        direction: ResearchMetricDirection,
        value: float,
        previous: float | None,
    ) -> bool:
        if previous is None:
            return True
        if direction is ResearchMetricDirection.MAXIMIZE:
            return value > previous
        if direction is ResearchMetricDirection.MINIMIZE:
            return value < previous
        raise campaign_error(
            "context-only metric cannot drive campaign selection",
            code="CAMPAIGN_METRIC_INVALID",
            reason="campaign_primary_metric_not_rankable",
        )

    @classmethod
    def _improved(
        cls,
        metric_id: ResearchMetricId,
        value: float,
        previous: float | None,
    ) -> bool:
        direction = R3_RESEARCH_METRIC_SCHEMA.definition(metric_id).direction
        return cls._direction_improved(direction, value, previous)

    def _append_event(
        self,
        campaign_id: ExperimentId,
        *,
        event_type: str,
        status: CampaignCoordinatorStatus,
        detail: Mapping[str, object],
        occurred_at: datetime,
        identity: Mapping[str, object],
    ) -> CampaignEventRecord:
        event_id = campaign_event_id(
            event_type.replace("_", "-"), {"campaign_id": str(campaign_id), **identity}
        )
        existing = self._find_event(campaign_id, event_id)
        if existing is not None:
            return existing
        events = self._reader.list_campaign_events(campaign_id)
        latest_status = (
            None if not events else CampaignCoordinatorStatus(events[-1].status)
        )
        effective_status = (
            latest_status
            if status is CampaignCoordinatorStatus.RUNNING
            and latest_status is not None
            and (
                latest_status is CampaignCoordinatorStatus.PAUSED_BUDGET
                or latest_status is CampaignCoordinatorStatus.CANCEL_REQUESTED
                or latest_status.value in TERMINAL_CAMPAIGN_STATUSES
            )
            else status
        )
        record = CampaignEventRecord(
            event_id=event_id,
            campaign_id=campaign_id,
            ordinal=len(events),
            event_type=event_type,
            previous_status=None if not events else events[-1].status,
            status=effective_status.value,
            detail_payload=encode_campaign_detail(detail),
            occurred_at_epoch_us=campaign_epoch_us(occurred_at),
        )
        self._writer.append_campaign_event(record)
        return record

    def _find_event(
        self,
        campaign_id: ExperimentId,
        event_id: str,
    ) -> CampaignEventRecord | None:
        return next(
            (
                event
                for event in self._reader.list_campaign_events(campaign_id)
                if event.event_id == event_id
            ),
            None,
        )

    def _pause_budget(
        self,
        campaign_id: ExperimentId,
        *,
        reason: str,
        occurred_at: datetime,
        identity: Mapping[str, object],
    ) -> None:
        self._append_event(
            campaign_id,
            event_type="campaign_paused_budget",
            status=CampaignCoordinatorStatus.PAUSED_BUDGET,
            detail={"reason": reason},
            occurred_at=occurred_at,
            identity={**identity, "reason": reason},
        )

    def _fold_run_count(self, campaign_id: ExperimentId) -> int:
        reservations: dict[str, int] = {}
        dispatches: dict[str, int] = {}
        for event in self._reader.list_campaign_events(campaign_id):
            if event.event_type not in {
                "candidate_fold_reserved",
                "candidate_dispatched",
            }:
                continue
            detail = decode_campaign_detail(event.detail_payload)
            candidate_id = cast("str", detail["candidate_id"])
            count = cast("int", detail["fold_run_count"])
            target = (
                reservations
                if event.event_type == "candidate_fold_reserved"
                else dispatches
            )
            target[candidate_id] = count
        return sum(reservations.values()) + sum(
            count
            for candidate_id, count in dispatches.items()
            if candidate_id not in reservations
        )

    def _candidate_fold_count(
        self,
        campaign_id: ExperimentId,
        candidate_id: CandidateId,
    ) -> int:
        dispatched = 0
        for event in self._reader.list_campaign_events(campaign_id):
            if event.event_type not in {
                "candidate_fold_reserved",
                "candidate_dispatched",
            }:
                continue
            detail = decode_campaign_detail(event.detail_payload)
            if detail.get("candidate_id") == str(candidate_id):
                count = cast("int", detail["fold_run_count"])
                if event.event_type == "candidate_fold_reserved":
                    return count
                dispatched = count
        return dispatched

    @staticmethod
    def _receipt(
        command: CampaignCandidateProposalCommand,
        candidate: CandidateLineageRecord,
        event: CampaignEventRecord,
    ) -> CampaignCandidateReceipt:
        return CampaignCandidateReceipt.issue(
            command=command,
            candidate_id=str(candidate.candidate.candidate.candidate_id),
            candidate_hash=str(candidate.candidate.candidate_hash),
            generation=candidate.generation,
            status=event.status,
            event_id=event.event_id,
            occurred_at=datetime_from_epoch_us(event.occurred_at_epoch_us),
        )
