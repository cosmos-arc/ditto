"""复权因子跨源对账推导单测（#438）.

研究验收（docs/research/2026-10-04-fuyao-fred-second-review.md §4）：
复合除权例、基期不同但相对变化相同例、缺前价/缺配股价例；
推导不得对不可推导样本伪造数值，不得比较绝对因子。
"""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest
from ditto_data.quality.checkers.adjustment_events import (
    derive_event_adjustment_ratios,
    derive_factor_ratios,
)

_D = date(2025, 6, 25)
_D_PREV = date(2025, 6, 24)


def _factors(
    rows: list[tuple[int, date, float]],
) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "instrument_id": [r[0] for r in rows],
            "trade_date": [r[1] for r in rows],
            "adj_factor": [r[2] for r in rows],
        },
        schema={
            "instrument_id": pl.Int64,
            "trade_date": pl.Date,
            "adj_factor": pl.Float64,
        },
    )


def _events(
    rows: list[tuple[int, float | None, float | None, float | None, float | None]],
) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "instrument_id": [r[0] for r in rows],
            "trade_date": [_D] * len(rows),
            "dividend_per_share": [r[1] for r in rows],
            "per_share_bonus": [r[2] for r in rows],
            "allotment_ratio": [r[3] for r in rows],
            "allotment_price": [r[4] for r in rows],
        },
        schema={
            "instrument_id": pl.Int64,
            "trade_date": pl.Date,
            "dividend_per_share": pl.Float64,
            "per_share_bonus": pl.Float64,
            "allotment_ratio": pl.Float64,
            "allotment_price": pl.Float64,
        },
    )


def _closes(rows: list[tuple[int, float]]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "instrument_id": [r[0] for r in rows],
            "prev_close": [r[1] for r in rows],
        },
        schema={"instrument_id": pl.Int64, "prev_close": pl.Float64},
    )


@pytest.mark.unit
class TestDeriveFactorRatios:
    """主源累积因子 → 当日相对前值比例（仅变化行）."""

    def test_changed_factor_ratio(self) -> None:
        window = _factors([(1, _D_PREV, 10.0), (1, _D, 11.0)])

        ratios = derive_factor_ratios(window, _D)

        assert ratios.height == 1
        assert ratios["adjustment_ratio"][0] == pytest.approx(1.1)

    def test_unchanged_factor_excluded(self) -> None:
        window = _factors([(1, _D_PREV, 10.0), (1, _D, 10.0)])

        assert derive_factor_ratios(window, _D).is_empty()

    def test_no_prior_factor_excluded(self) -> None:
        # 目标日才入库（新上市等）：无前值不产生比例行
        window = _factors([(1, _D, 10.0)])

        assert derive_factor_ratios(window, _D).is_empty()

    def test_different_bases_same_relative_change(self) -> None:
        # 基期不同但相对变化相同：绝对因子不可比，比例可比
        window = _factors(
            [
                (1, _D_PREV, 10.0),
                (1, _D, 11.0),
                (2, _D_PREV, 2.0),
                (2, _D, 2.2),
            ]
        )

        ratios = derive_factor_ratios(window, _D)

        assert ratios["adjustment_ratio"].to_list() == pytest.approx([1.1, 1.1])

    def test_string_trade_date_accepted(self) -> None:
        window = _factors([(1, _D_PREV, 10.0), (1, _D, 11.0)]).with_columns(
            pl.col("trade_date").cast(pl.String)
        )

        assert derive_factor_ratios(window, _D).height == 1

    def test_empty_window_returns_empty(self) -> None:
        result = derive_factor_ratios(pl.DataFrame(), _D)

        assert result.is_empty()
        assert result.columns == ["instrument_id", "trade_date", "adjustment_ratio"]


@pytest.mark.unit
class TestDeriveEventAdjustmentRatios:
    """事件 + 主源前收 → 事件可推导比例；不可推导行保留原因."""

    def test_dividend_only(self) -> None:
        events = _events([(1, 1.0, None, None, None)])
        closes = _closes([(1, 20.0)])

        result = derive_event_adjustment_ratios(events, closes)

        assert result["adjustment_ratio"][0] == pytest.approx(20.0 / 19.0)
        assert result["event_kind"][0] == "dividend"
        assert result["underivable_reason"][0] is None

    def test_bonus_only_with_null_other_components(self) -> None:
        # 稀疏事件流：不适用的分量为 null，按 0 参与公式
        events = _events([(1, None, 0.5, None, None)])
        closes = _closes([(1, 10.0)])

        result = derive_event_adjustment_ratios(events, closes)

        assert result["adjustment_ratio"][0] == pytest.approx(1.5)
        assert result["event_kind"][0] == "bonus"

    def test_allotment_with_price(self) -> None:
        events = _events([(1, None, None, 0.2, 5.0)])
        closes = _closes([(1, 10.0)])

        result = derive_event_adjustment_ratios(events, closes)

        # ref = (10 + 0.2×5)/(1+0.2) = 11/1.2; ratio = 10/(11/1.2)
        assert result["adjustment_ratio"][0] == pytest.approx(12.0 / 11.0)
        assert result["event_kind"][0] == "allotment"

    def test_complex_ex_rights_event(self) -> None:
        # 复合除权例：分红 1 元 + 每股送 0.2
        events = _events([(1, 1.0, 0.2, None, None)])
        closes = _closes([(1, 20.0)])

        result = derive_event_adjustment_ratios(events, closes)

        reference = (20.0 - 1.0) / 1.2
        assert result["adjustment_ratio"][0] == pytest.approx(20.0 / reference)
        assert result["event_kind"][0] == "complex"

    def test_missing_prev_close_underivable(self) -> None:
        events = _events([(1, 1.0, None, None, None)])

        result = derive_event_adjustment_ratios(events, _closes([]))

        assert result["underivable_reason"][0] == "missing_prev_close"
        assert result["adjustment_ratio"][0] is None

    def test_missing_allotment_price_underivable(self) -> None:
        events = _events([(1, None, None, 0.1, None)])
        closes = _closes([(1, 10.0)])

        result = derive_event_adjustment_ratios(events, closes)

        assert result["underivable_reason"][0] == "missing_allotment_price"
        assert result["adjustment_ratio"][0] is None

    def test_empty_event_underivable(self) -> None:
        events = _events([(1, None, None, None, None)])
        closes = _closes([(1, 10.0)])

        result = derive_event_adjustment_ratios(events, closes)

        assert result["underivable_reason"][0] == "empty_event"

    def test_underivable_row_keeps_no_false_ratio(self) -> None:
        # 不可推导样本不得伪造数值比较
        events = _events([(1, 1.0, None, None, None), (2, None, 0.3, None, None)])
        closes = _closes([(2, 10.0)])

        result = derive_event_adjustment_ratios(events, closes)

        assert result.filter(pl.col("instrument_id") == 1)[
            "adjustment_ratio"
        ].to_list() == [None]
        assert result.filter(pl.col("instrument_id") == 2)[
            "adjustment_ratio"
        ].to_list() == [pytest.approx(1.3)]

    def test_empty_events_returns_typed_frame(self) -> None:
        result = derive_event_adjustment_ratios(_events([]), _closes([(1, 10.0)]))

        assert result.is_empty()
        assert "underivable_reason" in result.columns
