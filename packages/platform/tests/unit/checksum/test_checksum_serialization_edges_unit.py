"""Object-column serialization edges for generic DataFrame checksums."""

from __future__ import annotations

import polars as pl
from ditto_platform.foundation.util.checksum import ChecksumCompute


class _StableObject:
    def __str__(self) -> str:
        return "stable-object"


def test_checksum_serializes_nested_dataframes_in_object_columns() -> None:
    nested = pl.DataFrame({"nested": [1]})
    frame = pl.DataFrame(
        {"value": pl.Series("value", [nested], dtype=pl.Object)},
    )

    assert len(ChecksumCompute.from_dataframe(frame)) == 32


def test_checksum_falls_back_to_string_for_other_object_values() -> None:
    frame = pl.DataFrame(
        {"value": pl.Series("value", [_StableObject()], dtype=pl.Object)},
    )

    assert len(ChecksumCompute.from_dataframe(frame)) == 32
