"""Immutable provider payload artifact tests."""

from pathlib import Path

import polars as pl
import pytest
from ditto_data.catalog.provider_payload import FilesystemProviderPayloadStore


def _payload(*, include_future: bool = False) -> pl.DataFrame:
    rows = {
        "trade_date": ["2026-08-28"],
        "source_ticker": ["000001.SZ"],
        "close": [10.5],
    }
    if include_future:
        rows = {
            "trade_date": ["2026-08-28", "2026-08-31"],
            "source_ticker": ["000001.SZ", "000001.SZ"],
            "close": [10.5, 11.0],
        }
    return pl.DataFrame(rows)


@pytest.mark.unit
@pytest.mark.pit
def test_provider_payload_is_content_addressed_and_future_safe(
    tmp_path: Path,
) -> None:
    store = FilesystemProviderPayloadStore(tmp_path)
    original = store.retain_payload(
        dataset_id="stock_daily",
        source="tushare",
        payload=_payload(),
    )
    replay = store.retain_payload(
        dataset_id="stock_daily",
        source="tushare",
        payload=_payload(),
    )
    revised = store.retain_payload(
        dataset_id="stock_daily",
        source="tushare",
        payload=_payload(include_future=True),
    )

    assert replay == original
    assert revised.uri != original.uri
    assert revised.checksum != original.checksum
    assert store.read_payload(original).to_dicts() == _payload().to_dicts()
    assert (
        store.read_payload(revised).to_dicts()
        == _payload(include_future=True).to_dicts()
    )


@pytest.mark.unit
@pytest.mark.pit
def test_provider_payload_rejects_tampered_content(tmp_path: Path) -> None:
    store = FilesystemProviderPayloadStore(tmp_path)
    artifact = store.retain_payload(
        dataset_id="stock_daily",
        source="tushare",
        payload=_payload(),
    )
    (tmp_path / artifact.uri).write_bytes(b"not parquet")

    with pytest.raises(ValueError, match="immutable provider payload"):
        store.retain_payload(
            dataset_id="stock_daily",
            source="tushare",
            payload=_payload(),
        )


@pytest.mark.unit
def test_provider_payload_rejects_unsafe_identity(tmp_path: Path) -> None:
    store = FilesystemProviderPayloadStore(tmp_path)

    with pytest.raises(ValueError, match="dataset_id"):
        store.retain_payload(
            dataset_id="../stock_daily",
            source="tushare",
            payload=_payload(),
        )


@pytest.mark.unit
@pytest.mark.pit
def test_same_values_with_different_schema_cannot_reuse_artifact(
    tmp_path: Path,
) -> None:
    store = FilesystemProviderPayloadStore(tmp_path)
    int32 = pl.DataFrame(
        {"instrument_id": [1], "close": pl.Series("close", [10], pl.Int32)}
    )
    int64 = int32.cast({"close": pl.Int64})

    first = store.retain_payload(
        dataset_id="stock_daily", source="tushare", payload=int32
    )

    assert int64["close"].dtype != int32["close"].dtype
    assert int64["close"].to_list() == int32["close"].to_list()
    with pytest.raises(ValueError, match="collides across schemas"):
        store.retain_payload(dataset_id="stock_daily", source="tushare", payload=int64)
    assert store.read_payload(first).schema == int32.schema


@pytest.mark.unit
@pytest.mark.pit
def test_publishing_race_keeps_one_schema_per_checksum(tmp_path: Path) -> None:
    store = FilesystemProviderPayloadStore(tmp_path)
    int32 = pl.DataFrame(
        {"instrument_id": [1], "close": pl.Series("close", [10], pl.Int32)}
    )
    int64 = int32.cast({"close": pl.Int64})

    first = store.retain_payload(
        dataset_id="stock_daily", source="tushare", payload=int32
    )
    # The racer starts while nothing is published for this checksum yet.
    (tmp_path / first.uri).unlink()

    original_write = pl.DataFrame.write_parquet

    def delayed_write(frame, target, *args, **kwargs):
        original_write(frame, target, *args, **kwargs)
        if str(target).endswith(".tmp") and frame.schema == int64.schema:
            # The racing winner publishes its schema while the loser is
            # between its own temp write and publication.
            store.retain_payload(
                dataset_id="stock_daily", source="tushare", payload=int32
            )

    pl.DataFrame.write_parquet = delayed_write
    try:
        with pytest.raises(ValueError, match="collides across schemas"):
            store.retain_payload(
                dataset_id="stock_daily", source="tushare", payload=int64
            )
    finally:
        pl.DataFrame.write_parquet = original_write

    assert store.read_payload(first).schema == int32.schema


@pytest.mark.unit
@pytest.mark.pit
def test_read_refuses_swapped_physical_schema_and_missing_fingerprint(
    tmp_path: Path,
) -> None:
    store = FilesystemProviderPayloadStore(tmp_path)
    int32 = pl.DataFrame(
        {"instrument_id": [1], "close": pl.Series("close", [10], pl.Int32)}
    )
    artifact = store.retain_payload(
        dataset_id="stock_daily", source="tushare", payload=int32
    )
    path = tmp_path / artifact.uri

    # A crashed pre-guard racer could leave same-value, different-dtype bytes.
    int32.cast({"close": pl.Int64}).write_parquet(path)
    with pytest.raises(ValueError, match="fingerprint mismatch"):
        store.read_payload(artifact)

    int32.write_parquet(path)
    path.with_name(f"{path.name}.schema").unlink()
    with pytest.raises(ValueError, match="fingerprint is missing"):
        store.read_payload(artifact)

    retrained = store.retain_payload(
        dataset_id="stock_daily", source="tushare", payload=int32
    )
    assert store.read_payload(retrained).schema == int32.schema
