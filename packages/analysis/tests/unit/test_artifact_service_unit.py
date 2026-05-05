"""Tests for ResearchArtifactService (artifact_service.py)."""

from __future__ import annotations

from pathlib import Path

import orjson
import polars as pl
import pytest
from ditto_analysis.errors import ResearchDatasetError
from ditto_analysis.research.artifact_service import ResearchArtifactService


@pytest.fixture
def service(tmp_path: Path) -> ResearchArtifactService:
    """Create a ResearchArtifactService rooted in a temp directory."""
    return ResearchArtifactService(artifact_root=tmp_path)


class TestReadParquet:
    """Tests for read_parquet."""

    def test_read_parquet_exists(
        self, service: ResearchArtifactService, tmp_path: Path
    ) -> None:
        """Reading an existing parquet file should return the DataFrame."""
        frame = pl.DataFrame({"a": [1, 2], "b": [3.0, 4.0]})
        path = tmp_path / "data.parquet"
        frame.write_parquet(path)

        result = service.read_parquet("data.parquet")

        assert result.shape == (2, 2)
        assert result["a"].to_list() == [1, 2]

    def test_read_parquet_not_found(self, service: ResearchArtifactService) -> None:
        """Reading a missing parquet file should raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="research parquet not found"):
            service.read_parquet("missing.parquet")


class TestWriteParquet:
    """Tests for write_parquet."""

    def test_write_parquet(
        self, service: ResearchArtifactService, tmp_path: Path
    ) -> None:
        """Writing and reading back should yield the same DataFrame."""
        frame = pl.DataFrame({"x": [10, 20], "y": ["a", "b"]})

        service.write_parquet("output.parquet", frame)

        result = service.read_parquet("output.parquet")
        assert result["x"].to_list() == [10, 20]
        assert result["y"].to_list() == ["a", "b"]

    def test_write_parquet_creates_dirs(
        self, service: ResearchArtifactService, tmp_path: Path
    ) -> None:
        """write_parquet should create intermediate directories."""
        frame = pl.DataFrame({"z": [1]})

        service.write_parquet("nested/deep/dir/data.parquet", frame)

        assert (tmp_path / "nested" / "deep" / "dir" / "data.parquet").exists()


class TestExportDataset:
    """Tests for export_dataset."""

    def test_export_dataset_parquet(
        self, service: ResearchArtifactService, tmp_path: Path
    ) -> None:
        """Exporting as parquet should create a readable parquet file."""
        frame = pl.DataFrame({"col": [1, 2]})

        service.export_dataset("out.parquet", frame, fmt="parquet")

        assert (tmp_path / "out.parquet").exists()
        result = pl.read_parquet(tmp_path / "out.parquet")
        assert result["col"].to_list() == [1, 2]

    def test_export_dataset_csv(
        self, service: ResearchArtifactService, tmp_path: Path
    ) -> None:
        """Exporting as csv should create a readable CSV file."""
        frame = pl.DataFrame({"col": [1, 2]})

        service.export_dataset("out.csv", frame, fmt="csv")

        assert (tmp_path / "out.csv").exists()
        result = pl.read_csv(tmp_path / "out.csv")
        assert result["col"].to_list() == [1, 2]

    def test_export_dataset_feather(
        self, service: ResearchArtifactService, tmp_path: Path
    ) -> None:
        """Exporting as feather should create a readable IPC file."""
        frame = pl.DataFrame({"col": [1, 2]})

        service.export_dataset("out.feather", frame, fmt="feather")

        assert (tmp_path / "out.feather").exists()
        result = pl.read_ipc(tmp_path / "out.feather")
        assert result["col"].to_list() == [1, 2]

    def test_export_dataset_unsupported(self, service: ResearchArtifactService) -> None:
        """Exporting with an unsupported format should raise ResearchDatasetError."""
        frame = pl.DataFrame({"col": [1]})

        with pytest.raises(
            ResearchDatasetError, match="unsupported format"
        ) as exc_info:
            service.export_dataset("out.xlsx", frame, fmt="xlsx")  # type: ignore[arg-type]
        assert exc_info.value.details == {
            "relative_path": "out.xlsx",
            "format": "xlsx",
            "supported": ("parquet", "csv", "feather"),
            "supported_formats": ("parquet", "csv", "feather"),
        }


class TestReadJson:
    """Tests for read_json."""

    def test_read_json_valid(
        self, service: ResearchArtifactService, tmp_path: Path
    ) -> None:
        """Reading a valid JSON object should return a dict."""
        data = {"key": "value", "num": 42}
        path = tmp_path / "test.json"
        path.write_bytes(orjson.dumps(data))

        result = service.read_json("test.json")

        assert result == {"key": "value", "num": 42}

    def test_read_json_not_found(self, service: ResearchArtifactService) -> None:
        """Reading a missing JSON file should raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="research JSON not found"):
            service.read_json("missing.json")

    def test_read_json_not_dict(
        self, service: ResearchArtifactService, tmp_path: Path
    ) -> None:
        """Reading a JSON file that is not a dict should raise ResearchDatasetError."""
        path = tmp_path / "list.json"
        path.write_bytes(orjson.dumps([1, 2, 3]))

        with pytest.raises(
            ResearchDatasetError, match="expected JSON object"
        ) as exc_info:
            service.read_json("list.json")
        assert exc_info.value.details == {
            "relative_path": "list.json",
            "expected": "object",
            "actual": "list",
        }


class TestWriteJson:
    """Tests for write_json."""

    def test_write_json(self, service: ResearchArtifactService, tmp_path: Path) -> None:
        """write_json should create a file with sorted keys and indentation."""
        data = {"b": 2, "a": 1}

        service.write_json("output.json", data)

        path = tmp_path / "output.json"
        assert path.exists()
        content = orjson.loads(path.read_bytes())
        assert content == {"a": 1, "b": 2}

    def test_write_json_creates_dirs(
        self, service: ResearchArtifactService, tmp_path: Path
    ) -> None:
        """write_json should create intermediate directories."""
        service.write_json("nested/dir/output.json", {"x": 1})

        assert (tmp_path / "nested" / "dir" / "output.json").exists()


class TestResolveArtifactRelativePath:
    """Tests for resolve_artifact_relative_path."""

    def test_resolve_artifact_relative_path_found(
        self,
        service: ResearchArtifactService,
        tmp_path: Path,
    ) -> None:
        """Should resolve an existing artifact path."""
        artifact_dir = (
            tmp_path / "derived" / "artifacts" / "series" / "factor.alpha" / "v2"
        )
        artifact_dir.mkdir(parents=True)

        result = service.resolve_artifact_relative_path("factor.alpha", 2)

        assert result is not None
        assert "factor.alpha" in result
        assert "v2" in result

    def test_resolve_artifact_relative_path_not_found(
        self,
        service: ResearchArtifactService,
    ) -> None:
        """Should return None when no artifact exists."""
        result = service.resolve_artifact_relative_path("nonexistent", 1)

        assert result is None


class TestReadSourceSnapshotIds:
    """Tests for read_source_snapshot_ids."""

    def test_read_source_snapshot_ids_valid(
        self,
        service: ResearchArtifactService,
        tmp_path: Path,
    ) -> None:
        """Should read and return sorted unique snapshot IDs from latest metadata."""
        version_path = tmp_path / "derived" / "v1"
        runs_path = version_path / "_runs" / "run_001"
        runs_path.mkdir(parents=True)
        metadata = {"input_snapshots": ["snap_b", "snap_a", "snap_b"]}
        (runs_path / "artifact_metadata.json").write_bytes(orjson.dumps(metadata))

        result = service.read_source_snapshot_ids("derived/v1")

        assert result == ("snap_a", "snap_b")

    def test_read_source_snapshot_ids_no_runs_dir(
        self,
        service: ResearchArtifactService,
        tmp_path: Path,
    ) -> None:
        """Should return empty tuple when _runs directory does not exist."""
        version_path = tmp_path / "derived" / "v1"
        version_path.mkdir(parents=True)

        result = service.read_source_snapshot_ids("derived/v1")

        assert result == ()

    def test_read_source_snapshot_ids_no_metadata_files(
        self,
        service: ResearchArtifactService,
        tmp_path: Path,
    ) -> None:
        """Should return empty tuple when no metadata files exist."""
        version_path = tmp_path / "derived" / "v1"
        runs_path = version_path / "_runs"
        runs_path.mkdir(parents=True)

        result = service.read_source_snapshot_ids("derived/v1")

        assert result == ()

    def test_read_source_snapshot_ids_non_list_input_snapshots(
        self,
        service: ResearchArtifactService,
        tmp_path: Path,
    ) -> None:
        """Should return empty tuple when input_snapshots is not a list."""
        version_path = tmp_path / "derived" / "v1"
        runs_path = version_path / "_runs" / "run_001"
        runs_path.mkdir(parents=True)
        metadata = {"input_snapshots": "not_a_list"}
        (runs_path / "artifact_metadata.json").write_bytes(orjson.dumps(metadata))

        result = service.read_source_snapshot_ids("derived/v1")

        assert result == ()

    def test_read_source_snapshot_ids_filters_empty_strings(
        self,
        service: ResearchArtifactService,
        tmp_path: Path,
    ) -> None:
        """Should filter out empty strings from snapshot IDs."""
        version_path = tmp_path / "derived" / "v1"
        runs_path = version_path / "_runs" / "run_001"
        runs_path.mkdir(parents=True)
        metadata = {"input_snapshots": ["snap_a", "", "snap_b"]}
        (runs_path / "artifact_metadata.json").write_bytes(orjson.dumps(metadata))

        result = service.read_source_snapshot_ids("derived/v1")

        assert result == ("snap_a", "snap_b")
