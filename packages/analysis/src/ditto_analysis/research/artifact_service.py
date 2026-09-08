"""Research artifact file I/O service."""

from __future__ import annotations

import hashlib
import os
import tempfile
from collections.abc import Callable, Mapping
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from typing import Literal, cast

import orjson
import polars as pl

from ditto_analysis.errors import (
    ExperimentConflictError,
    ExperimentIntegrityError,
    ExperimentSpecError,
    ResearchDatasetError,
)
from ditto_analysis.experiments.artifact_manifest import ArtifactPublicationSpec
from ditto_analysis.experiments.persistence import (
    ArtifactRecord,
    LeaseFence,
    validate_artifact_relative_path,
)
from ditto_analysis.research._artifact_file_primitives import (
    fsync_entry as _fsync_entry,
)
from ditto_analysis.research._artifact_file_primitives import (
    open_directory as _open_directory,
)
from ditto_analysis.research._indexed_artifacts import (
    ArtifactIndexReader,
    ArtifactIndexWriter,
    IndexedArtifactIO,
)

__all__ = ["ResearchArtifactService"]

_SHA256_HEX_LENGTH = 64

ExportFormat = Literal["parquet", "csv", "feather"]
_EXPORT_WRITERS: dict[ExportFormat, str] = {
    "parquet": "write_parquet",
    "csv": "write_csv",
    "feather": "write_ipc",
}


class ResearchArtifactService:
    """Encapsulates analysis-owned research artifact file I/O."""

    def __init__(
        self,
        *,
        artifact_root: Path,
        indexed_artifact_root: Path | None = None,
        artifact_reader: ArtifactIndexReader | None = None,
        artifact_writer: ArtifactIndexWriter | None = None,
    ) -> None:
        self._root = Path(artifact_root).resolve()
        if (
            indexed_artifact_root is not None
            and artifact_reader is None
            and artifact_writer is None
        ):
            raise ExperimentSpecError(
                "an indexed artifact root requires both index ports",
                details={"reason_code": "artifact_index_port_incomplete"},
            )
        configured_indexed_root = (
            self._root
            if indexed_artifact_root is None
            else Path(indexed_artifact_root).resolve()
        )
        self._indexed_root = (
            None
            if artifact_reader is None and artifact_writer is None
            else configured_indexed_root
        )
        self._indexed = (
            None
            if artifact_reader is None and artifact_writer is None
            else IndexedArtifactIO(
                artifact_root=configured_indexed_root,
                reader=artifact_reader,
                writer=artifact_writer,
            )
        )

    @property
    def artifact_root(self) -> Path:
        """Return the legacy data-product artifact namespace."""
        return self._root

    @property
    def indexed_artifact_root(self) -> Path | None:
        """Return the reserved R3 evidence namespace when configured."""
        return self._indexed_root

    def _require_indexed(self) -> IndexedArtifactIO:
        if self._indexed is None:
            raise ExperimentSpecError(
                "indexed artifact operation requires an experiment artifact index",
                details={"reason_code": "artifact_index_not_configured"},
            )
        return self._indexed

    def _path(self, relative_path: str) -> Path:
        canonical = validate_artifact_relative_path(relative_path)
        path = (self._root / Path(*canonical.parts)).resolve()
        if not path.is_relative_to(self._root):
            raise ExperimentSpecError(
                "artifact path escapes its resolved canonical root",
                details={"reason_code": "invalid_artifact_relative_path"},
            )
        if self._indexed_root is not None and (
            path == self._indexed_root or path.is_relative_to(self._indexed_root)
        ):
            raise ExperimentSpecError(
                "indexed evidence requires identity-based verified APIs",
                details={"reason_code": "indexed_artifact_requires_verified_api"},
            )
        return path

    def _atomic_write(
        self,
        relative_path: str,
        write: Callable[[Path], object],
    ) -> None:
        target = self._path(relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{target.name}.",
            suffix=".tmp",
            dir=target.parent,
        )
        os.close(descriptor)
        temporary = Path(temporary_name)
        try:
            write(temporary)
            with temporary.open("r+b") as stream:
                os.fsync(stream.fileno())
            temporary.replace(target)
        finally:
            with suppress(FileNotFoundError):
                temporary.unlink()

    def publish_immutable_artifact(
        self,
        relative_path: str,
        payload: bytes,
    ) -> str:
        """
        Publish final evidence bytes once, returning their SHA-256 digest.

        Unlike the generic ``write_*`` methods, this operation never replaces an
        existing target. Replaying identical bytes is a no-op; any other replay is
        a typed persistence conflict.
        """
        target = self._path(relative_path)
        incoming_sha256 = hashlib.sha256(payload).hexdigest()
        try:
            existing = target.read_bytes()
        except FileNotFoundError:
            pass
        else:
            digest = self._validate_immutable_replay(
                relative_path=relative_path,
                existing=existing,
                incoming=payload,
                incoming_sha256=incoming_sha256,
            )
            self._fsync_parent_directory(target)
            return digest

        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{target.name}.",
            suffix=".tmp",
            dir=target.parent,
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                descriptor = -1
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, target)
            except FileExistsError:
                existing = target.read_bytes()
                digest = self._validate_immutable_replay(
                    relative_path=relative_path,
                    existing=existing,
                    incoming=payload,
                    incoming_sha256=incoming_sha256,
                )
                self._fsync_parent_directory(target)
                return digest
            self._fsync_parent_directory(target)
            return incoming_sha256
        finally:
            if descriptor >= 0:
                with suppress(OSError):
                    os.close(descriptor)
            with suppress(FileNotFoundError):
                temporary.unlink()

    def publish_frozen_research_input(
        self,
        artifact_id: str,
        payload: bytes,
    ) -> str:
        """Publish planning input bytes before an experiment row exists."""
        identity_path, payload_path = self._frozen_research_input_paths(artifact_id)
        content_hash = hashlib.sha256(payload).hexdigest()
        identity = orjson.dumps(
            {
                "artifact_id": artifact_id,
                "content_hash": content_hash,
                "schema": "ditto.frozen-research-input.v1",
            },
            option=orjson.OPT_SORT_KEYS,
        )
        self.publish_immutable_artifact(payload_path, payload)
        self.publish_immutable_artifact(identity_path, identity)
        return content_hash

    def read_frozen_research_input_bytes(self, artifact_id: str) -> bytes:
        """Read and verify one pre-experiment immutable planning input."""
        identity_path, payload_path = self._frozen_research_input_paths(artifact_id)
        try:
            identity_target = self._path(identity_path)
        except ExperimentSpecError as error:
            if error.details.get("reason_code") != (
                "indexed_artifact_requires_verified_api"
            ):
                raise
            return self.read_indexed_artifact_bytes(artifact_id)
        try:
            identity_bytes = identity_target.read_bytes()
        except FileNotFoundError:
            # Existing experiment-backed fixtures and already-published evidence
            # remain readable while new planning inputs use the independent
            # namespace above.
            return self.read_indexed_artifact_bytes(artifact_id)
        try:
            identity = orjson.loads(identity_bytes)
        except orjson.JSONDecodeError as error:
            raise self._frozen_research_input_integrity_error(
                artifact_id,
                reason="invalid_identity_json",
            ) from error
        if type(identity) is not dict:
            raise self._frozen_research_input_integrity_error(
                artifact_id,
                reason="invalid_identity",
            )
        typed_identity = cast("dict[str, object]", identity)
        content_hash = typed_identity.get("content_hash")
        if (
            set(typed_identity) != {"artifact_id", "content_hash", "schema"}
            or typed_identity.get("artifact_id") != artifact_id
            or typed_identity.get("schema") != "ditto.frozen-research-input.v1"
            or type(content_hash) is not str
            or len(content_hash) != _SHA256_HEX_LENGTH
        ):
            raise self._frozen_research_input_integrity_error(
                artifact_id,
                reason="invalid_identity",
            )
        try:
            payload = self._path(payload_path).read_bytes()
        except FileNotFoundError as error:
            raise self._frozen_research_input_integrity_error(
                artifact_id,
                reason="payload_missing",
            ) from error
        actual_hash = hashlib.sha256(payload).hexdigest()
        if actual_hash != content_hash:
            raise self._frozen_research_input_integrity_error(
                artifact_id,
                reason="content_hash_mismatch",
                expected_content_hash=content_hash,
                actual_content_hash=actual_hash,
            )
        return payload

    @staticmethod
    def _frozen_research_input_integrity_error(
        artifact_id: str,
        *,
        reason: str,
        **details: object,
    ) -> ExperimentIntegrityError:
        return ExperimentIntegrityError(
            "frozen research input evidence is inconsistent",
            details={
                "reason_code": "frozen_research_input_integrity_mismatch",
                "reason": reason,
                "artifact_id": artifact_id,
                **details,
            },
        )

    @staticmethod
    def _frozen_research_input_paths(artifact_id: str) -> tuple[str, str]:
        if type(artifact_id) is not str or not artifact_id:
            raise ExperimentSpecError(
                "frozen research input artifact_id is required",
                details={"reason_code": "invalid_frozen_research_input_id"},
            )
        identity_key = hashlib.sha256(artifact_id.encode()).hexdigest()
        root = f"frozen-research-inputs/v1/{identity_key}"
        return f"{root}/identity.json", f"{root}/payload.bin"

    def publish_indexed_json(
        self,
        spec: ArtifactPublicationSpec,
        data: Mapping[str, object],
        *,
        lease_fence: LeaseFence,
        now_epoch_us: int,
    ) -> ArtifactRecord:
        """Publish immutable JSON and append its Schema v1 index fact."""
        return self._require_indexed().publish_json(
            spec,
            data,
            lease_fence=lease_fence,
            now_epoch_us=now_epoch_us,
        )

    def publish_indexed_parquet(
        self,
        spec: ArtifactPublicationSpec,
        frame: pl.DataFrame,
        *,
        lease_fence: LeaseFence,
        now_epoch_us: int,
    ) -> ArtifactRecord:
        """Publish immutable Parquet and append measured index metadata."""
        return self._require_indexed().publish_parquet(
            spec,
            frame,
            lease_fence=lease_fence,
            now_epoch_us=now_epoch_us,
        )

    def read_indexed_json(self, artifact_id: str) -> dict[str, object]:
        """Read only an indexed JSON artifact after full verification."""
        return self._require_indexed().read_json(artifact_id)

    def read_indexed_artifact_bytes(self, artifact_id: str) -> bytes:
        """Load verified raw artifact bytes keyed by artifact_id."""
        return self._require_indexed().read_indexed_artifact_bytes(artifact_id)

    def read_indexed_parquet(self, artifact_id: str) -> pl.DataFrame:
        """Read only indexed Parquet after full verification."""
        return self._require_indexed().read_parquet(artifact_id)

    def pin_indexed_artifact(
        self,
        artifact_id: str,
        *,
        expected_revision: int,
        pinned_at: datetime,
    ) -> ArtifactRecord:
        """Verify file evidence, then perform the one-way index pin CAS."""
        return self._require_indexed().pin(
            artifact_id,
            expected_revision=expected_revision,
            pinned_at=pinned_at,
        )

    @staticmethod
    def _fsync_parent_directory(target: Path) -> None:
        directory_descriptor = _open_directory(target.parent, durable=True)
        try:
            _fsync_entry(directory_descriptor)
        finally:
            os.close(directory_descriptor)

    @staticmethod
    def _validate_immutable_replay(
        *,
        relative_path: str,
        existing: bytes,
        incoming: bytes,
        incoming_sha256: str,
    ) -> str:
        existing_sha256 = hashlib.sha256(existing).hexdigest()
        if existing_sha256 == incoming_sha256 and existing == incoming:
            return incoming_sha256
        raise ExperimentConflictError(
            "immutable artifact already exists with different content",
            details={
                "reason_code": "immutable_artifact_conflict",
                "relative_path": relative_path,
                "existing_sha256": existing_sha256,
                "incoming_sha256": incoming_sha256,
            },
        )

    # -- Parquet --

    def read_parquet(self, relative_path: str) -> pl.DataFrame:
        """Read a parquet file by its relative path from artifact_root."""
        path = self._path(relative_path)
        if not path.exists():
            raise FileNotFoundError(f"research parquet not found: {relative_path}")
        return pl.read_parquet(path)

    def write_parquet(
        self,
        relative_path: str,
        frame: pl.DataFrame,
    ) -> None:
        """Write a parquet file, creating parent directories as needed."""
        self._atomic_write(relative_path, frame.write_parquet)

    # -- Multi-format export --

    def export_dataset(
        self,
        relative_path: str,
        frame: pl.DataFrame,
        *,
        fmt: ExportFormat = "parquet",
    ) -> None:
        """
        Export a DataFrame in the specified format.

        Creates parent directories as needed. Supported formats: parquet, csv, feather.
        """
        writer_name = _EXPORT_WRITERS.get(fmt)
        if writer_name is None:
            supported = ", ".join(_EXPORT_WRITERS)
            raise ResearchDatasetError(
                f"unsupported format: {fmt!r}. Expected one of: {supported}",
                relative_path=relative_path,
                format=fmt,
                supported=tuple(_EXPORT_WRITERS),
                supported_formats=tuple(_EXPORT_WRITERS),
            )
        writer = cast("Callable[[Path], object]", getattr(frame, writer_name))
        self._atomic_write(relative_path, writer)

    # -- JSON --

    def read_json(self, relative_path: str) -> dict[str, object]:
        """Read a JSON file by its relative path from artifact_root."""
        path = self._path(relative_path)
        if not path.exists():
            raise FileNotFoundError(f"research JSON not found: {relative_path}")
        payload = orjson.loads(path.read_bytes())
        if not isinstance(payload, dict):
            raise ResearchDatasetError(
                f"expected JSON object at {relative_path}",
                relative_path=relative_path,
                expected="object",
                actual=type(payload).__name__,
            )
        return cast(dict[str, object], payload)

    def write_json(
        self,
        relative_path: str,
        data: Mapping[str, object],
    ) -> None:
        """Write a JSON file with sorted keys, creating parent directories."""
        payload = orjson.dumps(
            data,
            option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS,
        )
        self._atomic_write(relative_path, lambda path: path.write_bytes(payload))

    # -- Artifact resolution --

    def resolve_artifact_relative_path(
        self,
        derived_id: str,
        version: int,
    ) -> str | None:
        """Resolve artifact relative path for a derived/version pair."""
        artifact_root = self._root / "derived" / "artifacts"
        matches = sorted(artifact_root.glob(f"*/{derived_id}/v{version}"))
        if matches:
            resolved = matches[0].resolve()
            if resolved.is_relative_to(self._root):
                relative_path = resolved.relative_to(self._root).as_posix()
                self._path(relative_path)
                return relative_path
        return None

    def read_source_snapshot_ids(
        self,
        artifact_relative_path: str,
    ) -> tuple[str, ...]:
        """Read source snapshot IDs from the latest artifact metadata."""
        version_root = self._path(artifact_relative_path)
        runs_root = version_root / "_runs"
        if not runs_root.exists():
            return ()
        metadata_paths = tuple(runs_root.glob("*/artifact_metadata.json"))
        if not metadata_paths:
            return ()
        latest_metadata = max(
            metadata_paths,
            key=lambda p: p.stat().st_mtime_ns,
        )
        payload = orjson.loads(latest_metadata.read_bytes())
        raw_snapshots = payload.get("input_snapshots", [])
        if not isinstance(raw_snapshots, list):
            return ()
        ids: list[str] = []
        for item in cast(list[object], raw_snapshots):
            if isinstance(item, str) and item:
                ids.append(item)
        return tuple(sorted(set(ids)))
