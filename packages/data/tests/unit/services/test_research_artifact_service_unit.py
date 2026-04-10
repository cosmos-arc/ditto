"""Unit tests for ResearchArtifactService."""

from __future__ import annotations

import os
from pathlib import Path

import orjson
import polars as pl
import pytest
from ditto_data.services.research_artifact_service import ResearchArtifactService
from polars.testing import assert_frame_equal


class TestReadParquet:
    def test_reads_parquet_file(self, tmp_path: Path) -> None:
        frame = pl.DataFrame({"a": [1, 2], "b": [3.0, 4.0]})
        frame.write_parquet(tmp_path / "data.parquet")

        service = ResearchArtifactService(artifact_root=tmp_path)
        result = service.read_parquet("data.parquet")

        assert_frame_equal(result, frame)

    def test_raises_for_missing_file(self, tmp_path: Path) -> None:
        service = ResearchArtifactService(artifact_root=tmp_path)
        with pytest.raises(FileNotFoundError, match=r"nonexistent\.parquet"):
            service.read_parquet("nonexistent.parquet")


class TestWriteParquet:
    def test_writes_parquet_and_creates_parent_dirs(self, tmp_path: Path) -> None:
        frame = pl.DataFrame({"x": [1, 2, 3]})

        service = ResearchArtifactService(artifact_root=tmp_path)
        service.write_parquet("deep/nested/dir/data.parquet", frame)

        written = tmp_path / "deep" / "nested" / "dir" / "data.parquet"
        assert written.exists()
        result = pl.read_parquet(written)
        assert_frame_equal(result, frame)

    def test_overwrites_existing_file(self, tmp_path: Path) -> None:
        pl.DataFrame({"x": [1]}).write_parquet(tmp_path / "data.parquet")

        updated = pl.DataFrame({"x": [2, 3]})
        service = ResearchArtifactService(artifact_root=tmp_path)
        service.write_parquet("data.parquet", updated)

        result = pl.read_parquet(tmp_path / "data.parquet")
        assert_frame_equal(result, updated)


class TestReadJson:
    def test_reads_json_file(self, tmp_path: Path) -> None:
        data = {"key": "value", "num": 42}
        (tmp_path / "meta.json").write_bytes(orjson.dumps(data))

        service = ResearchArtifactService(artifact_root=tmp_path)
        result = service.read_json("meta.json")

        assert result == data

    def test_raises_for_missing_file(self, tmp_path: Path) -> None:
        service = ResearchArtifactService(artifact_root=tmp_path)
        with pytest.raises(FileNotFoundError, match=r"nonexistent\.json"):
            service.read_json("nonexistent.json")

    def test_raises_for_non_object_json(self, tmp_path: Path) -> None:
        (tmp_path / "list.json").write_bytes(orjson.dumps([1, 2, 3]))

        service = ResearchArtifactService(artifact_root=tmp_path)
        with pytest.raises(ValueError, match="expected JSON object"):
            service.read_json("list.json")


class TestWriteJson:
    def test_writes_json_and_creates_parent_dirs(self, tmp_path: Path) -> None:
        data = {"key": "value", "num": 42}

        service = ResearchArtifactService(artifact_root=tmp_path)
        service.write_json("deep/dir/meta.json", data)

        path = tmp_path / "deep" / "dir" / "meta.json"
        assert path.exists()
        loaded = orjson.loads(path.read_bytes())
        assert loaded == data

    def test_writes_sorted_keys(self, tmp_path: Path) -> None:
        service = ResearchArtifactService(artifact_root=tmp_path)
        service.write_json("meta.json", {"z": 1, "a": 2})

        loaded = orjson.loads((tmp_path / "meta.json").read_bytes())
        keys = list(loaded.keys())
        assert keys == ["a", "z"]


class TestExportDataset:
    """Tests for multi-format dataset export."""

    def test_export_parquet_default(self, tmp_path: Path) -> None:
        """Default format is parquet."""
        frame = pl.DataFrame({"a": [1, 2], "b": [3.0, 4.0]})

        service = ResearchArtifactService(artifact_root=tmp_path)
        service.export_dataset("out/data.parquet", frame)

        result = pl.read_parquet(tmp_path / "out" / "data.parquet")
        assert_frame_equal(result, frame)

    def test_export_csv(self, tmp_path: Path) -> None:
        """Export to CSV format."""
        frame = pl.DataFrame({"a": [1, 2], "b": [3.0, 4.0]})

        service = ResearchArtifactService(artifact_root=tmp_path)
        service.export_dataset("out/data.csv", frame, fmt="csv")

        result = pl.read_csv(tmp_path / "out" / "data.csv")
        assert_frame_equal(result, frame)

    def test_export_feather(self, tmp_path: Path) -> None:
        """Export to Feather (IPC) format."""
        frame = pl.DataFrame({"a": [1, 2], "b": [3.0, 4.0]})

        service = ResearchArtifactService(artifact_root=tmp_path)
        service.export_dataset("out/data.feather", frame, fmt="feather")

        result = pl.read_ipc(tmp_path / "out" / "data.feather")
        assert_frame_equal(result, frame)

    def test_export_creates_parent_directories(self, tmp_path: Path) -> None:
        """Parent directories are created automatically."""
        frame = pl.DataFrame({"x": [10]})

        service = ResearchArtifactService(artifact_root=tmp_path)
        service.export_dataset("deep/nested/data.csv", frame, fmt="csv")

        path = tmp_path / "deep" / "nested" / "data.csv"
        assert path.exists()

    def test_export_raises_for_unsupported_format(self, tmp_path: Path) -> None:
        """Unsupported format raises ValueError."""
        frame = pl.DataFrame({"x": [1]})

        service = ResearchArtifactService(artifact_root=tmp_path)
        with pytest.raises(ValueError, match="unsupported format"):
            service.export_dataset("data.xlsx", frame, fmt="xlsx")

    def test_export_overwrites_existing_file(self, tmp_path: Path) -> None:
        """Existing file is overwritten."""
        frame1 = pl.DataFrame({"x": [1]})
        frame1.write_csv(tmp_path / "data.csv")

        frame2 = pl.DataFrame({"x": [2, 3]})

        service = ResearchArtifactService(artifact_root=tmp_path)
        service.export_dataset("data.csv", frame2, fmt="csv")

        result = pl.read_csv(tmp_path / "data.csv")
        assert_frame_equal(result, frame2)


class TestResolveArtifactRelativePath:
    def test_finds_matching_artifact(self, tmp_path: Path) -> None:
        version_root = (
            tmp_path / "derived" / "artifacts" / "series" / "factor.alpha" / "v2"
        )
        version_root.mkdir(parents=True)

        service = ResearchArtifactService(artifact_root=tmp_path)
        result = service.resolve_artifact_relative_path("factor.alpha", 2)

        assert result == "derived/artifacts/series/factor.alpha/v2"

    def test_returns_none_when_not_found(self, tmp_path: Path) -> None:
        service = ResearchArtifactService(artifact_root=tmp_path)
        result = service.resolve_artifact_relative_path("nonexistent", 1)

        assert result is None

    def test_returns_series_profile_when_multiple_profiles_exist(
        self,
        tmp_path: Path,
    ) -> None:
        """Should return all matching paths sorted, first one wins."""
        for profile in ("offline", "series"):
            (tmp_path / "derived" / "artifacts" / profile / "f.x" / "v1").mkdir(
                parents=True,
            )

        service = ResearchArtifactService(artifact_root=tmp_path)
        result = service.resolve_artifact_relative_path("f.x", 1)

        assert result is not None
        assert result.startswith("derived/artifacts/")


class TestReadSourceSnapshotIds:
    def test_reads_ids_from_metadata(self, tmp_path: Path) -> None:
        runs_root = (
            tmp_path
            / "derived"
            / "artifacts"
            / "series"
            / "f.x"
            / "v1"
            / "_runs"
            / "run-1"
        )
        runs_root.mkdir(parents=True)
        metadata = {
            "input_snapshots": ["market:20260310-001", "market:20260311-001"],
        }
        (runs_root / "artifact_metadata.json").write_bytes(orjson.dumps(metadata))

        service = ResearchArtifactService(artifact_root=tmp_path)
        result = service.read_source_snapshot_ids(
            "derived/artifacts/series/f.x/v1",
        )

        assert result == ("market:20260310-001", "market:20260311-001")

    def test_returns_empty_when_no_runs_dir(self, tmp_path: Path) -> None:
        version_root = tmp_path / "derived" / "artifacts" / "series" / "f.x" / "v1"
        version_root.mkdir(parents=True)

        service = ResearchArtifactService(artifact_root=tmp_path)
        result = service.read_source_snapshot_ids(
            "derived/artifacts/series/f.x/v1",
        )

        assert result == ()

    def test_returns_empty_when_no_metadata_files(self, tmp_path: Path) -> None:
        runs_root = (
            tmp_path / "derived" / "artifacts" / "series" / "f.x" / "v1" / "_runs"
        )
        runs_root.mkdir(parents=True)

        service = ResearchArtifactService(artifact_root=tmp_path)
        result = service.read_source_snapshot_ids(
            "derived/artifacts/series/f.x/v1",
        )

        assert result == ()

    def test_picks_latest_metadata_by_mtime(self, tmp_path: Path) -> None:
        run1 = (
            tmp_path
            / "derived"
            / "artifacts"
            / "series"
            / "f.x"
            / "v1"
            / "_runs"
            / "run-1"
        )
        run2 = (
            tmp_path
            / "derived"
            / "artifacts"
            / "series"
            / "f.x"
            / "v1"
            / "_runs"
            / "run-2"
        )
        run1.mkdir(parents=True)
        run2.mkdir(parents=True)

        run1_meta = run1 / "artifact_metadata.json"
        run2_meta = run2 / "artifact_metadata.json"
        run1_meta.write_bytes(orjson.dumps({"input_snapshots": ["market:001"]}))
        run2_meta.write_bytes(orjson.dumps({"input_snapshots": ["market:002"]}))

        # Ensure deterministic ordering by making run-1 older
        os.utime(run1_meta, ns=(0, 1))

        service = ResearchArtifactService(artifact_root=tmp_path)
        result = service.read_source_snapshot_ids(
            "derived/artifacts/series/f.x/v1",
        )

        assert result == ("market:002",)

    def test_deduplicates_and_sorts_snapshot_ids(self, tmp_path: Path) -> None:
        runs_root = (
            tmp_path
            / "derived"
            / "artifacts"
            / "series"
            / "f.x"
            / "v1"
            / "_runs"
            / "run-1"
        )
        runs_root.mkdir(parents=True)
        metadata = {
            "input_snapshots": ["market:002", "market:001", "market:002", ""],
        }
        (runs_root / "artifact_metadata.json").write_bytes(orjson.dumps(metadata))

        service = ResearchArtifactService(artifact_root=tmp_path)
        result = service.read_source_snapshot_ids(
            "derived/artifacts/series/f.x/v1",
        )

        assert result == ("market:001", "market:002")

    def test_returns_empty_for_non_list_snapshots(self, tmp_path: Path) -> None:
        runs_root = (
            tmp_path
            / "derived"
            / "artifacts"
            / "series"
            / "f.x"
            / "v1"
            / "_runs"
            / "run-1"
        )
        runs_root.mkdir(parents=True)
        (runs_root / "artifact_metadata.json").write_bytes(
            orjson.dumps({"input_snapshots": "not-a-list"}),
        )

        service = ResearchArtifactService(artifact_root=tmp_path)
        result = service.read_source_snapshot_ids(
            "derived/artifacts/series/f.x/v1",
        )

        assert result == ()

    def test_filters_empty_strings(self, tmp_path: Path) -> None:
        runs_root = (
            tmp_path
            / "derived"
            / "artifacts"
            / "series"
            / "f.x"
            / "v1"
            / "_runs"
            / "run-1"
        )
        runs_root.mkdir(parents=True)
        (runs_root / "artifact_metadata.json").write_bytes(
            orjson.dumps({"input_snapshots": ["", "market:001", ""]}),
        )

        service = ResearchArtifactService(artifact_root=tmp_path)
        result = service.read_source_snapshot_ids(
            "derived/artifacts/series/f.x/v1",
        )

        assert result == ("market:001",)
