"""Explicit saved snapshot export for personal local research."""

from dataclasses import asdict
from pathlib import Path

from ditto_analysis.errors import ExperimentIntegrityError
from ditto_analysis.research.artifact_service import ResearchArtifactService
from ditto_analysis.research.catalog_service import ResearchCatalogService
from ditto_analysis.research.specs import DatasetSnapshot
from ditto_data.catalog.source_snapshot import ProviderSnapshotReader

from ditto_application.exceptions import AppQueryError

__all__ = ["ResearchDatasetExport"]

# Minimal usage constraints per provider source, replacing the removed
# license-approval workflow. The constraint travels in every export receipt;
# unknown sources fail closed — dropping the workflow must not silently
# broaden redistribution rights the operator never declared.
_SOURCE_USAGE_CONSTRAINTS: dict[str, str] = {
    "tushare": "personal_local_research_only",
    "fuyao": "personal_local_research_only",
    "fred": "personal_local_research_only",
}


class ResearchDatasetExport:
    """Validate saved identity and input completeness before exporting."""

    def __init__(
        self,
        *,
        research_artifact_service: ResearchArtifactService,
        research_catalog_service: ResearchCatalogService,
        snapshots: ProviderSnapshotReader,
    ) -> None:
        self._artifacts = research_artifact_service
        self._catalog = research_catalog_service
        self._snapshots = snapshots

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
        usage_constraints = self._check_inputs(snapshot)
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
                "usage": "personal_local_research_only",
                "source_usage": usage_constraints,
            },
        )

    def _check_inputs(self, snapshot: DatasetSnapshot) -> dict[str, str]:
        """Verify input versions, universe bindings and the source closure."""
        if not snapshot.source_snapshot_ids:
            raise AppQueryError("导出缺少来源快照, 无法验证完整性")
        versions: dict[str, int] = {}
        bound_sources: set[str] = set()
        universe_inputs = 0
        for item in snapshot.resolved_inputs:
            if item.get("input_kind") == "universe":
                sources = item.get("source_snapshot_ids")
                universe_inputs += 1
                if (
                    universe_inputs != 1
                    or not item.get("universe_id")
                    or not isinstance(sources, list)
                    or not sources
                    or any(type(source) is not str or not source for source in sources)
                ):
                    raise AppQueryError("历史证券池来源绑定不完整")
                bound_sources.update(sources)
                continue
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
        usage_constraints: dict[str, str] = {}
        for snapshot_id in snapshot.source_snapshot_ids:
            source = self._snapshots.get_snapshot(snapshot_id)
            if source is None or source.snapshot_id != source.expected_snapshot_id():
                raise AppQueryError("导出来源快照不存在或身份不完整")
            constraint = _SOURCE_USAGE_CONSTRAINTS.get(source.source)
            if constraint is None:
                raise AppQueryError(
                    "来源使用约束未声明, 拒绝导出",
                    details={
                        "source_snapshot_id": snapshot_id,
                        "source": source.source,
                    },
                )
            usage_constraints[snapshot_id] = constraint
        return usage_constraints
