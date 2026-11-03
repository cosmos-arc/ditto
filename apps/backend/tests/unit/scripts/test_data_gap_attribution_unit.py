"""data_gap_attribution 单元测试（#658 批次2）.

锁定 classify_gap_rows 的生命周期归因优先级与 _attribute_anomalies 的
结构归因输出（交易所分布/样本清单/名册缺口名单）。
"""

from __future__ import annotations

from datetime import date

import polars as pl
from ditto_apps.scripts.data_gap_attribution import (
    _attribute_anomalies,
    classify_gap_rows,
)


def _gap_rows() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "instrument_id": [1, 2, 3, 4, 5, 5],
            "trade_date": [
                date(2024, 3, 1),
                date(2024, 3, 1),
                date(2024, 3, 1),
                date(2024, 3, 1),
                date(2024, 3, 1),
                date(2024, 6, 1),
            ],
            "kind": ["status_trading_no_bar"] * 6,
        }
    )


def _bars() -> pl.DataFrame:
    # 1=沪市中段静默（前后有价）；2=从无行情；3=首价前缺口；4=末价后缺口；
    # 5=两段缺口（首价前+中段）。
    return pl.DataFrame(
        {
            "instrument_id": [1, 1, 3, 4, 4, 5, 5, 5],
            "trade_date": [
                date(2024, 1, 5),
                date(2024, 12, 20),
                date(2024, 4, 1),
                date(2024, 1, 5),
                date(2024, 2, 1),
                date(2024, 2, 1),
                date(2024, 4, 1),
                date(2024, 12, 1),
            ],
        }
    )


def _tickers() -> dict[int, str]:
    return {
        1: "600000.SH",
        2: "000001.SZ",
        3: "000002.SZ",
        4: "000003.SZ",
        5: "920001.BJ",
    }


class TestClassifyGapRows:
    def test_bucket_priority_lifecycle_attribution(self) -> None:
        classified = classify_gap_rows(_gap_rows(), tickers=_tickers(), bars=_bars())
        buckets = dict(
            zip(
                classified["instrument_id"].to_list(),
                classified["bucket"].to_list(),
                strict=True,
            )
        )
        # 920001.BJ 无论行情形态一律 BSE 范围外（含中段静默行）。
        assert buckets[1] == "silent_stretch"
        assert buckets[2] == "never_any_bar"
        assert buckets[3] == "head_before_first_bar"
        assert buckets[4] == "tail_after_last_bar"
        assert buckets[5] == "bse_out_of_scope"

    def test_empty_gap_detail_passes_through(self) -> None:
        empty = pl.DataFrame(
            schema={
                "instrument_id": pl.Int64,
                "trade_date": pl.Date,
                "kind": pl.String,
            }
        )
        classified = classify_gap_rows(empty, tickers={}, bars=_bars())
        assert classified.height == 0
        assert classified["bucket"].to_list() == []


class TestAttributeAnomalies:
    def test_bar_before_list_date_split_by_exchange(self) -> None:
        anomaly = pl.DataFrame(
            {
                "instrument_id": [5, 5, 1],
                "trade_date": [
                    date(2024, 3, 1),
                    date(2024, 3, 4),
                    date(2024, 3, 5),
                ],
                "kind": ["bar_before_list_date"] * 3,
            }
        )
        result = _attribute_anomalies(anomaly, tickers=_tickers(), roster=_roster())
        entry = result["bar_before_list_date"]
        assert entry["count"] == 3
        assert entry["by_exchange_suffix"] == {"BJ": 2, "SH": 1}

    def test_master_list_date_missing_lists_tickers(self) -> None:
        anomaly = pl.DataFrame(
            schema={
                "instrument_id": pl.Int64,
                "trade_date": pl.Date,
                "kind": pl.String,
            }
        )
        result = _attribute_anomalies(anomaly, tickers=_tickers(), roster=_roster())
        assert result["master_list_date_missing"] == {
            "count": 1,
            "tickers": ["688827.SH"],
        }


def _roster() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "instrument_id": [1, 2, 3, 4, 5, 6],
            "source_ticker": [
                "600000.SH",
                "000001.SZ",
                "000002.SZ",
                "000003.SZ",
                "920001.BJ",
                "688827.SH",
            ],
            "list_date": [
                date(2020, 1, 1),
                date(2020, 1, 1),
                date(2020, 1, 1),
                date(2020, 1, 1),
                date(2020, 1, 1),
                None,
            ],
        }
    )


class TestWindowEdgeAttribution:
    def test_pre_window_listing_head_gap_is_silent_stretch(self) -> None:
        """I3：窗口起点前已上市、首价在窗口内＝跨窗长停，归中段静默而非首价前."""
        gap = pl.DataFrame(
            {
                "instrument_id": [10, 11],
                "trade_date": [date(2024, 1, 5), date(2024, 1, 5)],
                "kind": ["no_status_dataset"] * 2,
            }
        )
        bars = pl.DataFrame(
            {
                "instrument_id": [10, 11],
                "trade_date": [date(2024, 3, 1), date(2024, 2, 1)],
            }
        )
        classified = classify_gap_rows(
            gap,
            tickers={10: "600010.SH", 11: "600011.SH"},
            bars=bars,
            list_dates={10: date(2020, 1, 1), 11: date(2024, 1, 20)},
            window_start=date(2024, 1, 1),
        )
        buckets = dict(
            zip(
                classified["instrument_id"].to_list(),
                classified["bucket"].to_list(),
                strict=True,
            )
        )
        # 10=窗口前上市（2020）→ 跨窗静默；11=窗口内上市（2024-01-20）→ 首价前。
        assert buckets[10] == "silent_stretch"
        assert buckets[11] == "head_before_first_bar"
