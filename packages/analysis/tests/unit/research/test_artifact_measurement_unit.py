"""Unit tests for public no-I/O indexed-artifact measurements."""

from __future__ import annotations

import hashlib
from io import BytesIO

import polars as pl
import pytest
from ditto_analysis.errors import ResearchDatasetError
from ditto_analysis.experiments.artifact_manifest import ArtifactFormat
from ditto_analysis.experiments.models import ContentHash
from ditto_analysis.experiments.persistence import canonical_payload
from ditto_analysis.research.artifact_measurement import (
    ArtifactMeasurement,
    measure_json_bytes,
    measure_parquet_bytes,
)


def test_json_measurement_binds_exact_bytes_and_structural_shape() -> None:
    payload = canonical_payload(
        {
            "flag": True,
            "items": [1, "one", 2],
            "name": "artifact",
        }
    ).json_bytes
    expected_schema = canonical_payload(
        {
            "schema_version": 1,
            "format": ArtifactFormat.JSON.value,
            "shape": {
                "type": "object",
                "properties": {
                    "flag": {"type": "boolean"},
                    "items": {
                        "type": "array",
                        "item_shapes": [
                            {"type": "integer"},
                            {"type": "string"},
                        ],
                    },
                    "name": {"type": "string"},
                },
            },
        }
    )

    measurement = measure_json_bytes(payload)

    assert type(measurement) is ArtifactMeasurement
    assert measurement.content_hash == ContentHash(hashlib.sha256(payload).hexdigest())
    assert measurement.schema_hash == expected_schema.content_hash
    assert measurement.row_count == 1
    assert measurement.byte_size == len(payload)


def test_json_measurement_rejects_non_object_payload() -> None:
    payload = canonical_payload({"items": [1, 2]}).json_bytes
    non_object = payload[payload.index(b"[") : -1]

    with pytest.raises(ResearchDatasetError):
        measure_json_bytes(non_object)


def test_parquet_measurement_preserves_ordered_schema_and_row_count() -> None:
    frame = pl.DataFrame(
        {
            "instrument_id": [1, 2],
            "symbol": ["000001.SZ", "600000.SH"],
        },
        schema={"instrument_id": pl.Int64, "symbol": pl.String},
    )
    stream = BytesIO()
    frame.write_parquet(stream)
    payload = stream.getvalue()
    expected_schema = canonical_payload(
        {
            "schema_version": 1,
            "format": ArtifactFormat.PARQUET.value,
            "columns": [
                {"name": "instrument_id", "dtype": "Int64"},
                {"name": "symbol", "dtype": "String"},
            ],
        }
    )

    measurement = measure_parquet_bytes(payload)

    assert type(measurement) is ArtifactMeasurement
    assert measurement.content_hash == ContentHash(hashlib.sha256(payload).hexdigest())
    assert measurement.schema_hash == expected_schema.content_hash
    assert measurement.row_count == frame.height
    assert measurement.byte_size == len(payload)
