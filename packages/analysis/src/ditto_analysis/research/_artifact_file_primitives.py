"""Closed-file codecs and no-clobber primitives for indexed artifacts."""

from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import cast

import orjson
import polars as pl

from ditto_analysis.errors import ResearchDatasetError
from ditto_analysis.experiments.artifact_manifest import ArtifactFormat
from ditto_analysis.experiments.models import ContentHash
from ditto_analysis.experiments.persistence import canonical_payload

_READ_FLAGS = os.O_RDONLY | os.O_NOFOLLOW


@dataclass(frozen=True, slots=True)
class ArtifactMeasurement:
    """Measurements derived from the exact staged or verified bytes."""

    content_hash: ContentHash
    schema_hash: ContentHash
    row_count: int
    byte_size: int


def write_json_file(path: Path, payload: bytes) -> None:
    """Write canonical JSON bytes to an already-created safe path."""
    descriptor = os.open(path, os.O_WRONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()


def write_parquet_file(path: Path, frame: pl.DataFrame) -> None:
    """Write one frame to an already-created safe path."""
    descriptor = os.open(path, os.O_WRONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "wb") as stream:
        frame.write_parquet(stream)
        stream.flush()


def _json_shape(value: object) -> object:
    if isinstance(value, dict):
        mapping = cast("dict[str, object]", value)
        return {
            "type": "object",
            "properties": {
                key: _json_shape(mapping[key])
                for key in sorted(mapping, key=str.encode)
            },
        }
    if isinstance(value, list):
        items = cast("list[object]", value)
        encoded_shapes = {
            canonical_payload({"shape": _json_shape(item)}).json_bytes for item in items
        }
        return {
            "type": "array",
            "item_shapes": [
                orjson.loads(encoded)["shape"] for encoded in sorted(encoded_shapes)
            ],
        }
    value_type = type(value)
    if value_type is type(None):
        scalar_type = "null"
    elif value_type is bool:
        scalar_type = "boolean"
    elif value_type is int:
        scalar_type = "integer"
    elif value_type is float:
        scalar_type = "number"
    elif value_type is str:
        scalar_type = "string"
    else:
        scalar_type = None
    if scalar_type is not None:
        return {"type": scalar_type}
    raise TypeError(f"unsupported JSON value: {type(value).__name__}")


def measure_json_bytes(payload: bytes) -> ArtifactMeasurement:
    """Measure canonical JSON bytes and their structural schema."""
    decoded = orjson.loads(payload)
    if not isinstance(decoded, dict):
        raise ResearchDatasetError(
            "indexed JSON artifact must contain one top-level object",
            expected="object",
            actual=type(decoded).__name__,
        )
    decoded_mapping = cast("dict[str, object]", decoded)
    schema = canonical_payload(
        {
            "schema_version": 1,
            "format": ArtifactFormat.JSON.value,
            "shape": _json_shape(decoded_mapping),
        }
    )
    return ArtifactMeasurement(
        content_hash=ContentHash(hashlib.sha256(payload).hexdigest()),
        schema_hash=schema.content_hash,
        row_count=1,
        byte_size=len(payload),
    )


def measure_parquet_bytes(payload: bytes) -> ArtifactMeasurement:
    """Measure Parquet bytes and their ordered column schema."""
    frame = pl.read_parquet(BytesIO(payload))
    schema = canonical_payload(
        {
            "schema_version": 1,
            "format": ArtifactFormat.PARQUET.value,
            "columns": [
                {"name": name, "dtype": str(dtype)}
                for name, dtype in frame.schema.items()
            ],
        }
    )
    return ArtifactMeasurement(
        content_hash=ContentHash(hashlib.sha256(payload).hexdigest()),
        schema_hash=schema.content_hash,
        row_count=frame.height,
        byte_size=len(payload),
    )


def _read_path_bytes(path: Path) -> bytes:
    descriptor = os.open(path, _READ_FLAGS)
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise OSError("artifact is not a regular file")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            return stream.read()
    finally:
        os.close(descriptor)


def measure_json_artifact(path: Path) -> ArtifactMeasurement:
    """Measure one closed staged JSON file."""
    return measure_json_bytes(_read_path_bytes(path))


def measure_parquet_artifact(path: Path) -> ArtifactMeasurement:
    """Measure one closed staged Parquet file."""
    return measure_parquet_bytes(_read_path_bytes(path))


def publish_no_clobber(temporary: Path, target: Path) -> bool:
    """Atomically expose one inode without replacing an existing target."""
    try:
        os.link(temporary, target, follow_symlinks=False)
    except FileExistsError:
        return False
    return True
