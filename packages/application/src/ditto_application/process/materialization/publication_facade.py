"""
App facade for derived publication orchestration.

Provides ``DerivedPublicationFacade`` for the publication lifecycle
(shadow publish, compare, certify, promote, rollback, deprecate) and
the ``build_certification_checks`` rule builder.

Pure helper functions live in ``publication_helpers``.
"""

from __future__ import annotations

from uuid import uuid4

from ditto_data.errors import DerivedNotFoundError, DerivedValidationError
from ditto_data.ingestion.publication_safety_record_service import (
    PublicationSafetyRecordService,
)
from ditto_data.models.derived import (
    DerivedSpecRecord,
    DerivedVersionRecord,
)
from ditto_data.models.publication_safety import (
    CertificationReportRecord,
    CompatibilityManifestRecord,
    DerivedShadowSlotRecord,
)
from ditto_data.services import (
    DerivedArtifactReader,
    DerivedCatalogService,
)
from ditto_data.services.derived_shadow_slot_service import DerivedShadowSlotService
from ditto_features.materialization import DerivedRunStatus, DerivedVersionStatus
from ditto_features.publication_safety import (
    CertificationPack,
    CertificationReport,
    CertificationStage,
    ShadowDiffReport,
)
from ditto_kernel.strategy import DerivedRole, MaterializationProfile

from ditto_application.config import now_iso
from ditto_application.process.materialization.certification_rules import (
    build_certification_checks,
)
from ditto_application.process.materialization.publication_helpers import (
    build_shadow_diff_report,
    build_shadow_traces,
    certification_payload,
    hydrate_manifest,
    to_shadow_report_record,
    to_shadow_trace_record,
)

__all__ = [
    "DerivedPublicationFacade",
    "build_certification_checks",
]


class DerivedPublicationFacade:
    """Use-case facade for publication lifecycle and safety gates."""

    def __init__(
        self,
        *,
        catalog_service: DerivedCatalogService,
        artifact_reader: DerivedArtifactReader,
        publication_record_service: PublicationSafetyRecordService,
        shadow_slot_service: DerivedShadowSlotService,
    ) -> None:
        self._catalog_service = catalog_service
        self._artifact_reader = artifact_reader
        self._publication_record_service = publication_record_service
        self._shadow_slot_service = shadow_slot_service

    def shadow_publish(
        self,
        *,
        derived_id: str,
        candidate_version: int,
        baseline_version: int | None = None,
    ) -> DerivedShadowSlotRecord:
        """Register or update the active shadow candidate for one derived id."""
        self._require_version(derived_id, candidate_version)
        resolved_baseline = baseline_version or self._resolve_baseline_version(
            derived_id,
            candidate_version,
        )
        slot = DerivedShadowSlotRecord(
            derived_id=derived_id,
            candidate_version=candidate_version,
            baseline_version=resolved_baseline,
            activated_at=now_iso(),
            disabled_at=None,
        )
        self._shadow_slot_service.save_slot(slot)
        return slot

    def run_shadow_compare(
        self,
        *,
        derived_id: str,
        start: str,
        end: str,
        candidate_version: int | None = None,
        baseline_version: int | None = None,
    ) -> ShadowDiffReport:
        """Compare candidate and baseline artifacts across one audit window."""
        slot = self._resolve_slot(
            derived_id=derived_id,
            candidate_version=candidate_version,
            baseline_version=baseline_version,
        )
        if slot.baseline_version is None:
            raise DerivedNotFoundError(derived_id=derived_id)
        candidate_manifest = self._require_manifest(
            derived_id=derived_id,
            version=slot.candidate_version,
        )
        baseline_manifest = self._require_manifest(
            derived_id=derived_id,
            version=slot.baseline_version,
        )
        candidate_frame = self._artifact_reader.read_frame(
            derived_id=derived_id,
            version=slot.candidate_version,
            start=start,
            end=end,
        )
        baseline_frame = self._artifact_reader.read_frame(
            derived_id=derived_id,
            version=slot.baseline_version,
            start=start,
            end=end,
        )
        report = build_shadow_diff_report(
            derived_id=derived_id,
            candidate_version=slot.candidate_version,
            baseline_version=slot.baseline_version,
            candidate_frame=candidate_frame,
            baseline_frame=baseline_frame,
            candidate_manifest_hash=candidate_manifest.manifest_hash,
            baseline_manifest_hash=baseline_manifest.manifest_hash,
        )
        traces = build_shadow_traces(
            report=report,
            candidate_frame=candidate_frame,
            baseline_frame=baseline_frame,
        )
        self._publication_record_service.save_shadow_report(
            to_shadow_report_record(report),
            tuple(to_shadow_trace_record(derived_id, trace) for trace in traces),
        )
        return report

    def certify(
        self,
        *,
        derived_id: str,
        version: int,
        stage: str | CertificationStage,
    ) -> CertificationReport:
        """Run one certification gate for a candidate version."""
        if not isinstance(stage, CertificationStage):
            stage = CertificationStage(stage)
        spec_record = self._require_spec(derived_id, version)
        manifest_record = self._require_manifest(derived_id=derived_id, version=version)
        manifest = hydrate_manifest(manifest_record)
        minimal_dq_record = (
            self._publication_record_service.get_latest_minimal_dq_summary(
                derived_id,
                version,
            )
        )
        slot = self._shadow_slot_service.get_active_slot(derived_id)
        shadow_report_record = None
        if (
            slot is not None
            and slot.candidate_version == version
            and slot.baseline_version is not None
        ):
            shadow_report_record = (
                self._publication_record_service.get_latest_shadow_report(
                    derived_id,
                    slot.candidate_version,
                    slot.baseline_version,
                )
            )
        role = DerivedRole(spec_record.role)
        materialization_profile = MaterializationProfile(
            spec_record.materialization_profile
        )
        checks = build_certification_checks(
            stage=stage,
            role=role,
            materialization_profile=materialization_profile,
            manifest=manifest,
            minimal_dq_record=minimal_dq_record,
            shadow_report_record=shadow_report_record,
        )
        pack = CertificationPack(
            pack_id=(
                f"pack-{spec_record.role.lower()}"
                + f"-{spec_record.materialization_profile.lower()}"
                + f"-{stage.value}"
            ),
            role=role,
            materialization_profile=materialization_profile,
            stage=stage,
            check_names=tuple(check.name for check in checks),
        )
        report = CertificationReport(
            report_id=f"cert-{uuid4().hex[:12]}",
            pack=pack,
            derived_id=derived_id,
            version=version,
            checks=checks,
            manifest_hash=manifest_record.manifest_hash,
            shadow_diff_report_id=None
            if shadow_report_record is None
            else shadow_report_record.report_id,
            created_at=now_iso(),
        )
        self._publication_record_service.save_certification_report(
            CertificationReportRecord(
                report_id=report.report_id,
                derived_id=derived_id,
                version=version,
                stage=stage.value,
                pack_id=pack.pack_id,
                manifest_hash=manifest_record.manifest_hash,
                payload=certification_payload(report),
                created_at=report.created_at,
            )
        )
        return report

    def promote(
        self,
        *,
        derived_id: str,
        candidate_version: int,
    ) -> DerivedVersionRecord:
        """Promote one candidate version to the online primary slot."""
        self._require_promotable_candidate(
            derived_id=derived_id,
            candidate_version=candidate_version,
        )
        promoted_at = now_iso()
        self._move_primary_pointer(
            derived_id=derived_id,
            target_version=candidate_version,
            target_status=DerivedVersionStatus.PUBLISHED,
            updated_at=promoted_at,
        )
        self._shadow_slot_service.disable_slot(derived_id, promoted_at)
        promoted = self._catalog_service.get_version(derived_id, candidate_version)
        if promoted is None:
            raise DerivedNotFoundError(derived_id=derived_id, version=candidate_version)
        return promoted

    def rollback(
        self,
        *,
        derived_id: str,
        target_version: int,
    ) -> DerivedVersionRecord:
        """Move the primary pointer back to one already-published version."""
        target = self._require_version(derived_id, target_version)
        if target.status != DerivedVersionStatus.PUBLISHED:
            raise DerivedValidationError(
                "rollback target must already be published: "
                + f"id={derived_id} v={target_version}",
                derived_id=derived_id,
            )
        rolled_back_at = now_iso()
        self._move_primary_pointer(
            derived_id=derived_id,
            target_version=target_version,
            target_status=target.status,
            updated_at=rolled_back_at,
        )
        rolled_back = self._catalog_service.get_version(derived_id, target_version)
        if rolled_back is None:
            raise DerivedNotFoundError(derived_id=derived_id, version=target_version)
        return rolled_back

    def deprecate(
        self,
        *,
        derived_id: str,
        version: int,
    ) -> DerivedVersionRecord:
        """Mark one published non-primary version as deprecated and offline."""
        version_record = self._require_version(derived_id, version)
        if version_record.status != DerivedVersionStatus.PUBLISHED:
            raise DerivedValidationError(
                "only published versions can be deprecated: "
                + f"id={derived_id} v={version}",
                derived_id=derived_id,
            )
        if version_record.is_primary:
            raise DerivedValidationError(
                "primary must be rolled back before deprecate: "
                + f"id={derived_id} v={version}",
            )
        deprecated_at = now_iso()
        self._catalog_service.save_version(
            DerivedVersionRecord(
                derived_id=version_record.derived_id,
                version=version_record.version,
                status=DerivedVersionStatus.DEPRECATED,
                engine_version=version_record.engine_version,
                is_online=False,
                is_primary=False,
                created_at=version_record.created_at,
                updated_at=deprecated_at,
            )
        )
        deprecated = self._catalog_service.get_version(derived_id, version)
        if deprecated is None:
            raise DerivedNotFoundError(derived_id=derived_id, version=version)
        return deprecated

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _resolve_slot(
        self,
        *,
        derived_id: str,
        candidate_version: int | None,
        baseline_version: int | None,
    ) -> DerivedShadowSlotRecord:
        if candidate_version is None and baseline_version is None:
            slot = self._shadow_slot_service.get_active_slot(derived_id)
            if slot is None:
                raise DerivedNotFoundError(derived_id=derived_id)
            return slot
        if candidate_version is None:
            raise DerivedValidationError(
                "candidate_version is required when baseline_version is set"
            )
        self._require_version(derived_id, candidate_version)
        if baseline_version is not None:
            self._require_version(derived_id, baseline_version)
        return DerivedShadowSlotRecord(
            derived_id=derived_id,
            candidate_version=candidate_version,
            baseline_version=baseline_version,
            activated_at=now_iso(),
            disabled_at=None,
        )

    def _resolve_baseline_version(
        self,
        derived_id: str,
        candidate_version: int,
    ) -> int | None:
        primary_online = next(
            (
                record.version
                for record in self._catalog_service.list_versions(derived_id)
                if (
                    record.is_primary
                    and record.is_online
                    and record.version != candidate_version
                )
            ),
            None,
        )
        if primary_online is not None:
            return primary_online
        return next(
            (
                record.version
                for record in self._catalog_service.list_versions(derived_id)
                if record.is_primary and record.version != candidate_version
            ),
            None,
        )

    def _require_promotable_candidate(
        self,
        *,
        derived_id: str,
        candidate_version: int,
    ) -> DerivedShadowSlotRecord:
        self._require_version(derived_id, candidate_version)
        latest_run = self._catalog_service.get_latest_run(derived_id, candidate_version)
        if latest_run is None or latest_run.status != DerivedRunStatus.SUCCESS:
            raise DerivedValidationError(
                "candidate version is not materialized: "
                + f"id={derived_id} v={candidate_version}",
                derived_id=derived_id,
            )
        manifest_record = self._require_manifest(
            derived_id=derived_id,
            version=candidate_version,
        )
        manifest = hydrate_manifest(manifest_record)
        if not manifest.is_complete():
            raise DerivedValidationError(
                "candidate manifest is incomplete: "
                + f"id={derived_id} v={candidate_version}",
                derived_id=derived_id,
            )
        slot = self._shadow_slot_service.get_active_slot(derived_id)
        if slot is None or slot.candidate_version != candidate_version:
            raise DerivedValidationError(
                "active shadow slot missing: "
                + f"id={derived_id} v={candidate_version}",
                derived_id=derived_id,
            )
        if slot.baseline_version is None:
            raise DerivedValidationError(
                f"shadow baseline missing for {derived_id}",
                derived_id=derived_id,
            )
        shadow_report = self._publication_record_service.get_latest_shadow_report(
            derived_id,
            candidate_version,
            slot.baseline_version,
        )
        if shadow_report is None or shadow_report.error_count > 0:
            raise DerivedValidationError(
                "shadow compare not publishable: "
                + f"id={derived_id} v={candidate_version}",
                derived_id=derived_id,
            )
        certification = (
            self._publication_record_service.get_latest_certification_report(
                derived_id,
                candidate_version,
                CertificationStage.PUBLISH_READY.value,
            )
        )
        if certification is None or certification.payload.get("passed") is not True:
            raise DerivedValidationError(
                "publish_ready gate has not passed: "
                + f"id={derived_id} v={candidate_version}",
                derived_id=derived_id,
            )
        return slot

    def _move_primary_pointer(
        self,
        *,
        derived_id: str,
        target_version: int,
        target_status: str,
        updated_at: str,
    ) -> None:
        for version_record in self._catalog_service.list_versions(derived_id):
            if version_record.version == target_version:
                self._catalog_service.save_version(
                    DerivedVersionRecord(
                        derived_id=version_record.derived_id,
                        version=version_record.version,
                        status=target_status,
                        engine_version=version_record.engine_version,
                        is_online=True,
                        is_primary=True,
                        created_at=version_record.created_at,
                        updated_at=updated_at,
                    )
                )
                continue
            if version_record.is_primary:
                self._catalog_service.save_version(
                    DerivedVersionRecord(
                        derived_id=version_record.derived_id,
                        version=version_record.version,
                        status=version_record.status,
                        engine_version=version_record.engine_version,
                        is_online=version_record.is_online,
                        is_primary=False,
                        created_at=version_record.created_at,
                        updated_at=updated_at,
                    )
                )

    def _require_spec(
        self,
        derived_id: str,
        version: int,
    ) -> DerivedSpecRecord:
        spec_record = self._catalog_service.get_spec(derived_id, version)
        if spec_record is None:
            raise DerivedNotFoundError(derived_id=derived_id, version=version)
        return spec_record

    def _require_version(self, derived_id: str, version: int) -> DerivedVersionRecord:
        version_record = self._catalog_service.get_version(derived_id, version)
        if version_record is None:
            raise DerivedNotFoundError(derived_id=derived_id, version=version)
        return version_record

    def _require_manifest(
        self,
        *,
        derived_id: str,
        version: int,
    ) -> CompatibilityManifestRecord:
        manifest_record = self._publication_record_service.get_manifest(
            derived_id,
            version,
        )
        if manifest_record is None:
            raise DerivedNotFoundError(derived_id=derived_id, version=version)
        return manifest_record
