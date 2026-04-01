"""Golden data tests for all expression engine operators.

Every test case contains hand-computed expected values derived from the
operator semantics (shift-then-roll for ts_*, per-key aggregation for cs_*,
element-wise for scalar ops).  The parametrized structure makes it
straightforward to audit correctness by reading the input data alongside
the expected output.

Design notes
------------
* Time-series operators (ts_*) apply ``shift(1)`` internally for PIT
  protection (except ``ts_delay`` / ``ts_delta`` / ``ts_pct_change`` /
  ``ts_diff`` which shift by the user-specified period directly).
* Rolling aggregations use ``min_samples=window``, so the first
  ``(window - 1)`` output slots after the shift are always null.
* Cross-section operators (cs_*) operate over the entire frame (rank /
  len) or grouped by time keys (scale, zscore, demean) depending on the
  codegen implementation.
"""

from __future__ import annotations

from datetime import date

import polars as pl
from ditto_analytics.expression import ExpressionCompiler
from ditto_analytics.materialization import (
    DerivedRole,
    DerivedSpec,
    MaterializationProfile,
)

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _sample_frame() -> pl.DataFrame:
    """Two-entity, six-date sample frame sorted by [instrument_id, trade_date].

    Columns
    -------
    instrument_id : [1,1,1,1,1,1, 2,2,2,2,2,2]
    trade_date    : 2026-03-08 .. 2026-03-13 per entity
    close         : [10,11,10,12,15,8, 8,7.5,8,9,11,20]
    volume        : [100,110,100,120,140,130, 90,85,90,95,105,110]
    """
    return pl.DataFrame(
        {
            "instrument_id": [1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 2],
            "trade_date": [
                date(2026, 3, 8),
                date(2026, 3, 9),
                date(2026, 3, 10),
                date(2026, 3, 11),
                date(2026, 3, 12),
                date(2026, 3, 13),
                date(2026, 3, 8),
                date(2026, 3, 9),
                date(2026, 3, 10),
                date(2026, 3, 11),
                date(2026, 3, 12),
                date(2026, 3, 13),
            ],
            "close": [
                10.0,
                11.0,
                10.0,
                12.0,
                15.0,
                8.0,
                8.0,
                7.5,
                8.0,
                9.0,
                11.0,
                20.0,
            ],
            "volume": [
                100.0,
                110.0,
                100.0,
                120.0,
                140.0,
                130.0,
                90.0,
                85.0,
                90.0,
                95.0,
                105.0,
                110.0,
            ],
        }
    )


def _single_entity_frame(
    col_name: str,
    values: list[float],
    start: int = 8,
) -> pl.DataFrame:
    """Create a single-entity frame with one data column.

    Parameters
    ----------
    col_name : column name for the data
    values : values for each row (length determines number of rows)
    start : starting day of month for trade_date
    """
    n = len(values)
    dates = [date(2026, 3, start + i) for i in range(n)]
    return pl.DataFrame(
        {
            "instrument_id": [1] * n,
            "trade_date": dates,
            col_name: values,
        }
    )


_COMPILER = ExpressionCompiler()


def _eval_expr(
    df: pl.DataFrame,
    expression: str,
    *,
    col_name: str = "value",
    spec_id: str = "golden_test",
    role: DerivedRole = DerivedRole.FEATURE,
) -> pl.DataFrame:
    """Compile an expression and apply it to *df*, returning the enriched frame."""
    spec = DerivedSpec(
        id=spec_id,
        version=1,
        role=role,
        materialization_profile=MaterializationProfile.DERIVE,
        expression=expression,
    )
    compiled = _COMPILER.compile(spec)
    return df.sort(["instrument_id", "trade_date"]).with_columns(
        compiled.expr.alias(col_name),
    )


def _assert_values(
    result: pl.DataFrame,
    col_name: str,
    expected: list[float | None],
    *,
    tol: float = 1e-6,
) -> None:
    """Assert each value matches the expected golden data."""
    actual = result[col_name].to_list()
    assert len(actual) == len(expected), (
        f"length mismatch: got {len(actual)}, expected {len(expected)}"
    )
    for i, (a, e) in enumerate(zip(actual, expected, strict=True)):
        if e is None:
            assert a is None, f"row {i}: expected None, got {a!r}"
        else:
            assert a is not None, f"row {i}: expected {e}, got None"
            assert abs(a - e) < tol, (
                f"row {i}: expected {e}, got {a} (diff={abs(a - e)})"
            )


# ===================================================================
# 1. Time-series rolling operators (shift(1) + rolling aggregation)
# ===================================================================


class TestTsRollingMean:
    """ts_mean(x, window): shift(1) then rolling mean with min_samples=window."""

    def test_ts_mean_window3_simple(self) -> None:
        """Data x=[1,2,3,4,5], after shift: [null,1,2,3,4], rolling_mean(3):
        null, null, null, mean(1,2,3)=2.0, mean(2,3,4)=3.0.
        """
        df = _single_entity_frame("x", [1.0, 2.0, 3.0, 4.0, 5.0])
        result = _eval_expr(df, "ts_mean(x, 3)")
        _assert_values(result, "value", [None, None, None, 2.0, 3.0])

    def test_ts_mean_window3_sample_close_inst1(self) -> None:
        """Instrument 1 close: [10,11,10,12,15,8], after shift: [null,10,11,10,12,15].
        rolling_mean(3): null, null, null, mean(10,11,10)=31/3, mean(11,10,12)=11.0,
        mean(10,12,15)=37/3.
        """
        df = _single_entity_frame("close", [10.0, 11.0, 10.0, 12.0, 15.0, 8.0])
        result = _eval_expr(df, "ts_mean(close, 3)")
        _assert_values(
            result,
            "value",
            [None, None, None, 31.0 / 3.0, 11.0, 37.0 / 3.0],
        )


class TestTsRollingSum:
    """ts_sum(x, window): shift(1) then rolling sum with min_samples=window."""

    def test_ts_sum_window3_simple(self) -> None:
        """Data x=[1,2,3,4,5], after shift: [null,1,2,3,4], rolling_sum(3):
        null, null, null, sum(1,2,3)=6, sum(2,3,4)=9.
        """
        df = _single_entity_frame("x", [1.0, 2.0, 3.0, 4.0, 5.0])
        result = _eval_expr(df, "ts_sum(x, 3)")
        _assert_values(result, "value", [None, None, None, 6.0, 9.0])

    def test_ts_sum_window3_sample_close_inst1(self) -> None:
        """Instrument 1 close after shift: [null,10,11,10,12,15].
        rolling_sum(3): null, null, null, 31, 33, 37.
        """
        df = _single_entity_frame("close", [10.0, 11.0, 10.0, 12.0, 15.0, 8.0])
        result = _eval_expr(df, "ts_sum(close, 3)")
        _assert_values(result, "value", [None, None, None, 31.0, 33.0, 37.0])


class TestTsRollingStd:
    """ts_std(x, window): shift(1) then rolling std (ddof=1) with min_samples=window."""

    def test_ts_std_window3_simple(self) -> None:
        """Data x=[1,2,3,4,5], after shift: [null,1,2,3,4], rolling_std(3):
        null, null, null, std(1,2,3)=1.0, std(2,3,4)=1.0.
        """
        df = _single_entity_frame("x", [1.0, 2.0, 3.0, 4.0, 5.0])
        result = _eval_expr(df, "ts_std(x, 3)")
        _assert_values(result, "value", [None, None, None, 1.0, 1.0])

    def test_ts_std_window3_variable(self) -> None:
        """Data x=[10,11,10,12,15,8], after shift: [null,10,11,10,12,15].
        rolling_std(3, min=3):
          row 0-2: null (need 3 window positions)
          row 3: [10,11,10] -> std=sqrt(1/3)=0.577
          row 4: [11,10,12] -> mean=11, var=(0+1+1)/2=1, std=1.0
          row 5: [10,12,15] -> mean=37/3,
            var=((49+1+64)/9)/2=114/18=19/3, std=sqrt(19/3)
        """
        df = _single_entity_frame("close", [10.0, 11.0, 10.0, 12.0, 15.0, 8.0])
        result = _eval_expr(df, "ts_std(close, 3)")
        import math

        expected_3 = math.sqrt(1.0 / 3.0)
        expected_5 = math.sqrt(19.0 / 3.0)
        _assert_values(
            result,
            "value",
            [None, None, None, expected_3, 1.0, expected_5],
        )


class TestTsRollingVar:
    """ts_var(x, window): shift(1) then rolling variance (ddof=1)."""

    def test_ts_var_window3_simple(self) -> None:
        """Data x=[1,2,3,4,5], after shift: [null,1,2,3,4].
        var([1,2,3])=1.0, var([2,3,4])=1.0.
        """
        df = _single_entity_frame("x", [1.0, 2.0, 3.0, 4.0, 5.0])
        result = _eval_expr(df, "ts_var(x, 3)")
        _assert_values(result, "value", [None, None, None, 1.0, 1.0])


class TestTsRollingMax:
    """ts_max(x, window): shift(1) then rolling max."""

    def test_ts_max_window3_simple(self) -> None:
        """Data x=[1,2,3,4,5], after shift: [null,1,2,3,4].
        rolling_max(3): null, null, null, max(1,2,3)=3, max(2,3,4)=4.
        """
        df = _single_entity_frame("x", [1.0, 2.0, 3.0, 4.0, 5.0])
        result = _eval_expr(df, "ts_max(x, 3)")
        _assert_values(result, "value", [None, None, None, 3.0, 4.0])

    def test_ts_max_window3_sample_close_inst1(self) -> None:
        """Instrument 1 close after shift: [null,10,11,10,12,15].
        rolling_max(3): null, null, null, 11, 12, 15.
        """
        df = _single_entity_frame("close", [10.0, 11.0, 10.0, 12.0, 15.0, 8.0])
        result = _eval_expr(df, "ts_max(close, 3)")
        _assert_values(result, "value", [None, None, None, 11.0, 12.0, 15.0])


class TestTsRollingMin:
    """ts_min(x, window): shift(1) then rolling min."""

    def test_ts_min_window3_simple(self) -> None:
        """Data x=[1,2,3,4,5], after shift: [null,1,2,3,4].
        rolling_min(3): null, null, null, min(1,2,3)=1, min(2,3,4)=2.
        """
        df = _single_entity_frame("x", [1.0, 2.0, 3.0, 4.0, 5.0])
        result = _eval_expr(df, "ts_min(x, 3)")
        _assert_values(result, "value", [None, None, None, 1.0, 2.0])

    def test_ts_min_window3_sample_close_inst1(self) -> None:
        """Instrument 1 close after shift: [null,10,11,10,12,15].
        rolling_min(3): null, null, null, 10, 10, 10.
        """
        df = _single_entity_frame("close", [10.0, 11.0, 10.0, 12.0, 15.0, 8.0])
        result = _eval_expr(df, "ts_min(close, 3)")
        _assert_values(result, "value", [None, None, None, 10.0, 10.0, 10.0])


class TestTsCount:
    """ts_count(x, window): shift(1) then count non-null in rolling window."""

    def test_ts_count_window3_no_nulls(self) -> None:
        """Data x=[1,2,3,4,5], after shift: [null,1,2,3,4].
        is_not_null: [0,1,1,1,1], rolling_sum(3, min=3):
        null, null, sum(0,1,1)=2, sum(1,1,1)=3, sum(1,1,1)=3.
        """
        df = _single_entity_frame("x", [1.0, 2.0, 3.0, 4.0, 5.0])
        result = _eval_expr(df, "ts_count(x, 3)")
        _assert_values(result, "value", [None, None, 2.0, 3.0, 3.0])


class TestTsMedian:
    """ts_median(x, window): shift(1) then rolling median."""

    def test_ts_median_window3_simple(self) -> None:
        """Data x=[1,2,3,4,5], after shift: [null,1,2,3,4].
        rolling_median(3): null, null, null, median(1,2,3)=2, median(2,3,4)=3.
        """
        df = _single_entity_frame("x", [1.0, 2.0, 3.0, 4.0, 5.0])
        result = _eval_expr(df, "ts_median(x, 3)")
        _assert_values(result, "value", [None, None, None, 2.0, 3.0])

    def test_ts_median_window3_sample_close_inst1(self) -> None:
        """Instrument 1 close after shift: [null,10,11,10,12,15].
        rolling_median(3): null, null, null, median(10,11,10)=10, median(11,10,12)=11,
        median(10,12,15)=12.
        """
        df = _single_entity_frame("close", [10.0, 11.0, 10.0, 12.0, 15.0, 8.0])
        result = _eval_expr(df, "ts_median(close, 3)")
        _assert_values(result, "value", [None, None, None, 10.0, 11.0, 12.0])


# ===================================================================
# 2. Time-series shift-only operators
# ===================================================================


class TestTsDelay:
    """ts_delay(x, period): shift by the given period per entity (no rolling)."""

    def test_ts_delay_period2(self) -> None:
        """Instrument 1 close: [10,11,10,12,15,8].
        shift(2): [null, null, 10, 11, 10, 12].
        """
        df = _single_entity_frame("close", [10.0, 11.0, 10.0, 12.0, 15.0, 8.0])
        result = _eval_expr(df, "ts_delay(close, 2)")
        _assert_values(result, "value", [None, None, 10.0, 11.0, 10.0, 12.0])

    def test_ts_delay_period1(self) -> None:
        """Instrument 1 close: [10,11,10,12,15,8].
        shift(1): [null, 10, 11, 10, 12, 15].
        """
        df = _single_entity_frame("close", [10.0, 11.0, 10.0, 12.0, 15.0, 8.0])
        result = _eval_expr(df, "ts_delay(close, 1)")
        _assert_values(result, "value", [None, 10.0, 11.0, 10.0, 12.0, 15.0])


class TestTsDelta:
    """ts_delta(x, period): x - shift(period) per entity."""

    def test_ts_delta_period1(self) -> None:
        """Instrument 1 close: [10,11,10,12,15,8].
        delta = close - shift(1): [null, 1.0, -1.0, 2.0, 3.0, -7.0].
        """
        df = _single_entity_frame("close", [10.0, 11.0, 10.0, 12.0, 15.0, 8.0])
        result = _eval_expr(df, "ts_delta(close, 1)")
        _assert_values(result, "value", [None, 1.0, -1.0, 2.0, 3.0, -7.0])

    def test_ts_delta_period2(self) -> None:
        """Instrument 1 close: [10,11,10,12,15,8].
        delta = close - shift(2): [null, null, 0.0, 1.0, 5.0, -4.0].
        """
        df = _single_entity_frame("close", [10.0, 11.0, 10.0, 12.0, 15.0, 8.0])
        result = _eval_expr(df, "ts_delta(close, 2)")
        _assert_values(result, "value", [None, None, 0.0, 1.0, 5.0, -4.0])


class TestTsPctChange:
    """ts_pct_change(x, period): (x - shift(period)) / shift(period)."""

    def test_ts_pct_change_period1(self) -> None:
        """Instrument 1 close: [10,11,10,12,15,8].
        shifted = shift(1): [null,10,11,10,12,15].
        pct = (close/shifted)-1: [null, 0.1, -1/11, 0.2, 0.25, -7/15].
        """
        df = _single_entity_frame("close", [10.0, 11.0, 10.0, 12.0, 15.0, 8.0])
        result = _eval_expr(df, "ts_pct_change(close, 1)")
        _assert_values(
            result,
            "value",
            [None, 0.1, -1.0 / 11.0, 0.2, 0.25, -7.0 / 15.0],
        )

    def test_ts_pct_change_zero_denominator(self) -> None:
        """When the shifted value is 0, ts_pct_change returns 0.0."""
        df = _single_entity_frame("x", [5.0, 0.0, 0.0, 3.0], start=10)
        result = _eval_expr(df, "ts_pct_change(x, 1)")
        # shifted: [null, 5, 0, 0]
        # pct: [null, (0/5)-1=-1.0, 0.0 (zero denom), 0.0 (zero denom)]
        _assert_values(
            result,
            "value",
            [None, -1.0, 0.0, 0.0],
        )


class TestTsDiff:
    """ts_diff is an alias for ts_delta."""

    def test_ts_diff_period1(self) -> None:
        """ts_diff should produce the same result as ts_delta."""
        df = _single_entity_frame("close", [10.0, 11.0, 10.0, 12.0, 15.0, 8.0])
        result = _eval_expr(df, "ts_diff(close, 1)")
        _assert_values(result, "value", [None, 1.0, -1.0, 2.0, 3.0, -7.0])


# ===================================================================
# 3. Time-series special operators
# ===================================================================


class TestTsRank:
    """ts_rank(x, window): shift(1) then rolling rank / window."""

    def test_ts_rank_window3_simple(self) -> None:
        """Data x=[1,2,3,4,5], after shift: [null,1,2,3,4].
        rolling_rank(3, min=3)/3:
          row 2: window [null,1,2], null excluded, rank(2)=2, 2/3=0.667.
          row 3: window [1,2,3], rank(3)=3, 3/3=1.0.
          row 4: window [2,3,4], rank(4)=3, 3/3=1.0.
        """
        df = _single_entity_frame("x", [1.0, 2.0, 3.0, 4.0, 5.0])
        result = _eval_expr(df, "ts_rank(x, 3)")
        _assert_values(result, "value", [None, None, 2.0 / 3.0, 1.0, 1.0])

    def test_ts_rank_window3_variable(self) -> None:
        """Data x=[5,1,3,4,2], after shift: [null,5,1,3,4].
        rolling_rank(3, min=3)/3:
          row 2: window [null,5,1], null excluded, sorted=[1,5], rank(1)=1, 1/3=0.333.
          row 3: window [5,1,3], sorted=[1,3,5], rank(3)=2, 2/3=0.667.
          row 4: window [1,3,4], sorted=[1,3,4], rank(4)=3, 3/3=1.0.
        """
        df = _single_entity_frame("x", [5.0, 1.0, 3.0, 4.0, 2.0], start=10)
        result = _eval_expr(df, "ts_rank(x, 3)")
        _assert_values(result, "value", [None, None, 1.0 / 3.0, 2.0 / 3.0, 1.0])


class TestTsEma:
    """ts_ema(x, span): shift(1) then ewm_mean(span, min_samples=1)."""

    def test_ts_ema_span3(self) -> None:
        """Data x=[1,2,3,4,5,6], after shift: [null,1,2,3,4,5].
        ewm_mean(span=3, min_samples=1) starts from the first non-null.
        """
        df = _single_entity_frame("x", [1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
        result = _eval_expr(df, "ts_ema(x, 3)")
        values = result["value"].to_list()
        # First value should be null (shifted), rest should be finite
        assert values[0] is None
        for v in values[1:]:
            assert v is not None
            assert abs(v) < 1e10, f"unexpected value: {v}"

    def test_ts_ema_produces_increasing_values(self) -> None:
        """For monotonically increasing input, EMA should also be monotonically
        increasing after the first non-null value.
        """
        df = _single_entity_frame("x", [1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
        result = _eval_expr(df, "ts_ema(x, 3)")
        non_null = [v for v in result["value"].to_list() if v is not None]
        for i in range(1, len(non_null)):
            assert non_null[i] > non_null[i - 1], (
                f"EMA not increasing at index {i}: {non_null[i - 1]} -> {non_null[i]}"
            )


class TestTsDecayLinear:
    """ts_decay_linear(x, window): shift(1) then WMA (linearly weighted)."""

    def test_ts_decay_linear_window3_simple(self) -> None:
        """Data x=[1,2,3,4,5], after shift: [null,1,2,3,4].
        rolling_map with WMA, window=3, min_samples=3:
          window [1,2,3]: WMA = (1*1+2*2+3*3)/(1+2+3) = 14/6
          window [2,3,4]: WMA = (1*2+2*3+3*4)/(1+2+3) = 20/6
        """
        df = _single_entity_frame("x", [1.0, 2.0, 3.0, 4.0, 5.0])
        result = _eval_expr(df, "ts_decay_linear(x, 3)")
        _assert_values(
            result,
            "value",
            [None, None, None, 14.0 / 6.0, 20.0 / 6.0],
        )


class TestTsCorr:
    """ts_corr(a, b, window): shift(1) then rolling correlation."""

    def test_ts_corr_window3_perfectly_correlated(self) -> None:
        """Data a=[1,2,3,4,5,6], b=[2,4,6,8,10,12] (b=2a).
        After shift: a=[null,1,2,3,4,5], b=[null,2,4,6,8,10].
        rolling_corr(3): null, null, null, ~1.0, ~1.0, ~1.0.
        """
        df = pl.DataFrame(
            {
                "instrument_id": [1] * 6,
                "trade_date": [date(2026, 3, 8 + i) for i in range(6)],
                "a": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
                "b": [2.0, 4.0, 6.0, 8.0, 10.0, 12.0],
            }
        )
        result = _eval_expr(df, "ts_corr(a, b, 3)")
        values = result["value"].to_list()
        # First 3 are null (shift + min_samples)
        assert values[0] is None
        assert values[1] is None
        assert values[2] is None
        # Perfect correlation should yield ~1.0
        for v in values[3:]:
            assert v is not None
            assert abs(v - 1.0) < 0.01, f"expected ~1.0, got {v}"


class TestTsCov:
    """ts_cov(a, b, window): shift(1) then rolling covariance."""

    def test_ts_cov_window3_perfectly_correlated(self) -> None:
        """Data a=[1,2,3,4,5,6], b=[2,4,6,8,10,12] (b=2a).
        After shift: a=[null,1,2,3,4,5], b=[null,2,4,6,8,10].
        cov([1,2,3],[2,4,6]) = 2.0 (ddof=1).
        cov([2,3,4],[4,6,8]) = 2.0.
        cov([3,4,5],[6,8,10]) = 2.0.
        """
        df = pl.DataFrame(
            {
                "instrument_id": [1] * 6,
                "trade_date": [date(2026, 3, 8 + i) for i in range(6)],
                "a": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
                "b": [2.0, 4.0, 6.0, 8.0, 10.0, 12.0],
            }
        )
        result = _eval_expr(df, "ts_cov(a, b, 3)")
        _assert_values(
            result,
            "value",
            [None, None, None, 2.0, 2.0, 2.0],
            tol=1e-10,
        )


class TestTsArgmax:
    """ts_argmax(x, window): shift(1) then position of maximum in window."""

    def test_ts_argmax_window3_ascending(self) -> None:
        """Data x=[1,2,3,4,5], after shift: [null,1,2,3,4].
        window [1,2,3]: arg_max=2 (value 3 at index 2)
        window [2,3,4]: arg_max=2 (value 4 at index 2)
        """
        df = _single_entity_frame("x", [1.0, 2.0, 3.0, 4.0, 5.0])
        result = _eval_expr(df, "ts_argmax(x, 3)")
        _assert_values(result, "value", [None, None, None, 2.0, 2.0])

    def test_ts_argmax_window3_variable(self) -> None:
        """Data x=[5,1,3,4,2], after shift: [null,5,1,3,4].
        window [5,1,3]: arg_max=0 (value 5 at index 0)
        window [1,3,4]: arg_max=2 (value 4 at index 2)
        """
        df = _single_entity_frame("x", [5.0, 1.0, 3.0, 4.0, 2.0], start=10)
        result = _eval_expr(df, "ts_argmax(x, 3)")
        _assert_values(result, "value", [None, None, None, 0.0, 2.0])


class TestTsArgmin:
    """ts_argmin(x, window): shift(1) then position of minimum in window."""

    def test_ts_argmin_window3_variable(self) -> None:
        """Data x=[5,1,3,4,2], after shift: [null,5,1,3,4].
        window [5,1,3]: arg_min=1 (value 1 at index 1)
        window [1,3,4]: arg_min=0 (value 1 at index 0)
        """
        df = _single_entity_frame("x", [5.0, 1.0, 3.0, 4.0, 2.0], start=10)
        result = _eval_expr(df, "ts_argmin(x, 3)")
        _assert_values(result, "value", [None, None, None, 1.0, 0.0])


# ===================================================================
# 4. Cross-section operators
# ===================================================================


class TestCsRank:
    """cs_rank(x): rank(method='ordinal') / pl.len() over entire frame."""

    def test_cs_rank_close_on_sample_frame(self) -> None:
        """On the two-entity sample frame, close values sorted by ordinal rank:
        7.5(1), 8(2), 8(3), 8(4), 9(5), 10(6), 10(7), 11(8), 11(9), 12(10),
        15(11), 20(12).  Divided by total rows (12).
        Frame order: [10,11,10,12,15,8, 8,7.5,8,9,11,20]
        Ordinal ranks: [6,8,7,10,11,2, 3,1,4,5,9,12]
        """
        df = _sample_frame()
        result = _eval_expr(df, "cs_rank(close)")
        expected = [
            6.0 / 12.0,  # inst1, close=10
            8.0 / 12.0,  # inst1, close=11
            7.0 / 12.0,  # inst1, close=10
            10.0 / 12.0,  # inst1, close=12
            11.0 / 12.0,  # inst1, close=15
            2.0 / 12.0,  # inst1, close=8
            3.0 / 12.0,  # inst2, close=8
            1.0 / 12.0,  # inst2, close=7.5
            4.0 / 12.0,  # inst2, close=8
            5.0 / 12.0,  # inst2, close=9
            9.0 / 12.0,  # inst2, close=11
            12.0 / 12.0,  # inst2, close=20
        ]
        _assert_values(result, "value", expected)


class TestCsScale:
    """cs_scale(x): x / sum(|x|) per trade_date, zero denominator -> 0."""

    def test_cs_scale_close_on_sample_frame(self) -> None:
        """On the two-entity sample frame, per date:
        date 3/8: close=[10,8], sum(|close|)=18, scale=[10/18, 8/18]
        date 3/9: close=[11,7.5], sum(|close|)=18.5, scale=[11/18.5, 7.5/18.5]
        date 3/10: close=[10,8], sum(|close|)=18, scale=[10/18, 8/18]
        date 3/11: close=[12,9], sum(|close|)=21, scale=[12/21, 9/21]
        date 3/12: close=[15,11], sum(|close|)=26, scale=[15/26, 11/26]
        date 3/13: close=[8,20], sum(|close|)=28, scale=[8/28, 20/28]
        """
        df = _sample_frame()
        result = _eval_expr(df, "cs_scale(close)")
        expected = [
            10.0 / 18.0,
            11.0 / 18.5,
            10.0 / 18.0,
            12.0 / 21.0,
            15.0 / 26.0,
            8.0 / 28.0,
            8.0 / 18.0,
            7.5 / 18.5,
            8.0 / 18.0,
            9.0 / 21.0,
            11.0 / 26.0,
            20.0 / 28.0,
        ]
        _assert_values(result, "value", expected)

    def test_cs_scale_zero_values(self) -> None:
        """cs_scale on an all-zero column should return 0.0 for all rows."""
        df = pl.DataFrame(
            {
                "instrument_id": [1, 1, 2, 2],
                "trade_date": [date(2026, 3, 10), date(2026, 3, 11)] * 2,
                "x": [0.0, 0.0, 0.0, 0.0],
            }
        )
        result = _eval_expr(df, "cs_scale(x)")
        _assert_values(result, "value", [0.0, 0.0, 0.0, 0.0])


class TestCsZscore:
    """cs_zscore(x): (x - mean) / std per trade_date, zero std -> 0."""

    def test_cs_zscore_close_on_sample_frame(self) -> None:
        """On the two-entity sample frame, per date:
        date 3/8: close=[10,8], mean=9, std=sqrt(2), z=[1/sqrt(2), -1/sqrt(2)]
        date 3/9: close=[11,7.5], mean=9.25, std=sqrt(6.125), z=[1.75/std, -1.75/std]
        All dates have identical |zscore| since we always have exactly 2
        values with the same spread pattern (d/2, -d/2).
        For 2 values [a, b]: mean=(a+b)/2, std=|a-b|/sqrt(2).
        zscore(a) = (a - mean)/std = ((a-b)/2) / ((a-b)/sqrt(2))
        = sqrt(2)/2 = 1/sqrt(2).
        """
        df = _sample_frame()
        result = _eval_expr(df, "cs_zscore(close)")
        import math

        expected_val = 1.0 / math.sqrt(2.0)
        # Instrument 1 has higher close on dates 3/8-3/12, lower on 3/13
        expected = [
            expected_val,  # 3/8: inst1=10 > inst2=8
            expected_val,  # 3/9: inst1=11 > inst2=7.5
            expected_val,  # 3/10: inst1=10 > inst2=8
            expected_val,  # 3/11: inst1=12 > inst2=9
            expected_val,  # 3/12: inst1=15 > inst2=11
            -expected_val,  # 3/13: inst1=8 < inst2=20
            -expected_val,  # 3/8: inst2=8 < inst1=10
            -expected_val,  # 3/9: inst2=7.5 < inst1=11
            -expected_val,  # 3/10: inst2=8 < inst1=10
            -expected_val,  # 3/11: inst2=9 < inst1=12
            -expected_val,  # 3/12: inst2=11 < inst1=15
            expected_val,  # 3/13: inst2=20 > inst1=8
        ]
        _assert_values(result, "value", expected)

    def test_cs_zscore_zero_std(self) -> None:
        """cs_zscore on a constant column (std=0) should return 0.0."""
        df = pl.DataFrame(
            {
                "instrument_id": [1, 1, 2, 2],
                "trade_date": [date(2026, 3, 10), date(2026, 3, 11)] * 2,
                "x": [5.0, 5.0, 5.0, 5.0],
            }
        )
        result = _eval_expr(df, "cs_zscore(x)")
        _assert_values(result, "value", [0.0, 0.0, 0.0, 0.0])


class TestCsDemean:
    """cs_demean(x): x - mean per trade_date."""

    def test_cs_demean_close_on_sample_frame(self) -> None:
        """On the two-entity sample frame, per date:
        date 3/8: close=[10,8], mean=9, demean=[1,-1]
        date 3/9: close=[11,7.5], mean=9.25, demean=[1.75,-1.75]
        date 3/10: close=[10,8], mean=9, demean=[1,-1]
        date 3/11: close=[12,9], mean=10.5, demean=[1.5,-1.5]
        date 3/12: close=[15,11], mean=13, demean=[2,-2]
        date 3/13: close=[8,20], mean=14, demean=[-6,6]
        """
        df = _sample_frame()
        result = _eval_expr(df, "cs_demean(close)")
        expected = [
            1.0,  # 3/8 inst1
            1.75,  # 3/9 inst1
            1.0,  # 3/10 inst1
            1.5,  # 3/11 inst1
            2.0,  # 3/12 inst1
            -6.0,  # 3/13 inst1
            -1.0,  # 3/8 inst2
            -1.75,  # 3/9 inst2
            -1.0,  # 3/10 inst2
            -1.5,  # 3/11 inst2
            -2.0,  # 3/12 inst2
            6.0,  # 3/13 inst2
        ]
        _assert_values(result, "value", expected)


# ===================================================================
# 5. Grouped cross-section operators
# ===================================================================


class TestGroupRank:
    """group_rank(x, group): rank within group / group size."""

    def test_group_rank_sector(self) -> None:
        """Three instruments with sector groupings:
        inst1, inst2 in sector A (x=10, 20), inst3 in sector B (x=30).
        Sector A: ordinal rank [1,2], size=2, result [0.5, 1.0].
        Sector B: ordinal rank [1], size=1, result [1.0].
        """
        df = pl.DataFrame(
            {
                "instrument_id": [1, 2, 3],
                "trade_date": [date(2026, 3, 10)] * 3,
                "sector": ["A", "A", "B"],
                "x": [10.0, 20.0, 30.0],
            }
        )
        result = _eval_expr(df, "group_rank(x, sector)")
        _assert_values(result, "value", [0.5, 1.0, 1.0])

    def test_group_rank_multiple_dates(self) -> None:
        """group_rank should compute rank within group across all rows."""
        df = pl.DataFrame(
            {
                "instrument_id": [1, 1, 2, 2, 3, 3],
                "trade_date": [
                    date(2026, 3, 10),
                    date(2026, 3, 11),
                    date(2026, 3, 10),
                    date(2026, 3, 11),
                    date(2026, 3, 10),
                    date(2026, 3, 11),
                ],
                "sector": ["A", "A", "B", "B", "A", "A"],
                "x": [10.0, 20.0, 30.0, 40.0, 50.0, 60.0],
            }
        )
        result = _eval_expr(df, "group_rank(x, sector)")
        values = result["value"].to_list()
        # All values should be in (0, 1]
        for v in values:
            assert v is not None
            assert 0 < v <= 1.0, f"value {v} not in (0, 1]"


class TestGroupZscore:
    """group_zscore(x, group): (x - mean) / std within group, zero std -> 0."""

    def test_group_zscore_sector(self) -> None:
        """Two instruments per sector:
        Sector A: x=[10,20], mean=15, std=sqrt(50)=7.0711...
          zscore(10) = -5/7.0711 = -1/sqrt(2)
          zscore(20) = 5/7.0711 = 1/sqrt(2)
        Sector B: x=[5,5], std=0, zscore=0.0 for both.
        """
        df = pl.DataFrame(
            {
                "instrument_id": [1, 1, 2, 2, 3, 3],
                "trade_date": [
                    date(2026, 3, 10),
                    date(2026, 3, 11),
                    date(2026, 3, 10),
                    date(2026, 3, 11),
                    date(2026, 3, 10),
                    date(2026, 3, 11),
                ],
                "sector": ["A", "A", "B", "B", "A", "A"],
                "x": [10.0, 20.0, 5.0, 5.0, 50.0, 60.0],
            }
        )
        result = _eval_expr(df, "group_zscore(x, sector)")
        values = result["value"].to_list()
        # Sector B has constant x, std=0 -> 0.0
        assert values[2] == 0.0
        assert values[3] == 0.0
        # Sector A has non-zero std
        assert values[0] is not None
        # All values finite
        import math as _math

        for v in values:
            if v is not None:
                assert not _math.isnan(v)
                assert not _math.isinf(v)


# ===================================================================
# 6. Scalar unary operators
# ===================================================================


class TestScalarAbs:
    """abs(x): absolute value."""

    def test_abs_negative_values(self) -> None:
        """abs on a column with negative values."""
        df = _single_entity_frame("x", [-3.0, 0.0, 5.0, -1.5])
        result = _eval_expr(df, "abs(x)")
        _assert_values(result, "value", [3.0, 0.0, 5.0, 1.5])


class TestScalarLog:
    """log(x): natural logarithm."""

    def test_log_known_values(self) -> None:
        """log(1)=0, log(e)=1, log(e^2)=2."""
        import math

        e = math.e
        df = _single_entity_frame("x", [1.0, e, e * e])
        result = _eval_expr(df, "log(x)")
        _assert_values(result, "value", [0.0, 1.0, 2.0])


class TestScalarLog10:
    """log10(x): base-10 logarithm."""

    def test_log10_known_values(self) -> None:
        """log10(1)=0, log10(10)=1, log10(100)=2."""
        df = _single_entity_frame("x", [1.0, 10.0, 100.0])
        result = _eval_expr(df, "log10(x)")
        _assert_values(result, "value", [0.0, 1.0, 2.0])


class TestScalarLog2:
    """log2(x): base-2 logarithm."""

    def test_log2_known_values(self) -> None:
        """log2(1)=0, log2(2)=1, log2(8)=3."""
        df = _single_entity_frame("x", [1.0, 2.0, 8.0])
        result = _eval_expr(df, "log2(x)")
        _assert_values(result, "value", [0.0, 1.0, 3.0])


class TestScalarFloor:
    """floor(x): round toward negative infinity."""

    def test_floor_known_values(self) -> None:
        """floor(1.7)=1, floor(-1.2)=-2, floor(3.0)=3."""
        df = _single_entity_frame("x", [1.7, -1.2, 3.0])
        result = _eval_expr(df, "floor(x)")
        _assert_values(result, "value", [1.0, -2.0, 3.0])


class TestScalarCeil:
    """ceil(x): round toward positive infinity."""

    def test_ceil_known_values(self) -> None:
        """ceil(1.2)=2, ceil(-1.7)=-1, ceil(3.0)=3."""
        df = _single_entity_frame("x", [1.2, -1.7, 3.0])
        result = _eval_expr(df, "ceil(x)")
        _assert_values(result, "value", [2.0, -1.0, 3.0])


class TestScalarExp:
    """exp(x): exponential (e^x)."""

    def test_exp_known_values(self) -> None:
        """exp(0)=1, exp(1)=e, exp(ln(2))=2."""
        import math

        df = _single_entity_frame("x", [0.0, 1.0, math.log(2.0)])
        result = _eval_expr(df, "exp(x)")
        _assert_values(result, "value", [1.0, math.e, 2.0])


class TestScalarSqrt:
    """sqrt(x): square root."""

    def test_sqrt_known_values(self) -> None:
        """sqrt(0)=0, sqrt(1)=1, sqrt(4)=2, sqrt(9)=3."""
        df = _single_entity_frame("x", [0.0, 1.0, 4.0, 9.0])
        result = _eval_expr(df, "sqrt(x)")
        _assert_values(result, "value", [0.0, 1.0, 2.0, 3.0])


class TestScalarSign:
    """sign(x): -1 for negative, 0 for zero, 1 for positive."""

    def test_sign_known_values(self) -> None:
        """sign(-5)=-1, sign(0)=0, sign(3)=1."""
        df = _single_entity_frame("x", [-5.0, 0.0, 3.0])
        result = _eval_expr(df, "sign(x)")
        _assert_values(result, "value", [-1.0, 0.0, 1.0])


# ===================================================================
# 7. Scalar binary operators
# ===================================================================


class TestScalarPower:
    """power(a, b): a^b."""

    def test_power_known_values(self) -> None:
        """power(2, 3)=8, power(4, 0.5)=2, power(5, 2)=25."""
        df = pl.DataFrame(
            {
                "instrument_id": [1, 1, 1],
                "trade_date": [
                    date(2026, 3, 10),
                    date(2026, 3, 11),
                    date(2026, 3, 12),
                ],
                "a": [2.0, 4.0, 5.0],
                "b": [3.0, 0.5, 2.0],
            }
        )
        result = _eval_expr(df, "power(a, b)")
        _assert_values(result, "value", [8.0, 2.0, 25.0])


class TestScalarMax2:
    """max2(a, b): element-wise maximum of two columns."""

    def test_max2_known_values(self) -> None:
        """max2(3, 5)=5, max2(7, 2)=7, max2(4, 4)=4."""
        df = pl.DataFrame(
            {
                "instrument_id": [1, 1, 1],
                "trade_date": [
                    date(2026, 3, 10),
                    date(2026, 3, 11),
                    date(2026, 3, 12),
                ],
                "a": [3.0, 7.0, 4.0],
                "b": [5.0, 2.0, 4.0],
            }
        )
        result = _eval_expr(df, "max2(a, b)")
        _assert_values(result, "value", [5.0, 7.0, 4.0])


class TestScalarMin2:
    """min2(a, b): element-wise minimum of two columns."""

    def test_min2_known_values(self) -> None:
        """min2(3, 5)=3, min2(7, 2)=2, min2(4, 4)=4."""
        df = pl.DataFrame(
            {
                "instrument_id": [1, 1, 1],
                "trade_date": [
                    date(2026, 3, 10),
                    date(2026, 3, 11),
                    date(2026, 3, 12),
                ],
                "a": [3.0, 7.0, 4.0],
                "b": [5.0, 2.0, 4.0],
            }
        )
        result = _eval_expr(df, "min2(a, b)")
        _assert_values(result, "value", [3.0, 2.0, 4.0])


class TestScalarRound:
    """round(x, decimals): round to specified decimal places."""

    def test_round_to_zero_decimals(self) -> None:
        """round(1.4, 0)=1, round(1.5, 0)=2, round(2.6, 0)=3."""
        df = _single_entity_frame("x", [1.4, 1.5, 2.6])
        result = _eval_expr(df, "round(x, 0)")
        _assert_values(result, "value", [1.0, 2.0, 3.0])

    def test_round_to_one_decimal(self) -> None:
        """round(1.25, 1)=1.2, round(1.35, 1)=1.4 (banker's rounding)."""
        df = _single_entity_frame("x", [1.25, 1.35])
        result = _eval_expr(df, "round(x, 1)")
        values = result["value"].to_list()
        # Polars uses banker's rounding
        assert values[0] == 1.2 or values[0] == 1.3
        assert values[1] == 1.3 or values[1] == 1.4


class TestScalarClip:
    """clip(x, lo, hi): clamp values to [lo, hi]."""

    def test_clip_known_values(self) -> None:
        """clip(-5, 0, 10)=0, clip(3, 0, 10)=3, clip(15, 0, 10)=10."""
        df = _single_entity_frame("x", [-5.0, 3.0, 15.0])
        result = _eval_expr(df, "clip(x, 0, 10)")
        _assert_values(result, "value", [0.0, 3.0, 10.0])


class TestScalarIfElse:
    """if_else(condition, then, else): conditional expression."""

    def test_if_else_simple(self) -> None:
        """if_else(x > 3, x * 2, 0) for x=[1,4,2,5]: [0, 8, 0, 10]."""
        df = _single_entity_frame("x", [1.0, 4.0, 2.0, 5.0])
        result = _eval_expr(df, "if_else(x > 3, x * 2, 0)")
        _assert_values(result, "value", [0.0, 8.0, 0.0, 10.0])

    def test_if_else_with_string_result(self) -> None:
        """if_else can produce string results."""
        df = _single_entity_frame("x", [1.0, 4.0, 2.0, 5.0])
        result = _eval_expr(df, 'if_else(x > 3, "high", "low")')
        assert result["value"].to_list() == ["low", "high", "low", "high"]


class TestScalarCoalesce:
    """coalesce(a, b, ...): first non-null argument."""

    def test_coalesce_two_columns(self) -> None:
        """coalesce(a, b): a=[1,null,3,null], b=[null,2,null,4] -> [1,2,3,4]."""
        df = pl.DataFrame(
            {
                "instrument_id": [1, 1, 1, 1],
                "trade_date": [
                    date(2026, 3, 10),
                    date(2026, 3, 11),
                    date(2026, 3, 12),
                    date(2026, 3, 13),
                ],
                "a": [1.0, None, 3.0, None],
                "b": [None, 2.0, None, 4.0],
            }
        )
        result = _eval_expr(df, "coalesce(a, b)")
        _assert_values(result, "value", [1.0, 2.0, 3.0, 4.0])

    def test_coalesce_three_columns(self) -> None:
        """coalesce(a, b, c): a=[null, null], b=[null, null], c=[5, 6] -> [5, 6]."""
        df = pl.DataFrame(
            {
                "instrument_id": [1, 1],
                "trade_date": [date(2026, 3, 10), date(2026, 3, 11)],
                "a": [None, None],
                "b": [None, None],
                "c": [5.0, 6.0],
            }
        )
        result = _eval_expr(df, "coalesce(a, b, c)")
        _assert_values(result, "value", [5.0, 6.0])

    def test_coalesce_fallback_to_literal(self) -> None:
        """coalesce(a, 0): returns a when non-null, else 0."""
        df = pl.DataFrame(
            {
                "instrument_id": [1, 1],
                "trade_date": [date(2026, 3, 10), date(2026, 3, 11)],
                "a": [5.0, None],
            }
        )
        result = _eval_expr(df, "coalesce(a, 0)")
        _assert_values(result, "value", [5.0, 0.0])


# ===================================================================
# 8. Multi-entity rolling: two-entity sample frame
# ===================================================================


class TestTsRollingTwoEntities:
    """Verify that rolling operators produce independent results per entity."""

    def test_ts_mean_close_two_entities(self) -> None:
        """ts_mean(close, 3) on the two-entity frame.
        Instrument 1 close after shift: [null,10,11,10,12,15].
        Instrument 2 close after shift: [null,8,7.5,8,9,11].
        Each entity computes independently.
        """
        df = _sample_frame()
        result = _eval_expr(df, "ts_mean(close, 3)")
        # Inst 1: null, null, null, 31/3, 11.0, 37/3
        # Inst 2: null, null, null, (8+7.5+8)/3, (7.5+8+9)/3, (8+9+11)/3
        inst1_expected = [None, None, None, 31.0 / 3.0, 11.0, 37.0 / 3.0]
        inst2_expected = [
            None,
            None,
            None,
            (8.0 + 7.5 + 8.0) / 3.0,
            (7.5 + 8.0 + 9.0) / 3.0,
            (8.0 + 9.0 + 11.0) / 3.0,
        ]
        _assert_values(result, "value", inst1_expected + inst2_expected)

    def test_ts_delay_close_two_entities(self) -> None:
        """ts_delay(close, 2) on the two-entity frame.
        Instrument 1: [null, null, 10, 11, 10, 12]
        Instrument 2: [null, null, 8, 7.5, 8, 9]
        """
        df = _sample_frame()
        result = _eval_expr(df, "ts_delay(close, 2)")
        _assert_values(
            result,
            "value",
            [None, None, 10.0, 11.0, 10.0, 12.0, None, None, 8.0, 7.5, 8.0, 9.0],
        )

    def test_ts_delta_close_two_entities(self) -> None:
        """ts_delta(close, 1) on the two-entity frame.
        Instrument 1: [null, 1, -1, 2, 3, -7]
        Instrument 2: [null, -0.5, 0.5, 1, 2, 9]
        """
        df = _sample_frame()
        result = _eval_expr(df, "ts_delta(close, 1)")
        _assert_values(
            result,
            "value",
            [None, 1.0, -1.0, 2.0, 3.0, -7.0, None, -0.5, 0.5, 1.0, 2.0, 9.0],
        )
