"""Ordinary membership reconstruction retains explicit daily exclusions."""

import polars as pl
import pytest
from ditto_backtest.participation import daily_participation


@pytest.mark.pit
def test_late_listing_trading_day_warmup_and_half_open_membership() -> None:
    days = ["2026-01-30", "2026-02-02", "2026-02-03", "2026-02-09", "2026-02-10"]
    roster = [
        {
            "instrument_id": 1,
            "effective_from": "2026-01-01",
            "effective_to": "2026-02-10",
            "list_date": "2020-01-01",
            "delist_date": None,
        },
        {
            "instrument_id": 2,
            "effective_from": "2026-01-01",
            "effective_to": None,
            "list_date": "2026-02-02",
            "delist_date": None,
        },
        {
            "instrument_id": 3,
            "effective_from": "2026-02-09",
            "effective_to": None,
            "list_date": "2020-01-01",
            "delist_date": None,
        },
    ]
    result = daily_participation(roster, days, warmup_days=2, knowledge_lag_days=0)
    late = result.filter(pl.col("instrument_id") == 2)
    assert late["warmup_available"].to_list() == [0, 0, 1, 2, 3]
    assert late["status"].to_list() == [
        "not_listed",
        "warmup",
        "warmup",
        "listing_rule_unavailable",
        "listing_rule_unavailable",
    ]
    assert late["requires_quote"].to_list() == [False, True, True, True, True]
    first = result.filter(pl.col("instrument_id") == 1)
    assert first["status"].to_list() == [
        "warmup",
        "warmup",
        "eligible",
        "eligible",
        "outside_universe",
    ]
    entrant = result.filter(pl.col("instrument_id") == 3)
    assert entrant["status"].to_list()[-3:] == [
        "outside_universe",
        "eligible",
        "eligible",
    ]
