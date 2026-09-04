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
