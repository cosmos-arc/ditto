"""materialize_stock_universe 记录构建逻辑单测."""

from __future__ import annotations

from datetime import date

import polars as pl
from ditto_apps.scripts.materialize_stock_universe import build_constituent_records


def _frame(rows: list[dict[str, object]]) -> pl.DataFrame:
    return pl.DataFrame(
        rows,
        schema={
            "instrument_id": pl.Int64,
            "ticker": pl.String,
            "asset_class": pl.String,
            "list_date": pl.Date,
            "delist_date": pl.Date,
            "source_ticker": pl.String,
        },
        strict=False,
    )


def test_builds_pit_intervals_from_registry_dates() -> None:
    frame = _frame(
        [
            {
                "instrument_id": 1,
                "ticker": "000001",
                "asset_class": "stock",
                "list_date": date(1991, 4, 3),
                "delist_date": None,
                "source_ticker": "000001.SZ",
            },
            {
                "instrument_id": 2,
                "ticker": "600001",
                "asset_class": "stock",
                "list_date": date(1990, 12, 19),
                "delist_date": date(2021, 1, 7),
                "source_ticker": None,
            },
        ],
    )

    records, skipped = build_constituent_records(frame)

    assert skipped == 0
    assert records == [
        {
            "instrument_id": 1,
            "effective_from": "1991-04-03",
            "effective_to": None,
            "source": "instrument_registry",
            "source_ticker": "000001.SZ",
        },
        {
            "instrument_id": 2,
            "effective_from": "1990-12-19",
            "effective_to": "2021-01-07",
            "source": "instrument_registry",
            "source_ticker": "600001",
        },
    ]


def test_skips_null_list_date_and_non_stock_rows() -> None:
    frame = _frame(
        [
            {
                "instrument_id": 3,
                "ticker": "000003",
                "asset_class": "stock",
                "list_date": None,
                "delist_date": None,
                "source_ticker": None,
            },
            {
                "instrument_id": 4,
                "ticker": "510300",
                "asset_class": "etf",
                "list_date": date(2012, 5, 28),
                "delist_date": None,
                "source_ticker": None,
            },
        ],
    )

    records, skipped = build_constituent_records(frame)

    assert records == []
    assert skipped == 1


def test_skips_placeholder_list_dates_before_market_open() -> None:
    """1970 占位上市日不可判真实上市时点, 不得进入历史成员区间."""
    frame = _frame(
        [
            {
                "instrument_id": 5,
                "ticker": "301716",
                "asset_class": "stock",
                "list_date": date(1970, 1, 1),
                "delist_date": None,
                "source_ticker": None,
            },
        ],
    )

    records, skipped = build_constituent_records(frame)

    assert records == []
    assert skipped == 1


def test_empty_frame_returns_empty() -> None:
    assert build_constituent_records(_frame([])) == ([], 0)


def test_string_list_dates_are_normalized() -> None:
    """sqlite 读取路径返回字符串日期, 归一后同样参与校验与区间构建."""
    frame = pl.DataFrame(
        [
            {
                "instrument_id": 6,
                "ticker": "301999",
                "asset_class": "stock",
                "list_date": "2000-01-10",
                "delist_date": None,
                "source_ticker": None,
            },
            {
                "instrument_id": 7,
                "ticker": "301998",
                "asset_class": "stock",
                "list_date": "1970-01-01",
                "delist_date": None,
                "source_ticker": None,
            },
        ],
        schema={
            "instrument_id": pl.Int64,
            "ticker": pl.String,
            "asset_class": pl.String,
            "list_date": pl.String,
            "delist_date": pl.String,
            "source_ticker": pl.String,
        },
    )

    records, skipped = build_constituent_records(frame)

    assert records == [
        {
            "instrument_id": 6,
            "effective_from": "2000-01-10",
            "effective_to": None,
            "source": "instrument_registry",
            "source_ticker": "301999",
        },
    ]
    assert skipped == 1
