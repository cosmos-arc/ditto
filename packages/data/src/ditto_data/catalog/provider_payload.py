"""Content-addressed immutable provider payload artifacts."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Protocol, runtime_checkable
from uuid import uuid4

import orjson
import polars as pl
from ditto_platform.foundation import ChecksumCompute

from ditto_data.config.dataset_checksum import dataset_sort_keys

__all__ = [
    "FilesystemProviderPayloadStore",
    "ProviderPayloadArtifact",
    "ProviderPayloadReader",
    "ProviderPayloadWriter",
]

_IDENTITY_PATTERN = re.compile(r"[a-z0-9][a-z0-9_-]*")
_CHECKSUM_PATTERN = re.compile(r"[0-9a-f]{32}")
_PAYLOAD_ROOT = PurePosixPath("provider_payloads")


def _validate_identity(field: str, value: str) -> None:
    if _IDENTITY_PATTERN.fullmatch(value) is None:
        raise ValueError(f"invalid provider payload {field}: {value!r}")


def _schema_fingerprint(frame: pl.DataFrame) -> bytes:
    """Value checksums are dtype-blind; this pins the physical schema."""
    return orjson.dumps(
        {name: str(dtype) for name, dtype in frame.schema.items()},
        option=orjson.OPT_SORT_KEYS,
    )


@dataclass(frozen=True, slots=True)
class ProviderPayloadArtifact:
    """Identity and location of one immutable normalized provider response."""

    dataset_id: str
    source: str
    checksum: str
    row_count: int
    uri: str

    def __post_init__(self) -> None:
        """Reject identities that could alias or escape the content path."""
        _validate_identity("dataset_id", self.dataset_id)
        _validate_identity("source", self.source)
        if _CHECKSUM_PATTERN.fullmatch(self.checksum) is None:
            raise ValueError(f"invalid provider payload checksum: {self.checksum!r}")
        if self.row_count < 0:
            raise ValueError("provider payload row_count must be non-negative")
        expected_uri = (
            _PAYLOAD_ROOT / self.source / self.dataset_id / f"{self.checksum}.parquet"
        ).as_posix()
        if self.uri != expected_uri:
            raise ValueError("provider payload uri does not match its identity")


@runtime_checkable
class ProviderPayloadWriter(Protocol):
    """Retain normalized provider responses under immutable identities."""

    def retain_payload(
        self,
        *,
        dataset_id: str,
        source: str,
        payload: pl.DataFrame,
    ) -> ProviderPayloadArtifact:
        """Persist payload once and return its content-addressed identity."""
        ...


@runtime_checkable
class ProviderPayloadReader(Protocol):
    """Read and verify one exact provider payload artifact."""

    def read_payload(self, artifact: ProviderPayloadArtifact) -> pl.DataFrame:
        """Return the exact artifact or fail closed on absence or drift."""
        ...


class FilesystemProviderPayloadStore:
    """Parquet-backed provider payload store that never mutates an identity."""

    def __init__(self, data_root: Path) -> None:
        self._data_root = data_root.expanduser().resolve(strict=False)

    def retain_payload(
        self,
        *,
        dataset_id: str,
        source: str,
        payload: pl.DataFrame,
    ) -> ProviderPayloadArtifact:
        """Persist a normalized response by deterministic dataframe checksum."""
        _validate_identity("dataset_id", dataset_id)
        _validate_identity("source", source)
        checksum = ChecksumCompute.from_dataframe(
            payload,
            dataset_sort_keys(dataset_id),
        )
        artifact = ProviderPayloadArtifact(
            dataset_id=dataset_id,
            source=source,
            checksum=checksum,
            row_count=len(payload),
            uri=(
                _PAYLOAD_ROOT / source / dataset_id / f"{checksum}.parquet"
            ).as_posix(),
        )
        path = self._resolve_uri(artifact.uri)
        if path.exists():
            retained = self._read_parquet(path)
            self._verify_artifact(artifact, retained)
            # ponytail: value checksums are dtype-blind, so equal values with
            # different physical schemas must fail closed instead of aliasing
            # one artifact to two schema versions.
            if retained.schema != payload.schema:
                raise ValueError(
                    f"provider payload checksum collides across schemas: {artifact.uri}"
                )
            self._publish_fingerprint(path, payload)
            return artifact

        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            payload.write_parquet(temporary)
            self._verify_artifact(artifact, self._read_parquet(temporary))
            try:
                # A hard link publishes atomically: exactly one physical schema
                # can win a checksum path, and racing losers verify the winner.
                os.link(temporary, path)
            except FileExistsError:
                pass
            retained = self._read_parquet(path)
            self._verify_artifact(artifact, retained)
            if retained.schema != payload.schema:
                raise ValueError(
                    f"provider payload checksum collides across schemas: {artifact.uri}"
                )
        finally:
            temporary.unlink(missing_ok=True)
        self._publish_fingerprint(path, payload)
        return artifact

    def read_payload(self, artifact: ProviderPayloadArtifact) -> pl.DataFrame:
        """Read an immutable response and verify checksum, rows and schema."""
        path = self._resolve_uri(artifact.uri)
        frame = self._read_parquet(path)
        self._verify_artifact(artifact, frame)
        fingerprint = path.with_name(f"{path.name}.schema")
        if not fingerprint.exists():
            raise ValueError(
                f"provider payload schema fingerprint is missing: {artifact.uri}"
            )
        if fingerprint.read_bytes() != _schema_fingerprint(frame):
            raise ValueError(
                f"provider payload schema fingerprint mismatch: {artifact.uri}"
            )
        return frame

    @staticmethod
    def _publish_fingerprint(path: Path, frame: pl.DataFrame) -> None:
        """Persist the physical schema beside the artifact it describes."""
        fingerprint = path.with_name(f"{path.name}.schema")
        expected = _schema_fingerprint(frame)
        if fingerprint.exists():
            if fingerprint.read_bytes() != expected:
                raise ValueError(
                    f"provider payload schema fingerprint conflicts: {path.name}"
                )
            return
        temporary = path.with_name(f".{fingerprint.name}.{uuid4().hex}.tmp")
        temporary.write_bytes(expected)
        try:
            os.link(temporary, fingerprint)
        except FileExistsError:
            pass
        finally:
            temporary.unlink(missing_ok=True)

    def _resolve_uri(self, uri: str) -> Path:
        relative = PurePosixPath(uri)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("provider payload uri escapes data_root")
        path = (self._data_root / Path(*relative.parts)).resolve(strict=False)
        try:
            path.relative_to(self._data_root)
        except ValueError as error:
            raise ValueError("provider payload uri escapes data_root") from error
        return path

    @staticmethod
    def _read_parquet(path: Path) -> pl.DataFrame:
        try:
            return pl.read_parquet(path)
        except (OSError, pl.exceptions.PolarsError) as error:
            raise ValueError(
                "immutable provider payload is missing or unreadable"
            ) from error

    @staticmethod
    def _verify_artifact(
        artifact: ProviderPayloadArtifact,
        payload: pl.DataFrame,
    ) -> None:
        checksum = ChecksumCompute.from_dataframe(
            payload,
            dataset_sort_keys(artifact.dataset_id),
        )
        if checksum != artifact.checksum or len(payload) != artifact.row_count:
            raise ValueError("immutable provider payload checksum or row count drifted")
