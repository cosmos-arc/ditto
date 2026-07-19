"""Tests for ResearchArtifactService (artifact_service.py)."""

from __future__ import annotations

import hashlib
import os
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import orjson
import polars as pl
import pytest
from ditto_analysis.errors import (
    ExperimentConflictError,
    ExperimentSpecError,
    ResearchDatasetError,
)
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


class TestAtomicArtifactWrites:
    """Task 7 file writes must be canonically contained and atomically published."""

    @pytest.mark.parametrize(
        "relative_path",
        ["/absolute/file.parquet", "../escape.parquet", "a/../b.parquet", "C:/x"],
    )
    def test_all_writers_reject_noncanonical_paths_before_file_io(
        self,
        service: ResearchArtifactService,
        relative_path: str,
    ) -> None:
        with pytest.raises(ExperimentSpecError):
            service.write_parquet(relative_path, pl.DataFrame({"x": [1]}))

    def test_resolved_symlink_escape_is_rejected(
        self,
        tmp_path: Path,
    ) -> None:
        root = tmp_path / "root"
        outside = tmp_path / "outside"
        root.mkdir()
        outside.mkdir()
        (root / "link").symlink_to(outside, target_is_directory=True)
        service = ResearchArtifactService(artifact_root=root)

        with pytest.raises(ExperimentSpecError):
            service.write_json("link/escape.json", {"x": 1})

        assert not (outside / "escape.json").exists()

    def test_parquet_write_fsyncs_sibling_temp_before_atomic_replace(
        self,
        service: ResearchArtifactService,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        frame = pl.DataFrame({"x": [1, 2], "label": ["a", "b"]})
        original_fsync = os.fsync
        original_replace = os.replace
        calls: list[str] = []

        def observe_fsync(fd: int) -> None:
            calls.append("fsync")
            original_fsync(fd)

        def observe_replace(source: os.PathLike[str], target: os.PathLike[str]) -> None:
            source_path = Path(source)
            target_path = Path(target)
            assert source_path.parent == target_path.parent
            assert source_path.exists()
            assert not target_path.exists()
            calls.append("replace")
            original_replace(source, target)

        monkeypatch.setattr(os, "fsync", observe_fsync)
        monkeypatch.setattr(os, "replace", observe_replace)
        service.write_parquet("experiments/e-1/result.parquet", frame)

        assert calls == ["fsync", "replace"]
        assert pl.read_parquet(tmp_path / "experiments/e-1/result.parquet").equals(
            frame
        )
        assert tuple((tmp_path / "experiments/e-1").glob("*.tmp")) == ()

    def test_rename_failure_leaves_no_final_or_partial_file(
        self,
        service: ResearchArtifactService,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        def fail_replace(_source: os.PathLike[str], _target: os.PathLike[str]) -> None:
            raise OSError("injected rename failure")

        monkeypatch.setattr(os, "replace", fail_replace)
        with pytest.raises(OSError, match="injected rename failure"):
            service.write_parquet(
                "experiments/e-1/result.parquet", pl.DataFrame({"x": [1]})
            )

        assert not (tmp_path / "experiments/e-1/result.parquet").exists()
        assert tuple((tmp_path / "experiments/e-1").glob("*.tmp")) == ()


class TestImmutableArtifactPublication:
    """R3 evidence publication is immutable and separate from generic writes."""

    def test_publish_uses_fsynced_closed_sibling_temp_and_no_clobber_link(
        self,
        service: ResearchArtifactService,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        payload = b"immutable-evidence"
        original_mkstemp = tempfile.mkstemp
        original_fsync = os.fsync
        original_link = os.link
        descriptor: int | None = None
        calls: list[str] = []

        def capture_mkstemp(
            suffix: str | None = None,
            prefix: str | None = None,
            dir: str | os.PathLike[str] | None = None,  # noqa: A002
            text: bool = False,
        ) -> tuple[int, str]:
            nonlocal descriptor
            descriptor, temporary_name = original_mkstemp(
                suffix=suffix,
                prefix=prefix,
                dir=dir,
                text=text,
            )
            return descriptor, temporary_name

        def observe_fsync(fd: int) -> None:
            assert fd == descriptor
            calls.append("fsync")
            original_fsync(fd)

        def observe_link(
            source: str | os.PathLike[str],
            target: str | os.PathLike[str],
        ) -> None:
            source_path = Path(source)
            target_path = Path(target)
            assert calls == ["fsync"]
            assert descriptor is not None
            with pytest.raises(OSError):
                os.fstat(descriptor)
            assert source_path.parent == target_path.parent
            assert source_path.exists()
            assert not target_path.exists()
            calls.append("link")
            original_link(source, target)

        monkeypatch.setattr(tempfile, "mkstemp", capture_mkstemp)
        monkeypatch.setattr(os, "fsync", observe_fsync)
        monkeypatch.setattr(os, "link", observe_link)

        digest = service.publish_immutable_artifact(
            "experiments/e-1/evidence.bin", payload
        )

        assert digest == hashlib.sha256(payload).hexdigest()
        assert calls == ["fsync", "link"]
        assert (tmp_path / "experiments/e-1/evidence.bin").read_bytes() == payload
        assert tuple((tmp_path / "experiments/e-1").glob("*.tmp")) == ()

    def test_identical_replay_is_a_noop(
        self,
        service: ResearchArtifactService,
        tmp_path: Path,
    ) -> None:
        relative_path = "experiments/e-1/evidence.bin"
        payload = b"same-evidence"
        expected_digest = hashlib.sha256(payload).hexdigest()
        assert (
            service.publish_immutable_artifact(relative_path, payload)
            == expected_digest
        )
        target = tmp_path / relative_path
        before = target.stat()

        replay_digest = service.publish_immutable_artifact(relative_path, payload)

        after = target.stat()
        assert replay_digest == expected_digest
        assert (after.st_ino, after.st_mtime_ns, after.st_size) == (
            before.st_ino,
            before.st_mtime_ns,
            before.st_size,
        )
        assert tuple(target.parent.glob("*.tmp")) == ()

    def test_conflicting_replay_preserves_existing_bytes_without_partial(
        self,
        service: ResearchArtifactService,
        tmp_path: Path,
    ) -> None:
        relative_path = "experiments/e-1/evidence.bin"
        original = b"original-evidence"
        conflicting = b"conflicting-evidence"
        service.publish_immutable_artifact(relative_path, original)

        with pytest.raises(ExperimentConflictError) as exc_info:
            service.publish_immutable_artifact(relative_path, conflicting)

        assert exc_info.value.details == {
            "reason_code": "immutable_artifact_conflict",
            "relative_path": relative_path,
            "existing_sha256": hashlib.sha256(original).hexdigest(),
            "incoming_sha256": hashlib.sha256(conflicting).hexdigest(),
        }
        target = tmp_path / relative_path
        assert target.read_bytes() == original
        assert tuple(target.parent.glob("*.tmp")) == ()

    def test_concurrent_publishers_choose_one_content_without_clobber(
        self,
        service: ResearchArtifactService,
        tmp_path: Path,
    ) -> None:
        relative_path = "experiments/e-1/evidence.bin"
        payloads = (b"worker-a", b"worker-b")
        barrier = threading.Barrier(len(payloads))

        def publish(payload: bytes) -> tuple[str, str]:
            barrier.wait()
            try:
                digest = service.publish_immutable_artifact(relative_path, payload)
            except ExperimentConflictError as exc:
                return "conflict", str(exc.details["incoming_sha256"])
            return "published", digest

        with ThreadPoolExecutor(max_workers=len(payloads)) as executor:
            results = tuple(executor.map(publish, payloads))

        target = tmp_path / relative_path
        winning_payload = target.read_bytes()
        winning_digest = hashlib.sha256(winning_payload).hexdigest()
        assert winning_payload in payloads
        assert tuple(status for status, _digest in results).count("published") == 1
        assert tuple(status for status, _digest in results).count("conflict") == 1
        assert ("published", winning_digest) in results
        assert tuple(target.parent.glob("*.tmp")) == ()

    def test_generic_json_writer_keeps_overwrite_semantics(
        self,
        service: ResearchArtifactService,
    ) -> None:
        service.write_json("mutable.json", {"revision": 1})

        service.write_json("mutable.json", {"revision": 2})

        assert service.read_json("mutable.json") == {"revision": 2}


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
