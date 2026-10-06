"""#418 读侧诚实门禁：完成才可读＋身份漂移拒绝＋部分写入不可读."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from hashlib import sha256
from pathlib import Path

import polars as pl
import pytest
from ditto_features.errors import DerivedIntegrityError, DerivedVersionError
from ditto_features.models.derived import (
    DerivedCheckpointRecord,
    DerivedCheckpointStatus,
    DerivedPartitionRecord,
    DerivedRunRecord,
    DerivedSpecRecord,
    DerivedStateRecord,
    DerivedVersionRecord,
)
from ditto_features.services import DerivedArtifactReader


class _FakeCatalog:
    """协议级内存目录，只承载 reader 门禁所需事实."""

    def __init__(self, *, version_status: str = "published") -> None:
        spec = DerivedSpecRecord(
            derived_id="factor.momentum_1m",
            version=1,
            role="factor",
            materialization_profile="SERIES",
            spec_hash="hash-1",
            spec_json={"id": "factor.momentum_1m"},
            created_at="2026-10-04T10:00:00+08:00",
        )
        version = DerivedVersionRecord(
            derived_id=spec.derived_id,
            version=1,
            status=version_status,
            engine_version="unified-derived-v1",
            is_online=True,
            is_primary=True,
            created_at="2026-10-04T10:00:00+08:00",
            updated_at=None,
        )
        self._specs = {(spec.derived_id, spec.version): spec}
        self._versions = {(version.derived_id, version.version): version}
        self._states = {
            spec.derived_id: DerivedStateRecord(
                derived_id=spec.derived_id,
                active_version=1,
                coverage_start="2026-09-01",
                coverage_end="2026-09-30",
                watermark="2026-09-30",
                latest_run_id="drv-1",
                latest_run_status="SUCCESS",
                total_rows=2,
                updated_at="2026-10-04T10:00:00+08:00",
            )
        }
        self._checkpoints: dict[tuple[str, int, str], DerivedCheckpointRecord] = {}

    def get_run(
        self, derived_id: str, version: int, run_id: str
    ) -> DerivedRunRecord | None:
        # reader 门禁测试不触达 run 维度，误用即测试假设失效。
        raise AssertionError("reader gate tests must not query catalog runs")

    def list_partitions(
        self, derived_id: str, version: int, run_id: str
    ) -> list[DerivedPartitionRecord]:
        raise AssertionError("reader gate tests must not list catalog partitions")

    def get_spec(self, derived_id: str, version: int) -> DerivedSpecRecord | None:
        return self._specs.get((derived_id, version))

    def get_version(self, derived_id: str, version: int) -> DerivedVersionRecord | None:
        return self._versions.get((derived_id, version))

    def get_state(self, derived_id: str) -> DerivedStateRecord | None:
        return self._states.get(derived_id)

    def list_versions(self, derived_id: str) -> tuple[DerivedVersionRecord, ...]:
        return tuple(
            record
            for (record_derived_id, _), record in self._versions.items()
            if record_derived_id == derived_id
        )

    def list_checkpoints(
        self, derived_id: str, version: int
    ) -> tuple[DerivedCheckpointRecord, ...]:
        return tuple(
            record
            for (
                record_derived_id,
                record_version,
                _,
            ), record in self._checkpoints.items()
            if record_derived_id == derived_id and record_version == version
        )

    def put_checkpoint(self, record: DerivedCheckpointRecord) -> None:
        self._checkpoints[(record.derived_id, record.version, record.partition_key)] = (
            record
        )


def _write_partition(artifact_root: Path) -> Path:
    version_root = (
        artifact_root / "derived" / "artifacts" / "series" / "factor.momentum_1m" / "v1"
    )
    version_root.mkdir(parents=True, exist_ok=True)
    path = version_root / "2026.parquet"
    pl.DataFrame(
        {
            "instrument_id": [1, 2],
            "trade_date": [date(2026, 9, 29), date(2026, 9, 30)],
            "value": [0.1, 0.2],
        }
    ).write_parquet(path)
    return path


def _complete_checkpoint(path: Path) -> DerivedCheckpointRecord:
    return DerivedCheckpointRecord(
        derived_id="factor.momentum_1m",
        version=1,
        partition_key="2026",
        status=DerivedCheckpointStatus.COMPLETE.value,
        rows_written=2,
        checksum=sha256(path.read_bytes()).hexdigest(),
        error_message=None,
        started_at="2026-10-04T10:00:00+08:00",
        completed_at="2026-10-04T10:00:01+08:00",
    )


def test_complete_published_partition_reads(tmp_path: Path) -> None:
    catalog = _FakeCatalog()
    path = _write_partition(tmp_path)
    catalog.put_checkpoint(_complete_checkpoint(path))
    reader = DerivedArtifactReader(catalog_service=catalog, artifact_root=tmp_path)
    frame = reader.read_frame(
        derived_id="factor.momentum_1m",
        version=1,
        start="2026-09-01",
        end="2026-09-30",
    )
    assert frame.height == 2


def test_unpublished_version_refused(tmp_path: Path) -> None:
    catalog = _FakeCatalog(version_status="draft")
    path = _write_partition(tmp_path)
    catalog.put_checkpoint(_complete_checkpoint(path))
    reader = DerivedArtifactReader(catalog_service=catalog, artifact_root=tmp_path)
    with pytest.raises(DerivedVersionError, match="not published"):
        reader.read_frame(
            derived_id="factor.momentum_1m",
            version=1,
            start="2026-09-01",
            end="2026-09-30",
        )


def test_partial_write_payload_committed_refused(tmp_path: Path) -> None:
    """部分写入（rename 后、COMPLETE 前）不可读."""
    catalog = _FakeCatalog()
    path = _write_partition(tmp_path)
    checkpoint = replace(
        _complete_checkpoint(path),
        status=DerivedCheckpointStatus.PAYLOAD_COMMITTED.value,
        completed_at=None,
    )
    catalog.put_checkpoint(checkpoint)
    reader = DerivedArtifactReader(catalog_service=catalog, artifact_root=tmp_path)
    with pytest.raises(DerivedIntegrityError, match="not COMPLETE"):
        reader.read_frame(
            derived_id="factor.momentum_1m",
            version=1,
            start="2026-09-01",
            end="2026-09-30",
        )


def test_missing_checkpoint_row_refused(tmp_path: Path) -> None:
    catalog = _FakeCatalog()
    _write_partition(tmp_path)
    reader = DerivedArtifactReader(catalog_service=catalog, artifact_root=tmp_path)
    with pytest.raises(DerivedIntegrityError, match="not COMPLETE"):
        reader.read_frame(
            derived_id="factor.momentum_1m",
            version=1,
            start="2026-09-01",
            end="2026-09-30",
        )


def test_checksum_drift_refused(tmp_path: Path) -> None:
    """身份漂移：同 artifact id 的文件内容与目录 checksum 不一致."""
    catalog = _FakeCatalog()
    path = _write_partition(tmp_path)
    catalog.put_checkpoint(_complete_checkpoint(path))
    tampered = pl.read_parquet(path).with_columns(pl.col("value") * 10.0)
    tampered.write_parquet(path)
    reader = DerivedArtifactReader(catalog_service=catalog, artifact_root=tmp_path)
    with pytest.raises(DerivedIntegrityError, match="checksum drift"):
        reader.read_frame(
            derived_id="factor.momentum_1m",
            version=1,
            start="2026-09-01",
            end="2026-09-30",
        )


def test_inflight_tmp_file_refused(tmp_path: Path) -> None:
    """无窗口 glob 命中写入中的 tmp 文件时 fail closed."""
    catalog = _FakeCatalog()
    path = _write_partition(tmp_path)
    catalog.put_checkpoint(_complete_checkpoint(path))
    pl.DataFrame(
        {
            "instrument_id": [1],
            "trade_date": [date(2026, 9, 30)],
            "value": [0.3],
        }
    ).write_parquet(path.parent / "2026.tmp.parquet")
    reader = DerivedArtifactReader(catalog_service=catalog, artifact_root=tmp_path)
    with pytest.raises(DerivedIntegrityError, match="not COMPLETE"):
        reader.read_frame(derived_id="factor.momentum_1m", version=1)
