"""NAV disclosure uncertainty survives provider mapping, storage and reconciliation."""

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import polars as pl
import pytest
import yaml
from ditto_data.observability.metrics import register_metrics
from ditto_data.quality.engine import QualityEngine
from ditto_data.quality.spec import DatasetRules, DQSpec
from ditto_data.sources.tushare.adapters.etf import ETFTushareAdapter
from ditto_data.storage.market.etf.nav.nav_reader import EtfNavReader
from ditto_data.storage.market.etf.nav.nav_writer import EtfNavWriter
from ditto_platform.foundation import OnDuplicate, ParquetStore


@pytest.mark.parametrize(
    "disclosure", [None, "invalid", "missing", "20260930", "20261002"]
)
def test_nav_preserves_unknown_disclosure_and_remains_comparable(
    tmp_path: Path, disclosure: str | None
) -> None:
    register_metrics()
    raw = pl.DataFrame(
        {
            "ts_code": ["510300.SH", "510300.SH"],
            "nav_date": ["20260929", "20260930"],
            "ann_date": ["20260930", disclosure],
            "unit_nav": [4.4, 4.5],
            "acc_nav": [5.4, 5.5],
        }
    )
    if disclosure == "missing":
        raw = raw.drop("ann_date")
    adapter = ETFTushareAdapter.__new__(ETFTushareAdapter)
    adapter._client = MagicMock()
    adapter._client.query.return_value = raw
    frame = adapter.fetch_fund_nav(
        source_ticker="510300.SH", start_date="2026-09-29", end_date="2026-09-30"
    )
    frame = frame.with_columns(instrument_id=pl.lit(1, dtype=pl.Int64)).sort(
        "trade_date"
    )
    expected = (
        date(2026, 9, 30)
        if disclosure == "20260930"
        else date(2026, 10, 2)
        if disclosure == "20261002"
        else None
    )
    assert frame["knowledge_date"].dtype == pl.Date
    assert frame["knowledge_date"][1] == expected
    store = ParquetStore(
        tmp_path, key_columns=("instrument_id", "trade_date"), date_column="trade_date"
    )
    writer = EtfNavWriter(store)
    writer.write(frame, 2026)
    writer.write(frame, 2026, on_duplicate=OnDuplicate.VERIFY_IDENTICAL)
    stored = (
        EtfNavReader(store)
        .read(start_date="2026-09-29", end_date="2026-09-30")
        .sort("trade_date")
    )
    assert stored.equals(frame)
    root = next(
        parent
        for parent in Path(__file__).resolve().parents
        if (parent / "config/default/dq_rules").is_dir()
    )
    config = yaml.safe_load((root / "config/default/dq_rules/etf_nav.yml").read_text())
    engine = QualityEngine(DQSpec(datasets={"etf_nav": DatasetRules(**config)}))
    assert engine.check(stored, "etf_nav", context={"reference_values": {1}}).passed
    comparison = engine.compare_cross_source(
        stored, frame.drop("knowledge_date"), "etf_nav"
    )
    assert comparison.matched_count == 2
    assert comparison.diff_count == 0
