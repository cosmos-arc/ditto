"""Draft and exact-approval lifecycle for governed Campaign coordination."""

from __future__ import annotations

from datetime import datetime

from ditto_analysis.experiments.campaign import ResearchCampaignManifest
from ditto_analysis.experiments.campaign_persistence import (
    CampaignManifestRecord,
    CandidateLineageRecord,
)
from ditto_analysis.experiments.models import ExperimentId

from ditto_application.processes.experiments._autonomous_campaign_contracts import (
    CampaignAuthorizationProof,
    CampaignCoordinatorState,
    CampaignCoordinatorStatus,
    campaign_epoch_us,
    campaign_error,
    campaign_tool_is_forbidden,
    datetime_from_epoch_us,
    decode_campaign_detail,
    require_content_hash,
    require_utc,
)
from ditto_application.processes.experiments._autonomous_campaign_support import (
    AutonomousCampaignSupport,
)


class AutonomousCampaignAuthorization(AutonomousCampaignSupport):
    """Private lifecycle base that freezes drafts before exact human approval."""

    def get_state(self, campaign_id: ExperimentId) -> CampaignCoordinatorState:
        """Return the coordinator-owned durable projection."""
        raise NotImplementedError

    def authorize(
        self,
        manifest: ResearchCampaignManifest,
        proof: CampaignAuthorizationProof,
        *,
        occurred_at: datetime,
    ) -> CampaignCoordinatorState:
        """Compatibility entry point that creates and approves one exact manifest."""
        now = require_utc(occurred_at, "occurred_at")
        self._validate_manifest(manifest)
        self._validate_authorization(
            manifest_hash=str(manifest.manifest_hash),
            expected=self._manifest_authority(manifest),
            proof=proof,
            occurred_at=now,
        )
        self.create(manifest, occurred_at=now)
        return self.approve(
            manifest.campaign_id,
            proof,
            expected_manifest_hash=str(manifest.manifest_hash),
            occurred_at=now,
        )

    def create(
        self,
        manifest: ResearchCampaignManifest,
        *,
        occurred_at: datetime,
    ) -> CampaignCoordinatorState:
        """Persist or exactly replay an immutable Campaign draft."""
        now = require_utc(occurred_at, "occurred_at")
        self._validate_manifest(manifest)
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
        return self.get_state(manifest.campaign_id)

    def approve(
        self,
        campaign_id: ExperimentId,
        proof: CampaignAuthorizationProof,
        *,
        expected_manifest_hash: str,
        occurred_at: datetime,
    ) -> CampaignCoordinatorState:
        """Approve a persisted draft without allowing manifest or budget patches."""
        now = require_utc(occurred_at, "occurred_at")
        manifest_hash = require_content_hash(
            expected_manifest_hash,
            "expected_manifest_hash",
        )
        record = self._reader.get_campaign(campaign_id)
        if record is None:
            raise campaign_error(
                "campaign was not found",
                code="CAMPAIGN_NOT_FOUND",
                reason="campaign_not_found",
            )
        if str(record.manifest_hash) != manifest_hash:
            raise campaign_error(
                "campaign manifest hash drifted before approval",
                code="CAMPAIGN_AUTHORITY_MISMATCH",
                reason="campaign_manifest_hash_drift",
            )
        view = self._view(record)
        expected = (
            str(record.manifest_hash),
            view.search_axis.value,
            tuple(view.allowed_tools),
            view.snapshot_id,
            view.candidate_limit,
            view.fold_run_limit,
            view.generation_limit,
            view.concurrent_sandbox_limit,
            view.wall_time_limit_seconds,
            view.temporary_storage_limit_bytes,
            view.model_spend_limit_usd_micros,
        )
        self._validate_authorization(
            manifest_hash=manifest_hash,
            expected=expected,
            proof=proof,
            occurred_at=now,
        )
        prior = next(
            (
                event
                for event in self._reader.list_campaign_events(campaign_id)
                if event.event_type == "campaign_authorized"
            ),
            None,
        )
        if prior is not None:
            detail = decode_campaign_detail(prior.detail_payload)
            if detail.get("verification_hash") != proof.verification_hash:
                raise campaign_error(
                    "campaign approval replay conflicts with durable authority",
                    code="CAMPAIGN_AUTHORITY_MISMATCH",
                    reason="campaign_authorization_replay_conflict",
                )
            return self.get_state(campaign_id)
        self._append_event(
            campaign_id,
            event_type="campaign_authorized",
            status=CampaignCoordinatorStatus.AUTHORIZED,
            detail={
                "proof": proof.canonical_payload(),
                "verification_hash": proof.verification_hash,
            },
            occurred_at=now,
            identity={"authorization_hash": proof.authorization_hash},
        )
        return self.get_state(campaign_id)

    @staticmethod
    def _validate_manifest(manifest: ResearchCampaignManifest) -> None:
        if type(manifest) is not ResearchCampaignManifest:
            raise campaign_error(
                "campaign manifest is invalid",
                code="CAMPAIGN_AUTHORIZATION_INVALID",
                reason="campaign_authorization_integrity_invalid",
            )
        if any(campaign_tool_is_forbidden(tool) for tool in manifest.allowed_tools):
            raise campaign_error(
                "campaign authority includes a forbidden capability",
                code="CAMPAIGN_AUTHORITY_FORBIDDEN",
                reason="campaign_authority_forbidden",
            )

    @staticmethod
    def _validate_authorization(
        *,
        manifest_hash: str,
        expected: tuple[object, ...],
        proof: CampaignAuthorizationProof,
        occurred_at: datetime,
    ) -> None:
        if (
            type(proof) is not CampaignAuthorizationProof
            or not proof.verify_integrity()
        ):
            raise campaign_error(
                "campaign authorization proof was modified",
                code="CAMPAIGN_AUTHORIZATION_INVALID",
                reason="campaign_authorization_integrity_invalid",
            )
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
        if (
            proof.campaign_manifest_hash != manifest_hash
            or observed != expected
            or occurred_at < proof.authorized_at
            or occurred_at > proof.expires_at
        ):
            raise campaign_error(
                "campaign authority does not exactly match the manifest",
                code="CAMPAIGN_AUTHORITY_MISMATCH",
                reason="campaign_authority_mismatch",
            )


__all__ = ["AutonomousCampaignAuthorization"]
