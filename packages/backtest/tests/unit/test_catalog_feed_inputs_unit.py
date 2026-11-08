"""Frozen ordinary pools cannot shrink to available rows."""

from datetime import date

import polars as pl
import pytest
from ditto_backtest.data_feed import (
    FeedInputRequirements,
    ProviderBackedDataFeed,
    SnapshotProviders,
)
from ditto_data.provider import BarQuery
from ditto_kernel.identity import InstrumentId
from packages.backtest.tests.unit.test_provider_data_feed_unit import _StubProvider

DATES = ["2026-10-08", "2026-10-09", "2026-10-12", "2026-10-13"]


class _Provider(_StubProvider):
    def get_bars(self, query: BarQuery) -> pl.DataFrame:
        ids = (
            [3_000_001]
            if query.instruments == ("000300.SH",)
            else [2_000_001, 2_000_002]
        )
        return self._bars_df.filter(pl.col("instrument_id").is_in(ids))


def _feed(missing: tuple[int, str] | None = None) -> ProviderBackedDataFeed:
    rows = [
        {
            "instrument_id": iid,
            "trade_date": day,
            "close": 4.0,
            "open": 4.0,
            "high": 4.0,
            "low": 4.0,
            "volume": 1000.0,
            "knowledge_date": date.fromisoformat(day),
            "source_snapshot_id": f"snapshot:{iid}",
        }
        for iid in [2_000_001, 2_000_002, 3_000_001]
        for day in DATES
        if missing not in {(iid, day), (iid, "all")}
    ]
    return ProviderBackedDataFeed(
        _Provider(pl.DataFrame(rows), pl.DataFrame({"trade_date": DATES})),
        tickers=("510300.SH", "510500.SH"),
        start_date=DATES[0],
        end_date=DATES[-1],
        id_map={
            "510300.SH": InstrumentId(2_000_001),
            "510500.SH": InstrumentId(2_000_002),
        },
        benchmark_id=InstrumentId(3_000_001),
        snapshot_providers=SnapshotProviders(
            requirements=FeedInputRequirements(
                start_date=DATES[2], warmup_days=2, benchmark_ticker="000300.SH"
            )
        ),
    )


@pytest.mark.parametrize(
    "missing", [(2_000_002, "all"), (2_000_001, DATES[0]), (3_000_001, DATES[-1])]
)
def test_catalog_feed_rejects_missing_member_warmup_or_benchmark(missing) -> None:
    with pytest.raises(ValueError, match=str(missing[0])):
        _feed(missing).validate_inputs()


def test_catalog_feed_loads_benchmark_separately_without_trading_it() -> None:
    feed = _feed()
    feed.validate_inputs()
    slice_ = feed.get_slice(DATES[2])
    assert slice_.benchmark_close == 4.0
    assert set(slice_.bars) == {2_000_001, 2_000_002}
