"""Complete synthetic inputs for ordinary catalog assembly tests."""

from datetime import date, timedelta
from unittest.mock import MagicMock

import polars as pl
from ditto_data.provider import BarQuery, InstrumentQuery
from ditto_data.services.metadata_service import MetadataService

LISTINGS = {
    2_000_001: {
        "ticker": "510300",
        "asset_class": "etf",
        "exchange": "SSE",
        "list_date": "2012-05-28",
        "delist_date": None,
    },
    2_000_002: {
        "ticker": "510500",
        "asset_class": "etf",
        "exchange": "SSE",
        "list_date": "2013-03-15",
        "delist_date": None,
    },
    1_000_001: {
        "ticker": "000001",
        "asset_class": "stock",
        "exchange": "SZSE",
        "list_date": "1991-04-03",
        "delist_date": None,
    },
    3_000_001: {
        "ticker": "000300",
        "asset_class": "index",
        "exchange": "SSE",
        "list_date": "2005-04-08",
        "delist_date": None,
    },
}
TICKERS = {
    iid: f"{row['ticker']}.{'SZ' if row['exchange'] == 'SZSE' else 'SH'}"
    for iid, row in LISTINGS.items()
}


def make_metadata(asset_class: str = "etf") -> MagicMock:
    metadata = MagicMock(spec=MetadataService)
    metadata.resolve_instrument_id.return_value = 3_000_001
    metadata.get_universe.return_value = [
        iid for iid, record in LISTINGS.items() if record["asset_class"] == asset_class
    ]
    metadata.instrument.get_instrument.side_effect = LISTINGS.get
    metadata.instrument.get_source_ticker.side_effect = lambda iid, *_: TICKERS.get(iid)
    metadata.universe.get_universe_detail.return_value = {
        "universe_id": "synthetic",
        "name": "Synthetic",
        "description": "Synthetic inputs",
        "source_ref": "synthetic:catalog",
    }
    return metadata


class CatalogProvider:
    def __init__(self) -> None:
        self.missing: set[tuple[int, str]] = set()
        self.suspended = False
        self.missing_before: str | None = None

    def get_schedule(self, start: str, end: str) -> pl.DataFrame:
        day, stop = date.fromisoformat(start), date.fromisoformat(end)
        days = []
        while day <= stop:
            if day.weekday() < 5:
                days.append(day.isoformat())
            day += timedelta(days=1)
        return pl.DataFrame({"trade_date": days}, schema={"trade_date": pl.String})

    def get_bars(self, query: BarQuery) -> pl.DataFrame:
        rows = []
        for iid, ticker in TICKERS.items():
            if ticker not in query.instruments:
                continue
            for day in self.get_schedule(query.start, query.end)["trade_date"]:
                if self.missing_before is not None and day < self.missing_before:
                    continue
                if (iid, "all") in self.missing or (iid, day) in self.missing:
                    continue
                rows.append(
                    {
                        "instrument_id": iid,
                        "trade_date": day,
                        "knowledge_date": day,
                        "open": 10.0,
                        "high": 10.0,
                        "low": 10.0,
                        "close": 10.0,
                        "pre_close": 10.0,
                        "volume": 10000.0,
                        "amount": 1000.0,
                        "adj_factor": 1.0,
                        "is_suspended": self.suspended,
                        "is_st": False,
                        "list_status": "L",
                        "limit_up": 11.0,
                        "limit_down": 9.0,
                        "source": "tushare",
                        "source_ticker": ticker,
                        "source_snapshot_id": f"synthetic:{iid}",
                    }
                )
        return pl.DataFrame(rows)

    def get_instruments(self, query: InstrumentQuery) -> pl.DataFrame:
        return pl.DataFrame()

    def get_factor(
        self,
        name: str,
        instruments: tuple[str, ...],
        start: str,
        end: str,
        asof: str | None = None,
    ) -> pl.DataFrame:
        return pl.DataFrame()
