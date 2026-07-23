"""Tests for ResearchArtifactService (artifact_service.py)."""

from __future__ import annotations

import hashlib
import os
import stat
import tempfile
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import orjson
import polars as pl
import pytest
from ditto_analysis.errors import (
    ExperimentConflictError,
    ExperimentIntegrityError,
    ExperimentPersistenceError,
    ExperimentSpecError,
    ResearchDatasetError,
)
from ditto_analysis.experiments.artifact_manifest import ArtifactPublicationSpec
from ditto_analysis.experiments.models import (
    AttemptId,
    CandidateId,
    ContentHash,
    ExperimentId,
    FoldId,
)
from ditto_analysis.experiments.persistence import (
    ArtifactRecord,
    LeaseFence,
    canonical_payload,
)
from ditto_analysis.research import _indexed_artifacts as artifact_module
from ditto_analysis.research.artifact_service import ResearchArtifactService

NOW = datetime(2026, 7, 23, 1, 2, 3, 456789, tzinfo=UTC)
NOW_US = 1_774_000_000_000_000
FENCE = LeaseFence(
    experiment_id=ExperimentId("experiment-1"),
    owner_token="worker-1",
    revision=7,
    lease_until_epoch_us=NOW_US + 1_000,
)


class _MemoryArtifactIndex:
    """Thread-safe test port with the same immutable/CAS semantics as SQLite."""

    def __init__(self, artifact_root: Path | None = None) -> None:
        self.artifact_root = None if artifact_root is None else artifact_root.resolve()
        self.records: dict[str, ArtifactRecord] = {}
        self.add_calls = 0
        self.pin_calls = 0
        self.add_error: Exception | None = None
        self._lock = threading.Lock()

    def get_artifact(self, artifact_id: str) -> ArtifactRecord | None:
        with self._lock:
            return self.records.get(artifact_id)

    def get_artifact_by_relative_path(
        self, relative_path: str
    ) -> ArtifactRecord | None:
        with self._lock:
            return next(
                (
                    record
                    for record in self.records.values()
                    if record.relative_path == relative_path
                ),
                None,
            )

    def add_artifact(
        self,
        record: ArtifactRecord,
        *,
        lease_fence: LeaseFence,
        now_epoch_us: int,
        commit_guard: Callable[[], None],
    ) -> None:
        _ = (lease_fence, now_epoch_us)
        with self._lock:
            self.add_calls += 1
            if self.add_error is not None:
                raise self.add_error
            commit_guard()
            matches = tuple(
                item
                for item in self.records.values()
                if item.artifact_id == record.artifact_id
                or item.relative_path == record.relative_path
            )
            if not matches:
                self.records[record.artifact_id] = record
                return
            existing = matches[0]
            if replace(existing, is_pinned=False, pinned_at=None, revision=0) != record:
                raise ExperimentConflictError(
                    "artifact replay drift",
                    details={"reason_code": "artifact_replay_drift"},
                )

    def pin_artifact(
        self,
        artifact_id: str,
        *,
        expected_revision: int,
        pinned_at: datetime,
        commit_guard: Callable[[], None],
    ) -> ArtifactRecord:
        with self._lock:
            self.pin_calls += 1
            current = self.records.get(artifact_id)
            if (
                current is None
                or current.is_pinned
                or current.revision != expected_revision
            ):
                raise ExperimentConflictError(
                    "artifact pin revision is stale",
                    details={"reason_code": "stale_artifact_revision"},
                )
            commit_guard()
            pinned = replace(
                current,
                is_pinned=True,
                pinned_at=pinned_at,
                revision=expected_revision + 1,
            )
            self.records[artifact_id] = pinned
            return pinned


def _publication_spec(
    *,
    artifact_id: str = "artifact-attempt-1-result",
    relative_path: str = (
        "experiments/experiment-1/candidates/candidate-1/folds/fold-1/"
        "attempts/attempt-1/result.json"
    ),
    attempt_id: str = "attempt-1",
) -> ArtifactPublicationSpec:
    return ArtifactPublicationSpec(
        artifact_id=artifact_id,
        experiment_id=ExperimentId("experiment-1"),
        candidate_id=CandidateId("candidate-1"),
        fold_id=FoldId("fold-1"),
        attempt_id=AttemptId(attempt_id),
        artifact_kind="result",
        relative_path=relative_path,
        reproduction_fingerprint=ContentHash("a" * 64),
        audit={
            "run_id": "run-1",
            "attempt_id": attempt_id,
            "created_at": NOW.isoformat(),
        },
        created_at=NOW,
    )


def _indexed_service(
    tmp_path: Path,
    index: _MemoryArtifactIndex,
) -> ResearchArtifactService:
    index.artifact_root = tmp_path.resolve()
    return ResearchArtifactService(
        artifact_root=tmp_path,
        artifact_reader=index,
        artifact_writer=index,
    )


@pytest.fixture
def service(tmp_path: Path) -> ResearchArtifactService:
    """Create a ResearchArtifactService rooted in a temp directory."""
    return ResearchArtifactService(artifact_root=tmp_path)


def test_production_provider_separates_legacy_and_indexed_roots(
    tmp_path: Path,
) -> None:
    from ditto_analysis.di.storage import AnalysisStorageProvider
    from ditto_analysis.storage.sqlite.experiments import (
        ResearchExperimentDatabase,
        SQLiteExperimentReader,
        SQLiteExperimentWriter,
    )

    database = ResearchExperimentDatabase(tmp_path)
    reader = SQLiteExperimentReader(database)
    writer = SQLiteExperimentWriter(database)
    wired = AnalysisStorageProvider().research_artifact_service(
        tmp_path,
        database,
        reader,
        writer,
    )

    assert wired.artifact_root == tmp_path.resolve()
    assert wired.indexed_artifact_root == database.artifact_root
    wired.write_json("legacy/result.json", {"legacy": True})
    with pytest.raises(ExperimentSpecError) as exc_info:
        wired.write_json(
            "research/artifacts/experiments/experiment-1/result.json",
            {"bypass": True},
        )
    assert (
        exc_info.value.details["reason_code"]
        == "indexed_artifact_requires_verified_api"
    )
    database.close_all()


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
            mode = os.fstat(fd).st_mode
            if stat.S_ISREG(mode):
                assert calls == []
                calls.append("file_fsync")
            elif stat.S_ISDIR(mode):
                assert calls == ["file_fsync", "link"]
                calls.append("directory_fsync")
            else:  # pragma: no cover - defensive assertion for unexpected handles
                pytest.fail("immutable publisher fsync used an unexpected file type")
            original_fsync(fd)

        def observe_link(
            source: str | os.PathLike[str],
            target: str | os.PathLike[str],
        ) -> None:
            source_path = Path(source)
            target_path = Path(target)
            assert calls == ["file_fsync"]
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
        assert calls == ["file_fsync", "link", "directory_fsync"]
        assert (tmp_path / "experiments/e-1/evidence.bin").read_bytes() == payload
        assert tuple((tmp_path / "experiments/e-1").glob("*.tmp")) == ()

    def test_identical_replay_is_a_noop(
        self,
        service: ResearchArtifactService,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
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
        directory_fsyncs: list[Path] = []
        original_fsync = os.fsync

        def observe_replay_fsync(fd: int) -> None:
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                directory_fsyncs.append(target.parent)
            original_fsync(fd)

        monkeypatch.setattr(os, "fsync", observe_replay_fsync)

        replay_digest = service.publish_immutable_artifact(relative_path, payload)

        after = target.stat()
        assert replay_digest == expected_digest
        assert (after.st_ino, after.st_mtime_ns, after.st_size) == (
            before.st_ino,
            before.st_mtime_ns,
            before.st_size,
        )
        assert tuple(target.parent.glob("*.tmp")) == ()
        assert directory_fsyncs == [target.parent]

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


class TestIndexedArtifactPublication:
    """R3 evidence publication measures final bytes before indexing them."""

    def test_json_publish_measures_and_indexes_only_after_no_clobber_publish(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        index = _MemoryArtifactIndex()
        service = _indexed_service(tmp_path, index)
        spec = _publication_spec()
        observed: list[str] = []
        original_measure = artifact_module._measure_json_artifact
        original_publish = artifact_module._publish_no_clobber

        def observe_measure(path: Path) -> object:
            assert path.exists()
            observed.append(
                "measure_temp" if path.suffix == ".tmp" else "measure_final"
            )
            return original_measure(path)

        def observe_publish(temporary: Path, target: Path) -> bool:
            assert temporary.parent == target.parent
            if target.name == artifact_module._manifest_sidecar_name("result.json"):
                assert observed == ["measure_temp"]
                observed.append("publish_sidecar")
            else:
                assert target.name == "result.json"
                assert observed == ["measure_temp", "publish_sidecar"]
                observed.append("publish_data")
            return original_publish(temporary, target)

        original_add = index.add_artifact

        def observe_add(
            record: ArtifactRecord,
            *,
            lease_fence: LeaseFence,
            now_epoch_us: int,
            commit_guard: Callable[[], None],
        ) -> None:
            assert observed == [
                "measure_temp",
                "publish_sidecar",
                "publish_data",
            ]
            assert (tmp_path / record.relative_path).is_file()
            assert tuple((tmp_path / record.relative_path).parent.glob("*.tmp")) == ()
            commit_guard()
            observed.append("guard")
            observed.append("index")
            original_add(
                record,
                lease_fence=lease_fence,
                now_epoch_us=now_epoch_us,
                commit_guard=lambda: None,
            )

        monkeypatch.setattr(artifact_module, "_measure_json_artifact", observe_measure)
        monkeypatch.setattr(artifact_module, "_publish_no_clobber", observe_publish)
        monkeypatch.setattr(index, "add_artifact", observe_add)

        record = service.publish_indexed_json(
            spec,
            {"z": 2, "a": "value"},
            lease_fence=FENCE,
            now_epoch_us=NOW_US,
        )

        target = tmp_path / spec.relative_path
        assert observed == [
            "measure_temp",
            "publish_sidecar",
            "publish_data",
            "guard",
            "index",
        ]
        assert record == index.get_artifact(spec.artifact_id)
        assert record.content_hash == ContentHash(
            hashlib.sha256(target.read_bytes()).hexdigest()
        )
        assert (
            target.read_bytes() == canonical_payload({"z": 2, "a": "value"}).json_bytes
        )
        assert record.byte_size == target.stat().st_size
        assert record.row_count == 1
        assert record.manifest["format"] == "json"
        assert (
            record.content_hash
            == canonical_payload({"z": 2, "a": "value"}).content_hash
        )

    def test_parquet_measurements_come_from_closed_temp_bytes(
        self,
        tmp_path: Path,
    ) -> None:
        index = _MemoryArtifactIndex()
        service = _indexed_service(tmp_path, index)
        spec = _publication_spec(
            artifact_id="artifact-attempt-1-nav",
            relative_path=(
                "experiments/experiment-1/candidates/candidate-1/folds/fold-1/"
                "attempts/attempt-1/nav.parquet"
            ),
        )
        frame = pl.DataFrame({"date": ["2026-01-01", "2026-01-02"], "nav": [1.0, 1.1]})

        record = service.publish_indexed_parquet(
            spec,
            frame,
            lease_fence=FENCE,
            now_epoch_us=NOW_US,
        )

        assert record.row_count == 2
        assert record.byte_size == (tmp_path / spec.relative_path).stat().st_size
        assert service.read_indexed_parquet(spec.artifact_id).equals(frame)

    @pytest.mark.parametrize(
        "failure_stage",
        ["write", "fsync", "measure", "publish"],
    )
    def test_pre_index_failures_leave_no_final_temp_or_index(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        failure_stage: str,
    ) -> None:
        index = _MemoryArtifactIndex()
        service = _indexed_service(tmp_path, index)
        spec = _publication_spec()

        def fail(*_args: object, **_kwargs: object) -> object:
            raise OSError(f"injected {failure_stage} failure")

        if failure_stage == "write":
            monkeypatch.setattr(artifact_module, "_write_json_file", fail)
        elif failure_stage == "measure":
            monkeypatch.setattr(artifact_module, "_measure_json_artifact", fail)
        elif failure_stage == "publish":
            monkeypatch.setattr(artifact_module, "_publish_no_clobber", fail)
        else:
            original_fsync = os.fsync

            def fail_file_fsync(fd: int) -> None:
                if stat.S_ISREG(os.fstat(fd).st_mode):
                    raise OSError("injected fsync failure")
                original_fsync(fd)

            monkeypatch.setattr(os, "fsync", fail_file_fsync)

        with pytest.raises(OSError, match=f"injected {failure_stage} failure"):
            service.publish_indexed_json(
                spec,
                {"value": 1},
                lease_fence=FENCE,
                now_epoch_us=NOW_US,
            )

        target = tmp_path / spec.relative_path
        assert not target.exists()
        assert tuple(target.parent.glob("*.tmp")) == ()
        assert index.get_artifact(spec.artifact_id) is None
        assert index.add_calls == 0

    def test_index_failure_retains_unindexed_orphan_for_exact_recovery(
        self,
        tmp_path: Path,
    ) -> None:
        index = _MemoryArtifactIndex()
        service = _indexed_service(tmp_path, index)
        spec = _publication_spec()
        payload = {"value": 1}
        index.add_error = ExperimentPersistenceError(
            "injected index failure",
            details={"reason_code": "artifact_insert_failed"},
        )

        with pytest.raises(ExperimentPersistenceError, match="injected index failure"):
            service.publish_indexed_json(
                spec,
                payload,
                lease_fence=FENCE,
                now_epoch_us=NOW_US,
            )

        target = tmp_path / spec.relative_path
        before = target.stat()
        assert target.is_file()
        assert index.get_artifact(spec.artifact_id) is None
        with pytest.raises(ExperimentIntegrityError) as exc_info:
            service.read_indexed_json(spec.artifact_id)
        assert exc_info.value.details["reason_code"] == "artifact_not_indexed"

        index.add_error = None
        recovered = service.publish_indexed_json(
            spec,
            payload,
            lease_fence=FENCE,
            now_epoch_us=NOW_US + 1,
        )

        after = target.stat()
        assert (after.st_ino, after.st_mtime_ns, after.st_size) == (
            before.st_ino,
            before.st_mtime_ns,
            before.st_size,
        )
        assert recovered == index.get_artifact(spec.artifact_id)
        assert service.read_indexed_json(spec.artifact_id) == payload

    def test_orphan_cannot_be_claimed_by_a_different_artifact_identity(
        self,
        tmp_path: Path,
    ) -> None:
        index = _MemoryArtifactIndex()
        service = _indexed_service(tmp_path, index)
        original = _publication_spec()
        index.add_error = ExperimentPersistenceError("injected index failure")
        with pytest.raises(ExperimentPersistenceError):
            service.publish_indexed_json(
                original,
                {"value": 1},
                lease_fence=FENCE,
                now_epoch_us=NOW_US,
            )
        index.add_error = None

        with pytest.raises(ExperimentConflictError) as exc_info:
            service.publish_indexed_json(
                _publication_spec(artifact_id="artifact-stolen-identity"),
                {"value": 1},
                lease_fence=FENCE,
                now_epoch_us=NOW_US + 1,
            )

        assert exc_info.value.details["reason_code"] == "artifact_identity_conflict"
        assert index.get_artifact(original.artifact_id) is None
        assert index.get_artifact("artifact-stolen-identity") is None

    def test_sidecar_only_orphan_is_repaired_only_by_exact_retry(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        index = _MemoryArtifactIndex()
        service = _indexed_service(tmp_path, index)
        spec = _publication_spec()
        original_publish = artifact_module._publish_no_clobber
        fail_data_once = True

        def publish_sidecar_then_fail_data(temporary: Path, target: Path) -> bool:
            nonlocal fail_data_once
            if target.name == "result.json" and fail_data_once:
                fail_data_once = False
                raise OSError("injected data publication failure")
            return original_publish(temporary, target)

        monkeypatch.setattr(
            artifact_module,
            "_publish_no_clobber",
            publish_sidecar_then_fail_data,
        )

        with pytest.raises(OSError, match="injected data publication failure"):
            service.publish_indexed_json(
                spec,
                {"value": 1},
                lease_fence=FENCE,
                now_epoch_us=NOW_US,
            )

        target = tmp_path / spec.relative_path
        sidecar = target.with_name(artifact_module._manifest_sidecar_name(target.name))
        assert sidecar.is_file()
        assert not target.exists()
        assert index.get_artifact(spec.artifact_id) is None

        recovered = service.publish_indexed_json(
            spec,
            {"value": 1},
            lease_fence=FENCE,
            now_epoch_us=NOW_US + 1,
        )

        assert recovered.artifact_id == spec.artifact_id
        assert target.is_file()
        assert service.read_indexed_json(spec.artifact_id) == {"value": 1}

    def test_sidecar_fsync_failure_exposes_neither_identity_nor_data(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        index = _MemoryArtifactIndex()
        service = _indexed_service(tmp_path, index)
        spec = _publication_spec()

        def fail_sidecar_fsync(*_args: object, **_kwargs: object) -> None:
            raise OSError("injected sidecar fsync failure")

        monkeypatch.setattr(
            artifact_module.IndexedArtifactIO,
            "_write_fsynced_bytes",
            staticmethod(fail_sidecar_fsync),
        )

        with pytest.raises(OSError, match="sidecar fsync failure"):
            service.publish_indexed_json(
                spec,
                {"value": 1},
                lease_fence=FENCE,
                now_epoch_us=NOW_US,
            )

        target = tmp_path / spec.relative_path
        sidecar = target.with_name(artifact_module._manifest_sidecar_name(target.name))
        assert not target.exists()
        assert not sidecar.exists()
        assert index.get_artifact(spec.artifact_id) is None
        assert tuple(target.parent.glob("*.tmp")) == ()

    def test_existing_target_symlink_is_never_claimed_or_followed(
        self,
        tmp_path: Path,
    ) -> None:
        index = _MemoryArtifactIndex()
        service = _indexed_service(tmp_path, index)
        spec = _publication_spec()
        target = tmp_path / spec.relative_path
        target.parent.mkdir(parents=True)
        outside = tmp_path / "outside-target.json"
        outside.write_bytes(b"outside")
        target.symlink_to(outside)

        with pytest.raises(ExperimentIntegrityError) as exc_info:
            service.publish_indexed_json(
                spec,
                {"value": 1},
                lease_fence=FENCE,
                now_epoch_us=NOW_US,
            )

        assert exc_info.value.details["reason_code"] == "artifact_sidecar_missing"
        assert outside.read_bytes() == b"outside"
        assert target.is_symlink()
        assert index.get_artifact(spec.artifact_id) is None

    def test_second_artifact_cannot_claim_an_internal_sidecar_name(
        self,
        tmp_path: Path,
    ) -> None:
        index = _MemoryArtifactIndex()
        service = _indexed_service(tmp_path, index)
        original = _publication_spec()
        record = service.publish_indexed_json(
            original,
            {"value": 1},
            lease_fence=FENCE,
            now_epoch_us=NOW_US,
        )
        parent = str(Path(original.relative_path).parent)

        with pytest.raises(ExperimentSpecError) as exc_info:
            _publication_spec(
                artifact_id="artifact-sidecar-collision",
                relative_path=f"{parent}/.result.json.ditto-manifest.json",
            )

        assert exc_info.value.details["reason_code"] == "artifact_path_reserved"
        assert service.read_indexed_json(record.artifact_id) == {"value": 1}
        assert len(index.records) == 1

    @pytest.mark.parametrize("sidecar_state", ["missing", "conflicting"])
    def test_missing_or_conflicting_sidecar_never_enters_index(
        self,
        tmp_path: Path,
        sidecar_state: str,
    ) -> None:
        index = _MemoryArtifactIndex()
        service = _indexed_service(tmp_path, index)
        spec = _publication_spec()
        target = tmp_path / spec.relative_path
        target.parent.mkdir(parents=True)
        target.write_bytes(orjson.dumps({"value": 1}, option=orjson.OPT_INDENT_2))
        if sidecar_state == "conflicting":
            target.with_name(
                artifact_module._manifest_sidecar_name(target.name)
            ).write_bytes(b'{"artifact_id":"different"}')

        expected_error = (
            ExperimentIntegrityError
            if sidecar_state == "missing"
            else ExperimentConflictError
        )
        with pytest.raises(expected_error) as exc_info:
            service.publish_indexed_json(
                spec,
                {"value": 1},
                lease_fence=FENCE,
                now_epoch_us=NOW_US,
            )

        assert exc_info.value.details["reason_code"] == (
            "artifact_sidecar_missing"
            if sidecar_state == "missing"
            else "artifact_identity_conflict"
        )
        assert index.get_artifact(spec.artifact_id) is None

    def test_different_content_cannot_recover_or_overwrite_orphan(
        self,
        tmp_path: Path,
    ) -> None:
        index = _MemoryArtifactIndex()
        service = _indexed_service(tmp_path, index)
        spec = _publication_spec()
        index.add_error = ExperimentPersistenceError("injected index failure")
        with pytest.raises(ExperimentPersistenceError):
            service.publish_indexed_json(
                spec,
                {"winner": 1},
                lease_fence=FENCE,
                now_epoch_us=NOW_US,
            )
        target = tmp_path / spec.relative_path
        original = target.read_bytes()
        index.add_error = None

        with pytest.raises(ExperimentConflictError) as exc_info:
            service.publish_indexed_json(
                spec,
                {"loser": 2},
                lease_fence=FENCE,
                now_epoch_us=NOW_US + 1,
            )

        assert exc_info.value.details["reason_code"] == "artifact_identity_conflict"
        assert target.read_bytes() == original
        assert index.get_artifact(spec.artifact_id) is None

    def test_retry_attempt_must_use_its_own_path_and_identity(
        self,
        tmp_path: Path,
    ) -> None:
        index = _MemoryArtifactIndex()
        service = _indexed_service(tmp_path, index)
        parent = _publication_spec()
        service.publish_indexed_json(
            parent,
            {"value": 1},
            lease_fence=FENCE,
            now_epoch_us=NOW_US,
        )
        with pytest.raises(ExperimentSpecError) as exc_info:
            _publication_spec(
                artifact_id="artifact-attempt-2-result",
                attempt_id="attempt-2",
            )

        assert exc_info.value.details["reason_code"] == "artifact_path_lineage_mismatch"
        child = _publication_spec(
            artifact_id="artifact-attempt-2-result",
            attempt_id="attempt-2",
            relative_path=(
                "experiments/experiment-1/candidates/candidate-1/folds/fold-1/"
                "attempts/attempt-2/result.json"
            ),
        )
        child_record = service.publish_indexed_json(
            child,
            {"value": 1},
            lease_fence=FENCE,
            now_epoch_us=NOW_US + 2,
        )
        assert child_record.attempt_id == AttemptId("attempt-2")
        assert len(index.records) == 2

    def test_same_content_concurrent_publish_is_one_immutable_fact(
        self,
        tmp_path: Path,
    ) -> None:
        index = _MemoryArtifactIndex()
        service = _indexed_service(tmp_path, index)
        spec = _publication_spec()
        barrier = threading.Barrier(2)

        def publish() -> ArtifactRecord:
            barrier.wait()
            return service.publish_indexed_json(
                spec,
                {"value": 1},
                lease_fence=FENCE,
                now_epoch_us=NOW_US,
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = tuple(executor.map(lambda _item: publish(), range(2)))

        assert results[0] == results[1]
        assert len(index.records) == 1
        assert tuple((tmp_path / spec.relative_path).parent.glob("*.tmp")) == ()

    def test_different_content_concurrent_publish_has_one_identity_winner(
        self,
        tmp_path: Path,
    ) -> None:
        index = _MemoryArtifactIndex()
        service = _indexed_service(tmp_path, index)
        spec = _publication_spec()
        barrier = threading.Barrier(2)

        def publish(value: int) -> tuple[str, int]:
            barrier.wait()
            try:
                service.publish_indexed_json(
                    spec,
                    {"value": value},
                    lease_fence=FENCE,
                    now_epoch_us=NOW_US,
                )
            except ExperimentConflictError:
                return "conflict", value
            return "published", value

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = tuple(executor.map(publish, (1, 2)))

        assert tuple(status for status, _value in results).count("published") == 1
        assert tuple(status for status, _value in results).count("conflict") == 1
        winning_value = next(
            value for status, value in results if status == "published"
        )
        assert service.read_indexed_json(spec.artifact_id) == {"value": winning_value}
        assert len(index.records) == 1

    def test_empty_parquet_is_indexed_with_zero_rows(self, tmp_path: Path) -> None:
        index = _MemoryArtifactIndex()
        service = _indexed_service(tmp_path, index)
        spec = _publication_spec(
            artifact_id="artifact-empty-parquet",
            relative_path=(
                "experiments/experiment-1/candidates/candidate-1/folds/fold-1/"
                "attempts/attempt-1/empty.parquet"
            ),
        )
        frame = pl.DataFrame(schema={"value": pl.Int64})

        record = service.publish_indexed_parquet(
            spec,
            frame,
            lease_fence=FENCE,
            now_epoch_us=NOW_US,
        )

        assert record.row_count == 0
        assert service.read_indexed_parquet(record.artifact_id).equals(frame)

    def test_indexed_json_rejects_a_top_level_list_before_publication(
        self,
        tmp_path: Path,
    ) -> None:
        index = _MemoryArtifactIndex()
        service = _indexed_service(tmp_path, index)
        spec = _publication_spec()

        with pytest.raises(ResearchDatasetError):
            service.publish_indexed_json(
                spec,
                [],  # type: ignore[arg-type]
                lease_fence=FENCE,
                now_epoch_us=NOW_US,
            )

        assert not (tmp_path / spec.relative_path).exists()
        assert index.get_artifact(spec.artifact_id) is None

    def test_directory_fsync_failure_leaves_recoverable_unindexed_orphan(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        index = _MemoryArtifactIndex()
        service = _indexed_service(tmp_path, index)
        spec = _publication_spec()
        original_fsync = os.fsync
        original_publish = artifact_module._publish_no_clobber
        data_is_visible = False
        failed_once = False
        successful_directory_fsyncs_after_failure = 0

        def observe_publish(temporary: Path, target: Path) -> bool:
            nonlocal data_is_visible
            published = original_publish(temporary, target)
            if target.name == "result.json":
                data_is_visible = True
            return published

        def fail_directory_fsync(fd: int) -> None:
            nonlocal failed_once, successful_directory_fsyncs_after_failure
            if (
                stat.S_ISDIR(os.fstat(fd).st_mode)
                and data_is_visible
                and not failed_once
            ):
                failed_once = True
                raise OSError("injected directory fsync failure")
            if stat.S_ISDIR(os.fstat(fd).st_mode) and failed_once:
                successful_directory_fsyncs_after_failure += 1
            original_fsync(fd)

        monkeypatch.setattr(
            artifact_module,
            "_publish_no_clobber",
            observe_publish,
        )
        monkeypatch.setattr(os, "fsync", fail_directory_fsync)
        with pytest.raises(OSError, match="injected directory fsync failure"):
            service.publish_indexed_json(
                spec,
                {"value": 1},
                lease_fence=FENCE,
                now_epoch_us=NOW_US,
            )

        assert (tmp_path / spec.relative_path).is_file()
        assert index.get_artifact(spec.artifact_id) is None
        assert tuple((tmp_path / spec.relative_path).parent.glob("*.tmp")) == ()

        recovered = service.publish_indexed_json(
            spec,
            {"value": 1},
            lease_fence=FENCE,
            now_epoch_us=NOW_US + 1,
        )

        assert recovered.artifact_id == spec.artifact_id
        assert successful_directory_fsyncs_after_failure > 0
        assert index.get_artifact(spec.artifact_id) == recovered

    def test_created_directory_entries_are_fsynced_again_before_index_recovery(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        index = _MemoryArtifactIndex()
        service = _indexed_service(tmp_path, index)
        spec = _publication_spec()
        original_fsync = os.fsync
        failed_once = False
        directory_fsyncs_after_failure = 0

        def fail_first_directory_fsync(fd: int) -> None:
            nonlocal failed_once, directory_fsyncs_after_failure
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                if not failed_once:
                    failed_once = True
                    raise OSError("injected ancestor directory fsync failure")
                directory_fsyncs_after_failure += 1
            original_fsync(fd)

        monkeypatch.setattr(os, "fsync", fail_first_directory_fsync)
        with pytest.raises(OSError, match="ancestor directory fsync failure"):
            service.publish_indexed_json(
                spec,
                {"value": 1},
                lease_fence=FENCE,
                now_epoch_us=NOW_US,
            )

        assert index.get_artifact(spec.artifact_id) is None
        assert not (tmp_path / spec.relative_path).exists()

        record = service.publish_indexed_json(
            spec,
            {"value": 1},
            lease_fence=FENCE,
            now_epoch_us=NOW_US + 1,
        )

        assert directory_fsyncs_after_failure >= 1
        assert index.get_artifact(spec.artifact_id) == record

    def test_parent_swap_before_publish_never_writes_or_indexes_escape_target(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        index = _MemoryArtifactIndex()
        service = _indexed_service(tmp_path, index)
        spec = _publication_spec()
        outside = tmp_path / "outside"
        outside.mkdir()
        original_publish = artifact_module._publish_no_clobber

        def swap_parent_then_publish(temporary: Path, target: Path) -> bool:
            original_tree = tmp_path / "experiments"
            moved_tree = tmp_path / "experiments-original"
            original_tree.rename(moved_tree)
            original_tree.symlink_to(outside, target_is_directory=True)
            return original_publish(temporary, target)

        monkeypatch.setattr(
            artifact_module,
            "_publish_no_clobber",
            swap_parent_then_publish,
        )

        with pytest.raises(ExperimentSpecError) as exc_info:
            service.publish_indexed_json(
                spec,
                {"value": 1},
                lease_fence=FENCE,
                now_epoch_us=NOW_US,
            )

        assert exc_info.value.details["reason_code"] == "artifact_path_race_detected"
        assert tuple(outside.rglob("result.json")) == ()
        assert index.get_artifact(spec.artifact_id) is None

    def test_root_mismatch_is_rejected_before_any_file_or_index_write(
        self,
        tmp_path: Path,
    ) -> None:
        index = _MemoryArtifactIndex(tmp_path / "different-root")

        with pytest.raises(ExperimentSpecError) as exc_info:
            ResearchArtifactService(
                artifact_root=tmp_path,
                artifact_reader=index,
                artifact_writer=index,
            )

        assert exc_info.value.details["reason_code"] == "artifact_root_mismatch"

    def test_explicit_indexed_root_without_ports_is_rejected(
        self,
        tmp_path: Path,
    ) -> None:
        with pytest.raises(ExperimentSpecError) as exc_info:
            ResearchArtifactService(
                artifact_root=tmp_path,
                indexed_artifact_root=tmp_path / "reserved-indexed",
            )

        assert exc_info.value.details["reason_code"] == "artifact_index_port_incomplete"

    def test_json_schema_is_key_order_independent_but_shape_sensitive(
        self,
        tmp_path: Path,
    ) -> None:
        index = _MemoryArtifactIndex()
        service = _indexed_service(tmp_path, index)
        first = service.publish_indexed_json(
            _publication_spec(
                artifact_id="json-1",
                relative_path=(
                    "experiments/experiment-1/candidates/candidate-1/folds/fold-1/"
                    "attempts/attempt-1/a.json"
                ),
            ),
            {"b": [1, 2], "a": "x"},
            lease_fence=FENCE,
            now_epoch_us=NOW_US,
        )
        second = service.publish_indexed_json(
            _publication_spec(
                artifact_id="json-2",
                relative_path=(
                    "experiments/experiment-1/candidates/candidate-1/folds/fold-1/"
                    "attempts/attempt-1/b.json"
                ),
            ),
            {"a": "other", "b": [3]},
            lease_fence=FENCE,
            now_epoch_us=NOW_US + 1,
        )
        changed = service.publish_indexed_json(
            _publication_spec(
                artifact_id="json-3",
                relative_path=(
                    "experiments/experiment-1/candidates/candidate-1/folds/fold-1/"
                    "attempts/attempt-1/c.json"
                ),
            ),
            {"a": 1, "b": [3]},
            lease_fence=FENCE,
            now_epoch_us=NOW_US + 2,
        )

        assert first.schema_hash == second.schema_hash
        assert first.content_hash != second.content_hash
        assert changed.schema_hash != first.schema_hash

    def test_parquet_schema_tracks_column_order_and_dtype_not_values(
        self,
        tmp_path: Path,
    ) -> None:
        index = _MemoryArtifactIndex()
        service = _indexed_service(tmp_path, index)

        def publish(
            artifact_id: str,
            frame: pl.DataFrame,
        ) -> ArtifactRecord:
            return service.publish_indexed_parquet(
                _publication_spec(
                    artifact_id=artifact_id,
                    relative_path=(
                        "experiments/experiment-1/candidates/candidate-1/folds/fold-1/"
                        "attempts/attempt-1/"
                        f"{artifact_id}.parquet"
                    ),
                ),
                frame,
                lease_fence=FENCE,
                now_epoch_us=NOW_US,
            )

        first = publish("parquet-1", pl.DataFrame({"a": [1], "b": [1.0]}))
        values = publish("parquet-2", pl.DataFrame({"a": [2], "b": [2.0]}))
        reordered = publish("parquet-3", pl.DataFrame({"b": [2.0], "a": [2]}))
        changed_type = publish("parquet-4", pl.DataFrame({"a": [2.0], "b": [2.0]}))

        assert first.schema_hash == values.schema_hash
        assert first.content_hash != values.content_hash
        assert reordered.schema_hash != first.schema_hash
        assert changed_type.schema_hash != first.schema_hash


class TestIndexedArtifactReadAndPin:
    """Indexed reads and pins re-verify immutable file evidence."""

    def _published(
        self,
        tmp_path: Path,
    ) -> tuple[ResearchArtifactService, _MemoryArtifactIndex, ArtifactRecord]:
        index = _MemoryArtifactIndex()
        service = _indexed_service(tmp_path, index)
        record = service.publish_indexed_json(
            _publication_spec(),
            {"value": "evidence"},
            lease_fence=FENCE,
            now_epoch_us=NOW_US,
        )
        return service, index, record

    def test_corrupted_or_missing_file_fails_closed(self, tmp_path: Path) -> None:
        service, _index, record = self._published(tmp_path)
        target = tmp_path / record.relative_path
        original = target.read_bytes()
        target.write_bytes(b"x" * len(original))

        with pytest.raises(ExperimentIntegrityError) as exc_info:
            service.read_indexed_json(record.artifact_id)
        assert exc_info.value.details["reason_code"] == "artifact_content_mismatch"

        target.unlink()
        with pytest.raises(ExperimentIntegrityError) as exc_info:
            service.read_indexed_json(record.artifact_id)
        assert exc_info.value.details["reason_code"] == "artifact_file_missing"

    def test_directory_or_symlink_target_fails_closed(self, tmp_path: Path) -> None:
        service, _index, record = self._published(tmp_path)
        target = tmp_path / record.relative_path
        original = target.read_bytes()
        target.unlink()
        target.mkdir()
        with pytest.raises(ExperimentIntegrityError) as exc_info:
            service.read_indexed_json(record.artifact_id)
        assert exc_info.value.details["reason_code"] == "artifact_not_regular_file"
        target.rmdir()
        outside = tmp_path / "outside.json"
        outside.write_bytes(original)
        target.symlink_to(outside)
        with pytest.raises(ExperimentIntegrityError) as exc_info:
            service.read_indexed_json(record.artifact_id)
        assert exc_info.value.details["reason_code"] == "artifact_symlink_rejected"

    def test_manifest_and_reproduction_fingerprint_are_reverified(
        self,
        tmp_path: Path,
    ) -> None:
        service, index, record = self._published(tmp_path)
        index.records[record.artifact_id] = replace(
            record,
            reproduction_fingerprint=ContentHash("f" * 64),
        )

        with pytest.raises(ExperimentIntegrityError) as exc_info:
            service.read_indexed_json(record.artifact_id)

        assert exc_info.value.details["reason_code"] == "artifact_manifest_mismatch"

    @pytest.mark.parametrize("mutation", ["missing", "tampered"])
    def test_manifest_sidecar_is_mandatory_for_verified_read_and_pin(
        self,
        tmp_path: Path,
        mutation: str,
    ) -> None:
        service, index, record = self._published(tmp_path)
        target = tmp_path / record.relative_path
        sidecar = target.with_name(artifact_module._manifest_sidecar_name(target.name))
        if mutation == "missing":
            sidecar.unlink()
        else:
            sidecar.write_bytes(b'{"artifact_id":"tampered"}')

        with pytest.raises(ExperimentIntegrityError) as read_error:
            service.read_indexed_json(record.artifact_id)
        assert read_error.value.details["reason_code"] in {
            "artifact_sidecar_missing",
            "artifact_sidecar_mismatch",
        }
        with pytest.raises(ExperimentIntegrityError):
            service.pin_indexed_artifact(
                record.artifact_id,
                expected_revision=0,
                pinned_at=NOW,
            )
        assert index.pin_calls == 0

    def test_pin_verifies_file_then_performs_one_way_cas(self, tmp_path: Path) -> None:
        service, index, record = self._published(tmp_path)
        pinned = service.pin_indexed_artifact(
            record.artifact_id,
            expected_revision=0,
            pinned_at=NOW,
        )

        assert pinned.is_pinned is True
        assert pinned.pinned_at == NOW
        assert pinned.revision == 1
        assert index.pin_calls == 1
        with pytest.raises(ExperimentConflictError) as exc_info:
            service.pin_indexed_artifact(
                record.artifact_id,
                expected_revision=0,
                pinned_at=NOW,
            )
        assert exc_info.value.details["reason_code"] == "stale_artifact_revision"

    def test_pin_refuses_corrupt_file_before_index_cas(self, tmp_path: Path) -> None:
        service, index, record = self._published(tmp_path)
        (tmp_path / record.relative_path).write_bytes(b"corrupt")

        with pytest.raises(ExperimentIntegrityError):
            service.pin_indexed_artifact(
                record.artifact_id,
                expected_revision=0,
                pinned_at=NOW,
            )

        assert index.pin_calls == 0
        assert index.get_artifact(record.artifact_id) == record

    @pytest.mark.parametrize("pinned", [False, True])
    def test_legacy_raw_apis_cannot_bypass_indexed_namespace(
        self,
        tmp_path: Path,
        pinned: bool,
    ) -> None:
        service, _index, record = self._published(tmp_path)
        if pinned:
            service.pin_indexed_artifact(
                record.artifact_id,
                expected_revision=0,
                pinned_at=NOW,
            )
        target = tmp_path / record.relative_path
        original = target.read_bytes()
        calls: tuple[Callable[[], object], ...] = (
            lambda: service.read_json(record.relative_path),
            lambda: service.read_parquet(record.relative_path),
            lambda: service.write_json(record.relative_path, {"evil": True}),
            lambda: service.write_parquet(
                record.relative_path, pl.DataFrame({"evil": [True]})
            ),
            lambda: service.export_dataset(
                record.relative_path,
                pl.DataFrame({"evil": [True]}),
            ),
            lambda: service.publish_immutable_artifact(record.relative_path, b"evil"),
            lambda: service.read_source_snapshot_ids(record.relative_path),
        )

        for call in calls:
            with pytest.raises(ExperimentSpecError) as exc_info:
                call()
            assert (
                exc_info.value.details["reason_code"]
                == "indexed_artifact_requires_verified_api"
            )

        assert target.read_bytes() == original
        assert service.read_indexed_json(record.artifact_id) == {"value": "evidence"}

    def test_unindexed_file_cannot_be_read(self, tmp_path: Path) -> None:
        index = _MemoryArtifactIndex()
        service = _indexed_service(tmp_path, index)
        spec = _publication_spec()
        target = tmp_path / spec.relative_path
        target.parent.mkdir(parents=True)
        target.write_bytes(orjson.dumps({"unindexed": True}))

        with pytest.raises(ExperimentIntegrityError) as exc_info:
            service.read_indexed_json(spec.artifact_id)

        assert exc_info.value.details["reason_code"] == "artifact_not_indexed"

    def test_symlink_component_is_rejected_even_when_it_points_inside_root(
        self,
        tmp_path: Path,
    ) -> None:
        index = _MemoryArtifactIndex()
        real = tmp_path / "real"
        real.mkdir()
        (tmp_path / "experiments").symlink_to(real, target_is_directory=True)
        service = _indexed_service(tmp_path, index)
        spec = _publication_spec()

        with pytest.raises(ExperimentSpecError) as exc_info:
            service.publish_indexed_json(
                spec,
                {"value": 1},
                lease_fence=FENCE,
                now_epoch_us=NOW_US,
            )

        assert exc_info.value.details["reason_code"] == "artifact_symlink_rejected"
        assert index.add_calls == 0


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
