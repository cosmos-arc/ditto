"""PIT-safe factor Parquet reader/writer contract tests."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl
import pytest
from ditto_features.errors import FeatureStorageError
from ditto_features.storage.parquet.factors.factor_reader import FactorReader
from ditto_features.storage.parquet.factors.factor_writer import FactorWriter
from ditto_platform.foundation import OnDuplicate


def _factor_frame(*, newer_exposure: float = 2.0) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "instrument_id": [1, 1, 2],
            "trade_date": ["2026-01-02", "2026-01-02", "2026-01-03"],
            "factor_id": ["momentum", "momentum", "value"],
            "factor_class": ["technical", "technical", "fundamental"],
            "factor_family": ["momentum", "momentum", "value"],
            "exposure": [1.0, newer_exposure, -0.5],
            "effective_from": ["2026-01-01", "2026-02-01", "2026-01-01"],
            "effective_to": ["2026-02-01", None, None],
        }
    )


def test_factor_writer_rejects_incomplete_storage_schema(tmp_path: Path) -> None:
    with pytest.raises(FeatureStorageError, match="Missing required columns"):
        FactorWriter(tmp_path).write(
            pl.DataFrame({"instrument_id": [1]}),
            2026,
        )


@pytest.mark.pit
def test_factor_reader_uses_half_open_visibility_and_latest_visible_version(
    tmp_path: Path,
) -> None:
    writer = FactorWriter(tmp_path)
    reader = FactorReader(tmp_path)

    assert reader.read().is_empty()
    result = writer.write(_factor_frame(), 2026)
    assert result.added == 3
    assert result.updated == 0
    assert result.is_merge is False

    before_revision = reader.read(
        instrument_ids=[1],
        start_date="2026-01-02",
        end_date="2026-01-02",
        as_of_date="2026-01-31",
        factor_ids=["momentum"],
    )
    at_revision = reader.read(
        instrument_ids=[1],
        as_of_date="2026-02-01",
        factor_ids=["momentum"],
    )

    assert before_revision["exposure"].to_list() == [1.0]
    assert before_revision["effective_to"].to_list() == [date(2026, 2, 1)]
    assert at_revision["exposure"].to_list() == [2.0]
    assert at_revision["effective_from"].to_list() == [date(2026, 2, 1)]


def test_factor_duplicate_policies_preserve_or_replace_exact_version(
    tmp_path: Path,
) -> None:
    writer = FactorWriter(tmp_path)
    reader = FactorReader(tmp_path)
    writer.write(_factor_frame(), 2026)
    duplicate = _factor_frame(newer_exposure=9.0).filter(
        pl.col("effective_from") == "2026-02-01"
    )

    with pytest.raises(FeatureStorageError, match="Duplicate data"):
        writer.write(duplicate, 2026)

    kept = writer.write(duplicate, 2026, OnDuplicate.KEEP_FIRST)
    assert kept.added == 0
    assert kept.updated == 0
    assert reader.read(instrument_ids=[1], as_of_date="2026-02-01")[
        "exposure"
    ].to_list() == [2.0]

    replaced = writer.write(duplicate, 2026, OnDuplicate.KEEP_LAST)
    assert replaced.added == 0
    assert replaced.updated == 1
    assert reader.read(instrument_ids=[1], as_of_date="2026-02-01")[
        "exposure"
    ].to_list() == [9.0]


def test_factor_reader_metadata_and_partition_lifecycle(tmp_path: Path) -> None:
    writer = FactorWriter(tmp_path)
    reader = FactorReader(tmp_path)
    writer.write(_factor_frame(), 2026)

    assert reader.get_years() == [2026]
    assert reader.get_checksum("2026")
    assert reader.count() == 3
    assert reader.count(instrument_ids=[2]) == 1
    assert reader.get_date_range() == ("2026-01-02", "2026-01-03")
    assert reader.list_instrument_ids() == [1, 2]
    assert writer.delete_partition("missing") is False
    assert writer.delete_partition("2026") is True
    assert reader.get_years() == []
