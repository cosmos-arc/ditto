"""Unit tests for deterministic Tushare status composition."""

from __future__ import annotations

import polars as pl
from ditto_data.sources.tushare.processors import StatusMerger


def test_status_merger_collapses_multirow_inputs_before_join() -> None:
    merger = StatusMerger()
    universe = pl.DataFrame(
        {
            "ts_code": ["600000.SH", "000001.SZ"],
            "list_status": ["L", "L"],
        }
    )
    suspensions = pl.DataFrame(
        {
            "ts_code": ["600000.SH", "600000.SH"],
            "suspend_timing": ["13:00-15:00", "09:30-10:00"],
        }
    )
    st_rows = pl.DataFrame(
        {
            "ts_code": ["600000.SH", "600000.SH"],
            "name": ["ST Example", "*ST Example"],
        }
    )

    result = merger.merge_status_data(
        universe,
        suspensions,
        st_rows,
        "2024-03-29",
    )

    assert result.height == 2
    assert result["source_ticker"].n_unique() == 2
    row = result.filter(pl.col("source_ticker") == "600000.SH").row(
        0,
        named=True,
    )
    assert row["is_suspended"] is True
    assert row["suspend_timing"] == "09:30-10:00;13:00-15:00"
    assert row["is_st"] is True
    assert row["st_type"] == "*ST Example;ST Example"
