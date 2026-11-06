"""NAV disclosure uncertainty survives provider mapping, storage and reconciliation."""

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import polars as pl
import pytest
import yaml
from ditto_data.config.data_store import DataStoreSettings
from ditto_data.di.market import MarketProvider
from ditto_data.observability.metrics import register_metrics
from ditto_data.quality.engine import QualityEngine
from ditto_data.quality.spec import DatasetRules, DQSpec
from ditto_data.services.market_service import MarketService
from ditto_data.sources.tushare.adapters.etf import ETFTushareAdapter
from ditto_data.storage.market.etf.nav.nav_reader import EtfNavReader
from ditto_data.storage.market.etf.nav.nav_writer import EtfNavWriter
from ditto_platform.foundation import FileLockManager, OnDuplicate, ParquetStore


def _quality_engine() -> QualityEngine:
    root = next(
        parent
        for parent in Path(__file__).resolve().parents
        if (parent / "config/default/dq_rules").is_dir()
    )
    config = yaml.safe_load((root / "config/default/dq_rules/etf_nav.yml").read_text())
    return QualityEngine(DQSpec(datasets={"etf_nav": DatasetRules(**config)}))


@pytest.mark.pit
@pytest.mark.parametrize("earlier_disclosure", [None, date(2026, 10, 31)])
def test_nav_disclosure_revision_is_retained_and_displayed_once(
    tmp_path: Path, earlier_disclosure: date | None
) -> None:
    register_metrics()
    settings = DataStoreSettings(data_root=tmp_path)
    provider = MarketProvider()
    readers = provider.market_readers(settings, MagicMock())
    writer = provider.market_writers(
        settings, FileLockManager(tmp_path / "locks")
    ).etf_nav
    assert writer is not None
    original = pl.DataFrame(
        {
            "instrument_id": [2_000_001],
            "source_ticker": ["159509.SZ"],
            "trade_date": [date(2026, 10, 30)],
            "knowledge_date": [earlier_disclosure],
            "unit_nav": [2.1365],
            "acc_nav": [None],
        },
        schema_overrides={"knowledge_date": pl.Date, "acc_nav": pl.Float64},
    )
    writer.write(original, 2026)
    assert writer.write(original, 2026, OnDuplicate.VERIFY_IDENTICAL).added == 0
    with pytest.raises(ValueError, match="changed values"):
        writer.write(
            original.with_columns(unit_nav=pl.lit(999.0)),
            2026,
            OnDuplicate.VERIFY_IDENTICAL,
        )
    revision = original.with_columns(
        knowledge_date=pl.lit(date(2026, 11, 2)), unit_nav=pl.lit(2.2)
    )
    assert writer.write(revision, 2026, OnDuplicate.VERIFY_IDENTICAL).added == 1
    assert writer.write(revision, 2026, OnDuplicate.VERIFY_IDENTICAL).added == 0
    assert readers.etf_nav is not None
    retained = readers.etf_nav.read().sort("knowledge_date", nulls_last=False)
    assert retained["knowledge_date"].to_list() == [
        earlier_disclosure,
        date(2026, 11, 2),
    ]
    assert retained["unit_nav"].to_list() == [2.1365, 2.2]
    assert _quality_engine().check(retained, "etf_nav").passed
    before_disclosure = readers.etf_nav.read(
        filters=pl.col("knowledge_date") <= date(2026, 11, 1)
    )
    assert before_disclosure["unit_nav"].to_list() == (
        [] if earlier_disclosure is None else [2.1365]
    )
    displayed = MarketService(readers).get_etf_nav("2026-10-30", "2026-10-30")
    assert displayed["unit_nav"].to_list() == [2.2]
    with pytest.raises(ValueError, match="changed values"):
        writer.write(
            revision.with_columns(unit_nav=pl.lit(999.0)),
            2026,
            OnDuplicate.VERIFY_IDENTICAL,
        )
    assert readers.etf_nav.read().height == 2


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
            "accum_nav": [5.4, 5.5],
        }
    )
    if disclosure == "missing":
        raw = raw.drop("ann_date")
    client = MagicMock()
    client.query.return_value = raw
    adapter = ETFTushareAdapter(_client=client)
    # 预热 universe 缓存：#513 起 fund_nav 按标的路径先过 ETF universe 边界
    adapter._etf_universe = frozenset({"510300.SH"})
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
    assert frame["acc_nav"].to_list() == [5.4, 5.5]
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
    engine = _quality_engine()
    assert engine.check(stored, "etf_nav", context={"reference_values": {1}}).passed
    comparison = engine.compare_cross_source(
        stored, frame.drop("knowledge_date"), "etf_nav"
    )
    assert comparison.matched_count == 2
    assert comparison.diff_count == 0
