"""Exit-held valuation notes stay evidenced, dated and non-liquidating."""

from datetime import date

import polars as pl
from ditto_application.builders.exit_valuation import exit_held_valuation_notes


def _roster(delist_date: str | None) -> list[dict[str, object]]:
    return [
        {
            "instrument_id": 1005603,
            "list_date": "1994-01-03",
            "delist_date": delist_date,
            "ticker": "000033",
            "exchange": "SZSE",
            "asset_class": "stock",
            "source_ticker": "000033.SZ",
            "effective_from": "2017-07-03",
            "effective_to": None,
        },
        {
            "instrument_id": 1007561,
            "list_date": "1991-01-01",
            "delist_date": None,
            "ticker": "000001",
            "exchange": "SZSE",
            "asset_class": "stock",
            "source_ticker": "000001.SZ",
            "effective_from": "2017-07-03",
            "effective_to": None,
        },
    ]


def _participation() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "instrument_id": [1005603, 1005603, 1005603, 1007561],
            "trade_date": [
                "2017-07-06",
                "2017-07-07",
                "2017-07-10",
                "2017-07-07",
            ],
            "status": ["eligible", "delisted", "delisted", "eligible"],
        }
    )


def _bars() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "instrument_id": [1005603, 1005603, 1005603, 1007561],
            "trade_date": [
                date(2017, 7, 3),
                date(2017, 7, 5),
                date(2017, 7, 6),
                date(2017, 7, 6),
            ],
            "close": [1.48, 1.63, 1.7, 10.0],
            "is_valuation_only": [False, False, False, False],
            "valuation_date": [
                date(2017, 7, 3),
                date(2017, 7, 5),
                date(2017, 7, 6),
                date(2017, 7, 6),
            ],
        }
    )


def test_delisted_days_carry_dated_non_liquidating_valuation_note():
    notes = exit_held_valuation_notes(_participation(), _roster("2017-07-07"), _bars())
    rows = {row["trade_date"]: row["_exit_note"] for row in notes.to_dicts()}
    assert set(rows) == {"2017-07-07", "2017-07-10"}
    for note in rows.values():
        assert "已退出上市 2017-07-07" in note
        assert "持仓保留" in note
        assert "估值锚定 2017-07-06 收盘 1.7 元" in note
        assert "无退市清算会计证据" in note
        assert "卖出" not in note


def test_exit_note_without_any_retained_quote_omits_the_anchor():
    notes = exit_held_valuation_notes(
        _participation(), _roster("2017-07-07"), _bars().clear()
    )
    assert notes.height == 2
    for row in notes.to_dicts():
        assert "估值锚定" not in row["_exit_note"]
        assert "已退出上市 2017-07-07" in row["_exit_note"]


def test_missing_exit_fact_rows_produce_no_notes():
    assert exit_held_valuation_notes(
        _participation(), _roster(None), _bars()
    ).is_empty()


def _etf_roster(delist_date: str | None) -> list[dict[str, object]]:
    return [
        {
            "instrument_id": 2009171,
            "list_date": "2012-04-06",
            "delist_date": delist_date,
            "ticker": "159917",
            "exchange": "SZSE",
            "asset_class": "etf",
            "source_ticker": "159917.SZ",
            "effective_from": "2015-08-01",
            "effective_to": None,
        }
    ]


def _etf_frames() -> tuple[pl.DataFrame, pl.DataFrame]:
    participation = pl.DataFrame(
        {
            "instrument_id": [2009171, 2009171, 2009171],
            "trade_date": ["2015-08-26", "2015-08-27", "2015-08-28"],
            "status": ["eligible", "delisted", "delisted"],
        }
    )
    # ETF execution bars carry no suspension-valuation columns: the anchor is
    # the last retained quote day itself (159917.SZ's real final session).
    bars = pl.DataFrame(
        {
            "instrument_id": [2009171, 2009171, 2009171],
            "trade_date": [
                date(2015, 8, 24),
                date(2015, 8, 25),
                date(2015, 8, 26),
            ],
            "close": [1.746, 1.615, 1.77],
        }
    )
    return participation, bars


def test_etf_terminated_days_carry_dated_non_liquidating_note():
    participation, bars = _etf_frames()
    notes = exit_held_valuation_notes(participation, _etf_roster("2015-08-27"), bars)
    rows = {row["trade_date"]: row["_exit_note"] for row in notes.to_dicts()}
    assert set(rows) == {"2015-08-27", "2015-08-28"}
    for note in rows.values():
        assert "已终止上市 2015-08-27" in note
        assert "持仓保留" in note
        assert "估值锚定 2015-08-26 收盘 1.77 元" in note
        assert "无终止上市清算会计证据" in note
        assert "清算款" not in note


def test_etf_exit_note_without_any_retained_quote_omits_the_anchor():
    participation, bars = _etf_frames()
    notes = exit_held_valuation_notes(
        participation, _etf_roster("2015-08-27"), bars.clear()
    )
    assert notes.height == 2
    for row in notes.to_dicts():
        assert "估值锚定" not in row["_exit_note"]
        assert "已终止上市 2015-08-27" in row["_exit_note"]


def test_valuation_only_anchor_reports_the_real_quote_date():
    suspended = (
        _bars()
        .with_columns(
            pl.col("is_valuation_only"),
            pl.col("valuation_date"),
        )
        .filter(pl.col("instrument_id") == 1005603)
    )
    carried = pl.concat(
        [
            suspended.head(2),
            suspended.tail(1).with_columns(
                pl.lit(True).alias("is_valuation_only"),
                pl.lit(date(2017, 7, 5)).alias("valuation_date"),
            ),
        ]
    )
    notes = exit_held_valuation_notes(_participation(), _roster("2017-07-07"), carried)
    assert notes.height == 2
    assert "估值锚定 2017-07-05 收盘 1.7 元" in notes["_exit_note"][0]
