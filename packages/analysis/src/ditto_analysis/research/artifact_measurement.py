"""Pure byte measurements for immutable indexed research artifacts."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from io import BytesIO
from typing import cast

import orjson
import polars as pl

from ditto_analysis.errors import ResearchDatasetError
from ditto_analysis.experiments.artifact_manifest import ArtifactFormat
from ditto_analysis.experiments.models import ContentHash
from ditto_analysis.experiments.persistence import canonical_payload

__all__ = [
    "ArtifactMeasurement",
    "measure_json_bytes",
    "measure_parquet_bytes",
]


@dataclass(frozen=True, slots=True)
class ArtifactMeasurement:
    """Measurements derived from exact canonical or columnar bytes."""

    content_hash: ContentHash
    schema_hash: ContentHash
    row_count: int
    byte_size: int


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
