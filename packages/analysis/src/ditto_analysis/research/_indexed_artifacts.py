"""Race-aware immutable file publication composed with the artifact index."""

from __future__ import annotations

import os
import secrets
import stat
from collections.abc import Callable, Generator, Mapping
from contextlib import contextmanager, suppress
from dataclasses import replace
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import NoReturn, Protocol, cast

import orjson
import polars as pl

from ditto_analysis.errors import (
    ExperimentConflictError,
    ExperimentIntegrityError,
    ExperimentSpecError,
)
from ditto_analysis.experiments.artifact_manifest import (
    ArtifactFormat,
    ArtifactManifest,
    ArtifactPublicationSpec,
)
from ditto_analysis.experiments.persistence import (
    ArtifactRecord,
    LeaseFence,
    canonical_payload,
    validate_artifact_relative_path,
)
from ditto_analysis.research._artifact_file_primitives import (
    READ_FLAGS,
    SYNC_FLAGS,
    ArtifactFilePath,
    DirectoryEntryPath,
)
from ditto_analysis.research._artifact_file_primitives import (
    fsync_entry as _fsync_entry,
)
from ditto_analysis.research._artifact_file_primitives import (
    make_directory_entry as _make_directory_entry,
)
from ditto_analysis.research._artifact_file_primitives import (
    measure_json_artifact as _measure_json_artifact,
)
from ditto_analysis.research._artifact_file_primitives import (
    measure_parquet_artifact as _measure_parquet_artifact,
)
from ditto_analysis.research._artifact_file_primitives import (
    open_directory as _open_directory,
)
from ditto_analysis.research._artifact_file_primitives import (
    open_file as _open_file,
)
from ditto_analysis.research._artifact_file_primitives import (
    publish_no_clobber as _publish_no_clobber,
)
from ditto_analysis.research._artifact_file_primitives import (
    stat_entry as _stat_entry,
)
from ditto_analysis.research._artifact_file_primitives import (
    unlink_entry as _unlink_entry,
)
from ditto_analysis.research._artifact_file_primitives import (
    write_json_file as _write_json_file,
)
from ditto_analysis.research._artifact_file_primitives import (
    write_parquet_file as _write_parquet_file,
)
from ditto_analysis.research.artifact_measurement import (
    ArtifactMeasurement as _ArtifactMeasurement,
)
from ditto_analysis.research.artifact_measurement import (
    measure_json_bytes as _measure_json_bytes,
)
from ditto_analysis.research.artifact_measurement import (
    measure_parquet_bytes as _measure_parquet_bytes,
)

__all__ = ["ArtifactIndexReader", "ArtifactIndexWriter", "IndexedArtifactIO"]

_WRITE_FLAGS = (
    os.O_WRONLY
    | os.O_CREAT
    | os.O_EXCL
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_BINARY", 0)
)
_SIDECAR_SUFFIX = ".ditto-manifest.json"


class _DirectorySyncError(OSError):
    """Distinguish durability failures from unsafe path traversal."""


class ArtifactIndexReader(Protocol):
    """Narrow metadata read port consumed by verified file I/O."""

    @property
    def artifact_root(self) -> Path: ...

    def get_artifact(self, artifact_id: str) -> ArtifactRecord | None: ...

    def get_artifact_by_relative_path(
        self, relative_path: str
    ) -> ArtifactRecord | None: ...


class ArtifactIndexWriter(Protocol):
    """Narrow Schema v1 write port consumed after immutable publication."""

    @property
    def artifact_root(self) -> Path: ...

    def add_artifact(
        self,
        record: ArtifactRecord,
        *,
        lease_fence: LeaseFence,
        now_epoch_us: int,
        commit_guard: Callable[[], None],
    ) -> None: ...

    def pin_artifact(
        self,
        artifact_id: str,
        *,
        expected_revision: int,
        pinned_at: datetime,
        commit_guard: Callable[[], None],
    ) -> ArtifactRecord: ...


def _manifest_sidecar_name(target_name: str) -> str:
    return f".{target_name}{_SIDECAR_SUFFIX}"


def _conflict(message: str, reason_code: str, **details: object) -> NoReturn:
    raise ExperimentConflictError(
        message,
        details={"reason_code": reason_code, **details},
    )


def _integrity(message: str, reason_code: str, **details: object) -> NoReturn:
    raise ExperimentIntegrityError(
        message,
        details={"reason_code": reason_code, **details},
    )


def _initial(record: ArtifactRecord) -> ArtifactRecord:
    return replace(record, is_pinned=False, pinned_at=None, revision=0)


class IndexedArtifactIO:
    """Publish, verify, and pin Schema v1 experiment artifacts."""

    def __init__(
        self,
        *,
        artifact_root: Path,
        reader: ArtifactIndexReader | None,
        writer: ArtifactIndexWriter | None,
    ) -> None:
        if reader is None or writer is None:
            raise ExperimentSpecError(
                "indexed artifact service requires both reader and writer",
                details={"reason_code": "artifact_index_port_incomplete"},
            )
        self._root = artifact_root.resolve()
        if self._root == self._root.parent:
            raise ExperimentSpecError(
                "artifact root cannot be the filesystem root",
                details={"reason_code": "artifact_root_too_broad"},
            )
        for port in (reader, writer):
            port_root = Path(port.artifact_root).resolve()
            if port_root != self._root:
                raise ExperimentSpecError(
                    "artifact index and file service roots differ",
                    details={
                        "reason_code": "artifact_root_mismatch",
                        "service_root": str(self._root),
                        "index_root": str(port_root),
                    },
                )
        self._reader = reader
        self._writer = writer

    @staticmethod
    def _fd_entry(parent_fd: int, name: str) -> DirectoryEntryPath:
        return DirectoryEntryPath(parent_fd=parent_fd, name=name)

    @staticmethod
    def _open_absolute_directory(path: Path, *, durable: bool = False) -> int:
        parts = path.parts
        descriptors = [
            _open_directory(Path(parts[0]), durable=durable and len(parts) == 1)
        ]
        try:
            for index, part in enumerate(parts[1:], start=1):
                descriptors.append(
                    _open_directory(
                        DirectoryEntryPath(descriptors[-1], part),
                        durable=durable and index == len(parts) - 1,
                    )
                )
            result = descriptors.pop()
        finally:
            for descriptor in reversed(descriptors):
                with suppress(OSError):
                    os.close(descriptor)
        return result

    @staticmethod
    def _open_child_directory(
        parent_fd: int,
        name: str,
        *,
        durable: bool = False,
    ) -> int:
        return _open_directory(DirectoryEntryPath(parent_fd, name), durable=durable)

    @staticmethod
    def _ensure_durable_directory(parent_fd: int, name: str) -> None:
        try:
            _make_directory_entry(DirectoryEntryPath(parent_fd, name))
        except FileExistsError:
            pass
        try:
            _fsync_entry(parent_fd)
        except OSError as exc:
            raise _DirectorySyncError(str(exc)) from exc

    @contextmanager
    def _open_parent(
        self,
        relative_path: str,
        *,
        create: bool,
        read_integrity: bool = False,
    ) -> Generator[tuple[int, str]]:
        canonical = validate_artifact_relative_path(relative_path)
        descriptors: list[int] = []
        try:
            root_parent_fd = self._open_absolute_directory(
                self._root.parent, durable=create
            )
            descriptors.append(root_parent_fd)
            if create:
                self._ensure_durable_directory(root_parent_fd, self._root.name)
            descriptors.append(
                self._open_child_directory(
                    root_parent_fd, self._root.name, durable=create
                )
            )
            for part in canonical.parts[:-1]:
                if create:
                    self._ensure_durable_directory(descriptors[-1], part)
                descriptors.append(
                    self._open_child_directory(descriptors[-1], part, durable=create)
                )
        except _DirectorySyncError:
            for descriptor in reversed(descriptors):
                with suppress(OSError):
                    os.close(descriptor)
            raise
        except OSError as exc:
            for descriptor in reversed(descriptors):
                with suppress(OSError):
                    os.close(descriptor)
            if read_integrity:
                _integrity(
                    "indexed artifact parent is missing or unsafe",
                    "artifact_file_missing",
                    relative_path=relative_path,
                )
            raise ExperimentSpecError(
                "artifact path contains a symlink or non-directory component",
                details={
                    "reason_code": "artifact_symlink_rejected",
                    "relative_path": relative_path,
                },
            ) from exc
        try:
            yield descriptors[-1], canonical.name
        finally:
            for descriptor in reversed(descriptors):
                with suppress(OSError):
                    os.close(descriptor)

    def _assert_open_parent_is_current(
        self,
        relative_path: str,
        parent_fd: int,
    ) -> None:
        opened = os.fstat(parent_fd)
        try:
            with self._open_parent(relative_path, create=False) as (
                current_fd,
                _target_name,
            ):
                current = os.fstat(current_fd)
        except ExperimentSpecError as exc:
            raise ExperimentSpecError(
                "artifact parent changed during publication",
                details={"reason_code": "artifact_path_race_detected"},
            ) from exc
        if (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino):
            raise ExperimentSpecError(
                "artifact parent changed during publication",
                details={
                    "reason_code": "artifact_path_race_detected",
                    "relative_path": relative_path,
                },
            )

    def _indexed_identity(self, spec: ArtifactPublicationSpec) -> ArtifactRecord | None:
        by_id = self._reader.get_artifact(spec.artifact_id)
        by_path = self._reader.get_artifact_by_relative_path(spec.relative_path)
        if by_id is not None and by_path is not None and by_id != by_path:
            _conflict(
                "artifact identity and path point to different immutable facts",
                "artifact_identity_cross_conflict",
            )
        existing = by_id or by_path
        if existing is not None and (
            existing.artifact_id != spec.artifact_id
            or existing.relative_path != spec.relative_path
        ):
            _conflict(
                "artifact path is already bound to another identity",
                "artifact_path_identity_conflict",
                existing_artifact_id=existing.artifact_id,
            )
        return existing

    @staticmethod
    def _measurement_for(
        artifact_format: ArtifactFormat,
    ) -> Callable[[ArtifactFilePath], _ArtifactMeasurement]:
        return (
            _measure_json_artifact
            if artifact_format is ArtifactFormat.JSON
            else _measure_parquet_artifact
        )

    def _measure_target(
        self,
        parent_fd: int,
        target_name: str,
        artifact_format: ArtifactFormat,
        *,
        artifact_id: str,
    ) -> tuple[_ArtifactMeasurement, bytes]:
        try:
            descriptor = _open_file(
                DirectoryEntryPath(parent_fd, target_name),
                READ_FLAGS,
            )
        except FileNotFoundError:
            _integrity(
                "indexed artifact file is missing",
                "artifact_file_missing",
                artifact_id=artifact_id,
            )
        except OSError as exc:
            try:
                target_stat = _stat_entry(DirectoryEntryPath(parent_fd, target_name))
            except OSError:
                target_stat = None
            reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
            reason_code = (
                "artifact_symlink_rejected"
                if target_stat is not None
                and (
                    stat.S_ISLNK(target_stat.st_mode)
                    or getattr(target_stat, "st_file_attributes", 0) & reparse
                )
                else "artifact_not_regular_file"
            )
            raise ExperimentIntegrityError(
                "indexed artifact is not a safe regular file",
                details={"reason_code": reason_code, "artifact_id": artifact_id},
            ) from exc
        try:
            opened = os.fstat(descriptor)
            if not stat.S_ISREG(opened.st_mode):
                _integrity(
                    "indexed artifact is not a regular file",
                    "artifact_not_regular_file",
                    artifact_id=artifact_id,
                )
            with os.fdopen(descriptor, "rb", closefd=False) as stream:
                payload = stream.read()
            measurement = (
                _measure_json_bytes(payload)
                if artifact_format is ArtifactFormat.JSON
                else _measure_parquet_bytes(payload)
            )
            return measurement, payload
        except (OSError, orjson.JSONDecodeError, pl.exceptions.PolarsError) as exc:
            raise ExperimentIntegrityError(
                "indexed artifact bytes cannot be decoded",
                details={
                    "reason_code": "artifact_content_mismatch",
                    "artifact_id": artifact_id,
                },
            ) from exc
        finally:
            os.close(descriptor)

    @staticmethod
    def _entry_exists(parent_fd: int, name: str) -> bool:
        try:
            _stat_entry(DirectoryEntryPath(parent_fd, name))
        except FileNotFoundError:
            return False
        return True

    @staticmethod
    def _sidecar_bytes(record: ArtifactRecord) -> bytes:
        return canonical_payload(record.manifest).json_bytes

    def _require_sidecar(
        self,
        parent_fd: int,
        target_name: str,
        record: ArtifactRecord,
        *,
        conflict_on_mismatch: bool,
    ) -> None:
        sidecar_name = _manifest_sidecar_name(target_name)
        try:
            descriptor = _open_file(
                DirectoryEntryPath(parent_fd, sidecar_name), READ_FLAGS
            )
        except FileNotFoundError:
            _integrity(
                "indexed artifact identity sidecar is missing",
                "artifact_sidecar_missing",
                artifact_id=record.artifact_id,
            )
        except OSError as exc:
            raise ExperimentIntegrityError(
                "indexed artifact identity sidecar is unsafe",
                details={
                    "reason_code": "artifact_sidecar_mismatch",
                    "artifact_id": record.artifact_id,
                },
            ) from exc
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                _integrity(
                    "indexed artifact identity sidecar is not a regular file",
                    "artifact_sidecar_mismatch",
                    artifact_id=record.artifact_id,
                )
            with os.fdopen(descriptor, "rb", closefd=False) as stream:
                actual = stream.read()
        finally:
            os.close(descriptor)
        if actual != self._sidecar_bytes(record):
            if conflict_on_mismatch:
                _conflict(
                    "artifact path is owned by another publication identity",
                    "artifact_identity_conflict",
                    artifact_id=record.artifact_id,
                )
            _integrity(
                "indexed artifact identity sidecar differs from its index",
                "artifact_sidecar_mismatch",
                artifact_id=record.artifact_id,
            )

    @staticmethod
    def _write_fsynced_bytes(parent_fd: int, name: str, payload: bytes) -> None:
        descriptor = _open_file(
            DirectoryEntryPath(parent_fd, name),
            _WRITE_FLAGS,
            0o600,
        )
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            _fsync_entry(stream.fileno())

    def _publish_sidecar(
        self,
        parent_fd: int,
        target_name: str,
        record: ArtifactRecord,
    ) -> None:
        sidecar_name = _manifest_sidecar_name(target_name)
        sidecar_temporary_name = f".{sidecar_name}.{secrets.token_hex(12)}.tmp"
        try:
            self._write_fsynced_bytes(
                parent_fd,
                sidecar_temporary_name,
                self._sidecar_bytes(record),
            )
            _publish_no_clobber(
                self._fd_entry(parent_fd, sidecar_temporary_name),
                self._fd_entry(parent_fd, sidecar_name),
            )
            _unlink_entry(DirectoryEntryPath(parent_fd, sidecar_temporary_name))
            _fsync_entry(parent_fd)
            self._require_sidecar(
                parent_fd,
                target_name,
                record,
                conflict_on_mismatch=True,
            )
        finally:
            with suppress(FileNotFoundError):
                _unlink_entry(DirectoryEntryPath(parent_fd, sidecar_temporary_name))

    @staticmethod
    def _require_measurement(
        record: ArtifactRecord,
        actual: _ArtifactMeasurement,
    ) -> None:
        if (
            actual.content_hash != record.content_hash
            or actual.byte_size != record.byte_size
            or actual.schema_hash != record.schema_hash
            or actual.row_count != record.row_count
        ):
            _integrity(
                "indexed artifact measurements differ from final bytes",
                "artifact_content_mismatch",
                artifact_id=record.artifact_id,
            )

    def _verify_record(
        self,
        record: ArtifactRecord,
        artifact_format: ArtifactFormat,
    ) -> tuple[ArtifactManifest, bytes]:
        manifest = ArtifactManifest.from_record(record)
        if manifest.artifact_format is not artifact_format:
            _integrity(
                "indexed artifact format differs from requested decoder",
                "artifact_format_mismatch",
                artifact_id=record.artifact_id,
            )
        with self._open_parent(
            record.relative_path,
            create=False,
            read_integrity=True,
        ) as (parent_fd, target_name):
            self._require_sidecar(
                parent_fd,
                target_name,
                record,
                conflict_on_mismatch=False,
            )
            actual, payload = self._measure_target(
                parent_fd,
                target_name,
                artifact_format,
                artifact_id=record.artifact_id,
            )
            try:
                self._assert_open_parent_is_current(record.relative_path, parent_fd)
            except ExperimentSpecError as exc:
                raise ExperimentIntegrityError(
                    "indexed artifact parent changed during verification",
                    details={"reason_code": "artifact_path_race_detected"},
                ) from exc
        self._require_measurement(record, actual)
        return manifest, payload

    def _stage_record(
        self,
        spec: ArtifactPublicationSpec,
        artifact_format: ArtifactFormat,
        parent_fd: int,
        temporary_name: str,
        write: Callable[[ArtifactFilePath], None],
    ) -> tuple[ArtifactRecord, _ArtifactMeasurement]:
        temporary_path = self._fd_entry(parent_fd, temporary_name)
        write(temporary_path)
        descriptor = _open_file(
            DirectoryEntryPath(parent_fd, temporary_name), SYNC_FLAGS
        )
        try:
            _fsync_entry(descriptor)
        finally:
            os.close(descriptor)
        staged = self._measurement_for(artifact_format)(temporary_path)
        manifest = ArtifactManifest.create(
            spec=spec,
            artifact_format=artifact_format,
            content_hash=staged.content_hash,
            schema_hash=staged.schema_hash,
            row_count=staged.row_count,
            byte_size=staged.byte_size,
        )
        return manifest.to_record(), staged

    def _ensure_publication_sidecar(
        self,
        parent_fd: int,
        target_name: str,
        record: ArtifactRecord,
    ) -> None:
        sidecar_name = _manifest_sidecar_name(target_name)
        sidecar_exists = self._entry_exists(parent_fd, sidecar_name)
        target_exists = self._entry_exists(parent_fd, target_name)
        if target_exists and not sidecar_exists:
            sidecar_exists = self._entry_exists(parent_fd, sidecar_name)
            if not sidecar_exists:
                _integrity(
                    "unindexed artifact lacks durable publication identity",
                    "artifact_sidecar_missing",
                    artifact_id=record.artifact_id,
                )
        if sidecar_exists:
            self._require_sidecar(
                parent_fd,
                target_name,
                record,
                conflict_on_mismatch=True,
            )
        else:
            self._publish_sidecar(parent_fd, target_name, record)

    def _guard_published_record(
        self,
        parent_fd: int,
        target_name: str,
        record: ArtifactRecord,
        artifact_format: ArtifactFormat,
    ) -> None:
        self._require_sidecar(
            parent_fd,
            target_name,
            record,
            conflict_on_mismatch=False,
        )
        guarded, _payload = self._measure_target(
            parent_fd,
            target_name,
            artifact_format,
            artifact_id=record.artifact_id,
        )
        self._require_measurement(record, guarded)
        self._assert_open_parent_is_current(record.relative_path, parent_fd)

    def _publish(
        self,
        spec: ArtifactPublicationSpec,
        *,
        artifact_format: ArtifactFormat,
        write: Callable[[ArtifactFilePath], None],
        lease_fence: LeaseFence,
        now_epoch_us: int,
    ) -> ArtifactRecord:
        existing = self._indexed_identity(spec)
        with self._open_parent(spec.relative_path, create=True) as (
            parent_fd,
            target_name,
        ):
            temporary_name = f".{target_name}.{secrets.token_hex(12)}.tmp"
            descriptor = _open_file(
                DirectoryEntryPath(parent_fd, temporary_name),
                _WRITE_FLAGS,
                0o600,
            )
            os.close(descriptor)
            try:
                record, staged = self._stage_record(
                    spec,
                    artifact_format,
                    parent_fd,
                    temporary_name,
                    write,
                )
                if existing is not None:
                    if _initial(existing) != record:
                        _conflict(
                            "artifact replay changed immutable payload",
                            "artifact_replay_drift",
                            artifact_id=spec.artifact_id,
                        )
                    self._verify_record(existing, artifact_format)
                    return existing
                self._ensure_publication_sidecar(parent_fd, target_name, record)
                self._assert_open_parent_is_current(spec.relative_path, parent_fd)
                _publish_no_clobber(
                    self._fd_entry(parent_fd, temporary_name),
                    self._fd_entry(parent_fd, target_name),
                )
                with suppress(FileNotFoundError):
                    _unlink_entry(DirectoryEntryPath(parent_fd, temporary_name))
                _fsync_entry(parent_fd)
                actual, _final_payload = self._measure_target(
                    parent_fd,
                    target_name,
                    artifact_format,
                    artifact_id=spec.artifact_id,
                )
                if actual != staged:
                    _conflict(
                        "immutable artifact target contains different bytes",
                        "immutable_artifact_conflict",
                        relative_path=spec.relative_path,
                    )

                def commit_guard() -> None:
                    self._guard_published_record(
                        parent_fd,
                        target_name,
                        record,
                        artifact_format,
                    )

                commit_guard()
                self._writer.add_artifact(
                    record,
                    lease_fence=lease_fence,
                    now_epoch_us=now_epoch_us,
                    commit_guard=commit_guard,
                )
                indexed = self._reader.get_artifact(spec.artifact_id)
                if indexed is None or _initial(indexed) != record:
                    _integrity(
                        "artifact index did not retain the published fact",
                        "artifact_index_commit_mismatch",
                        artifact_id=spec.artifact_id,
                    )
                self._verify_record(indexed, artifact_format)
                return indexed
            finally:
                with suppress(FileNotFoundError):
                    _unlink_entry(DirectoryEntryPath(parent_fd, temporary_name))

    def publish_json(
        self,
        spec: ArtifactPublicationSpec,
        data: Mapping[str, object],
        *,
        lease_fence: LeaseFence,
        now_epoch_us: int,
    ) -> ArtifactRecord:
        """Publish one canonical JSON object, then append its index fact."""
        payload = canonical_payload(data).json_bytes
        return self._publish(
            spec,
            artifact_format=ArtifactFormat.JSON,
            write=lambda path: _write_json_file(path, payload),
            lease_fence=lease_fence,
            now_epoch_us=now_epoch_us,
        )

    def publish_parquet(
        self,
        spec: ArtifactPublicationSpec,
        frame: pl.DataFrame,
        *,
        lease_fence: LeaseFence,
        now_epoch_us: int,
    ) -> ArtifactRecord:
        """Publish Parquet and derive schema/rows from its staged bytes."""
        return self._publish(
            spec,
            artifact_format=ArtifactFormat.PARQUET,
            write=lambda path: _write_parquet_file(path, frame),
            lease_fence=lease_fence,
            now_epoch_us=now_epoch_us,
        )

    def _require_indexed_record(self, artifact_id: str) -> ArtifactRecord:
        """Return one indexed artifact record or fail closed."""
        record = self._reader.get_artifact(artifact_id)
        if record is None:
            _integrity(
                "artifact is not indexed",
                "artifact_not_indexed",
                artifact_id=artifact_id,
            )
        return record

    def read_json(self, artifact_id: str) -> dict[str, object]:
        """Load a JSON artifact only after index and file verification."""
        record = self._require_indexed_record(artifact_id)
        _manifest, verified_bytes = self._verify_record(record, ArtifactFormat.JSON)
        return cast("dict[str, object]", orjson.loads(verified_bytes))

    def read_parquet(self, artifact_id: str) -> pl.DataFrame:
        """Load Parquet only after index and file verification."""
        record = self._require_indexed_record(artifact_id)
        _manifest, verified_bytes = self._verify_record(record, ArtifactFormat.PARQUET)
        return pl.read_parquet(BytesIO(verified_bytes))

    def read_indexed_artifact_bytes(self, artifact_id: str) -> bytes:
        """Load verified raw artifact bytes keyed by artifact_id."""
        record = self._require_indexed_record(artifact_id)
        manifest = ArtifactManifest.from_record(record)
        _manifest, payload = self._verify_record(record, manifest.artifact_format)
        return payload

    def pin(
        self,
        artifact_id: str,
        *,
        expected_revision: int,
        pinned_at: datetime,
    ) -> ArtifactRecord:
        """Verify immutable evidence before its one-way review pin CAS."""
        record = self._require_indexed_record(artifact_id)
        manifest = ArtifactManifest.from_record(record)
        with self._open_parent(
            record.relative_path,
            create=False,
            read_integrity=True,
        ) as (parent_fd, target_name):

            def commit_guard() -> None:
                self._guard_published_record(
                    parent_fd,
                    target_name,
                    record,
                    manifest.artifact_format,
                )

            commit_guard()
            pinned = self._writer.pin_artifact(
                artifact_id,
                expected_revision=expected_revision,
                pinned_at=pinned_at,
                commit_guard=commit_guard,
            )
        if _initial(pinned) != _initial(record):
            _integrity(
                "artifact pin changed immutable content",
                "artifact_pin_payload_drift",
                artifact_id=artifact_id,
            )
        self._verify_record(pinned, manifest.artifact_format)
        return pinned
