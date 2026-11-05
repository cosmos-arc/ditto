"""#418 空跑清理语义：不产 artifact 的运行不落目录."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl
import pytest
from ditto_features.models.derived import DerivedSpecRecord
from ditto_features.storage.derived_artifact_writer import DerivedArtifactWriter


def _spec_record() -> DerivedSpecRecord:
    return DerivedSpecRecord(
        derived_id="factor.momentum_1m",
        version=1,
        role="factor",
        materialization_profile="SERIES",
        spec_hash="hash-1",
        spec_json={"id": "factor.momentum_1m"},
        created_at="2026-10-04T10:00:00+08:00",
    )


def _frame(*, rows: int) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "instrument_id": [1] * rows,
            "trade_date": [date(2026, 9, 30)] * rows,
            "value": [0.5] * rows,
        }
    )


def _version_root(artifact_root: Path) -> Path:
    return (
        artifact_root / "derived" / "artifacts" / "series" / "factor.momentum_1m" / "v1"
    )


def test_empty_frame_durable_write_creates_no_directory(tmp_path: Path) -> None:
    writer = DerivedArtifactWriter(tmp_path)
    partitions = writer.write_durable_partitions(
        spec=_spec_record(),
        time_key="trade_date",
        run_id="drv-empty",
        frame=_frame(rows=0),
        request_start="2026-09-30",
        request_end="2026-09-30",
    )
    assert partitions == ()
    assert not _version_root(tmp_path).exists()


def test_empty_frame_incremental_write_creates_no_directory(tmp_path: Path) -> None:
    writer = DerivedArtifactWriter(tmp_path)
    partitions = writer.write_incremental_partition(
        spec=_spec_record(),
        time_key="trade_date",
        run_id="drv-empty",
        frame=_frame(rows=0),
        source_snapshot_id=None,
    )
    assert partitions == ()
    assert not _version_root(tmp_path).exists()


def test_phase1_failure_cleans_temps_and_created_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writer = DerivedArtifactWriter(tmp_path)

    def _explode(*args: object, **kwargs: object) -> None:
        raise OSError("simulated parquet write failure")

    monkeypatch.setattr(pl.DataFrame, "write_parquet", _explode)
    with pytest.raises(OSError, match="simulated parquet write failure"):
        writer.write_durable_partitions(
            spec=_spec_record(),
            time_key="trade_date",
            run_id="drv-crash",
            frame=_frame(rows=2),
            request_start="2026-09-30",
            request_end="2026-09-30",
        )
    version_root = _version_root(tmp_path)
    assert not version_root.exists()


def test_phase1_failure_keeps_existing_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """既有产物目录里的内容不因失败回滚而被误删."""
    writer = DerivedArtifactWriter(tmp_path)
    published = writer.write_durable_partitions(
        spec=_spec_record(),
        time_key="trade_date",
        run_id="drv-ok",
        frame=_frame(rows=2),
        request_start="2026-09-30",
        request_end="2026-09-30",
    )
    assert published != ()

    def _explode(*args: object, **kwargs: object) -> None:
        raise OSError("simulated parquet write failure")

    monkeypatch.setattr(pl.DataFrame, "write_parquet", _explode)
    with pytest.raises(OSError, match="simulated parquet write failure"):
        writer.write_durable_partitions(
            spec=_spec_record(),
            time_key="trade_date",
            run_id="drv-crash",
            frame=_frame(rows=1),
            published_history=_frame(rows=2),
            request_start="2026-09-30",
            request_end="2026-09-30",
        )
    version_root = _version_root(tmp_path)
    assert (version_root / "2026.parquet").exists()


def test_killed_writer_tmp_residue_is_inert(tmp_path: Path) -> None:
    """#694：被杀写入者的唯一名 tmp 残留不进 *.parquet 读取 glob."""
    writer = DerivedArtifactWriter(tmp_path)
    partitions = writer.write_durable_partitions(
        spec=_spec_record(),
        time_key="trade_date",
        run_id="drv-ok",
        frame=_frame(rows=2),
        request_start="2026-09-30",
        request_end="2026-09-30",
    )
    assert partitions != ()
    version_root = _version_root(tmp_path)
    # 模拟另一写入者被杀后的半成品残留（写入者唯一名、.tmp 结尾）。
    (version_root / "2026.parquet.12345-deadbeef.tmp").write_bytes(b"half")
    visible = sorted(p.name for p in version_root.glob("*.parquet"))
    assert visible == ["2026.parquet"]
    # 旧共享名（2026.tmp.parquet）才会污染 glob——新命名不再出现该形态。
    assert not any(".tmp.parquet" in name for name in visible)


def test_overlapping_runs_never_tear_each_other(tmp_path: Path) -> None:
    """#694：重叠物化双线程同写尚不存在的分区，各自 run 的留存字节逐位等于自己的帧."""
    import threading

    writer = DerivedArtifactWriter(tmp_path)
    errors: list[Exception] = []
    start_gate = threading.Event()

    def _worker(run_id: str, value: float) -> None:
        frame = pl.DataFrame(
            {
                "instrument_id": [1, 1],
                "trade_date": [date(2026, 9, 29), date(2026, 9, 30)],
                "value": [value, value],
            }
        )
        try:
            start_gate.wait()
            writer.write_durable_partitions(
                spec=_spec_record(),
                time_key="trade_date",
                run_id=run_id,
                frame=frame,
                request_start="2026-09-29",
                request_end="2026-09-30",
            )
            retained = _version_root(tmp_path) / "_runs" / run_id / "2026.parquet"
            assert pl.read_parquet(retained)["value"].to_list() == [value, value]
        except Exception as exc:
            errors.append(exc)

    left = threading.Thread(target=_worker, args=("drv-left", 0.25))
    right = threading.Thread(target=_worker, args=("drv-right", 0.75))
    left.start()
    right.start()
    start_gate.set()
    left.join(timeout=60)
    right.join(timeout=60)
    assert not left.is_alive()
    assert not right.is_alive()
    assert errors == []
    # 当前分区是某一方的完整帧（两值一致），绝不是撕裂混合。
    current = pl.read_parquet(_version_root(tmp_path) / "2026.parquet")
    values = current["value"].unique().to_list()
    assert len(values) == 1
    assert values[0] in (0.25, 0.75)
