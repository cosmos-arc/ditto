"""Explicit saved snapshot export for personal local research."""

from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from ditto_analysis.errors import ExperimentIntegrityError
from ditto_analysis.research.artifact_service import ResearchArtifactService
from ditto_analysis.research.catalog_service import ResearchCatalogService
from ditto_analysis.research.specs import DatasetSnapshot
from ditto_data.catalog.field_admission import license_reasons
from ditto_data.catalog.license import DatasetLicenseReader
from ditto_data.catalog.source_snapshot import ProviderSnapshotReader

from ditto_application.exceptions import AppQueryError


class ResearchDatasetExport:
    """Validate saved identity and source licenses before publishing an export."""

    def __init__(
        self,
        *,
        research_artifact_service: ResearchArtifactService,
        research_catalog_service: ResearchCatalogService,
        snapshots: ProviderSnapshotReader,
        licenses: DatasetLicenseReader,
    ) -> None:
        self._artifacts = research_artifact_service
        self._catalog = research_catalog_service
        self._snapshots = snapshots
        self._licenses = licenses

    def export(
        self, snapshot: DatasetSnapshot, fmt: str, path: Path
    ) -> dict[str, object]:
        """Export saved bytes locally; this grants no redistribution rights."""
        if fmt not in ("csv", "sqlite"):
            raise AppQueryError(f"不支持的导出格式: {fmt}")
        saved = self._catalog.get_dataset_snapshot(snapshot.snapshot_id)
        expected = asdict(snapshot)
        expected["snapshot_start"] = expected.pop("start")
        expected["snapshot_end"] = expected.pop("end")
        if saved is None or asdict(saved) != expected:
            raise ExperimentIntegrityError(
                "research export requires the exact saved snapshot"
            )
        license_ids = self._check_licenses(snapshot)
        root = self._artifacts.artifact_root
        target = path if path.is_absolute() else root / path
        try:
            relative = target.resolve().relative_to(root).as_posix()
        except ValueError as error:
            raise AppQueryError("导出目标必须位于研究工件目录内") from error
        frame = self._artifacts.read_verified_snapshot(snapshot)
        return self._artifacts.export_dataset(
            relative,
            frame,
            fmt=fmt,
            table_name=snapshot.dataset_id.replace("-", "_"),
            provenance={
                **asdict(snapshot),
                "license_record_ids": license_ids,
                "usage": "personal_local_research_only",
            },
        )

    def _check_licenses(self, snapshot: DatasetSnapshot) -> tuple[str, ...]:
        if not snapshot.source_snapshot_ids:
            raise AppQueryError("导出缺少来源快照, 无法验证许可")
        versions: dict[str, int] = {}
        bound_sources: set[str] = set()
        for item in snapshot.resolved_inputs:
            derived_id = item.get("derived_id")
            version = item.get("version")
            sources = item.get("source_snapshot_ids")
            if (
                not isinstance(derived_id, str)
                or derived_id in versions
                or type(version) is not int
                or not isinstance(sources, list)
                or not sources
                or any(type(source) is not str or not source for source in sources)
            ):
                raise AppQueryError("每个研究输入都必须绑定完整来源快照证据")
            versions[derived_id] = version
            bound_sources.update(sources)
        if (
            not versions
            or versions != snapshot.resolved_versions
            or bound_sources != set(snapshot.source_snapshot_ids)
        ):
            raise AppQueryError("研究输入与来源快照汇总身份不一致")
        used_on = datetime.now(ZoneInfo("Asia/Shanghai")).date()
        license_ids: set[str] = set()
        for snapshot_id in snapshot.source_snapshot_ids:
            source = self._snapshots.get_snapshot(snapshot_id)
            if source is None or source.snapshot_id != source.expected_snapshot_id():
                raise AppQueryError("导出来源快照不存在或身份不完整")
            record = self._licenses.get_license(source.license_record_id)
            reasons = license_reasons(record, "formal_research", used_on)
            if (
                record is None
                or reasons
                or (
                    record.source != source.source
                    or record.dataset_id != source.dataset_id
                )
            ):
                raise AppQueryError(
                    "来源许可不允许本地研究导出",
                    details={"source_snapshot_id": snapshot_id, "reasons": reasons},
                )
            license_ids.add(record.record_id)
        return tuple(sorted(license_ids))
