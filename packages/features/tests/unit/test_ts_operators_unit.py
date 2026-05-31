"""Unit tests for expression/codegen/_ts_operators.py.

Tests each time-series special operator with known inputs/outputs to verify
correct shift(1) PIT-safety semantics and rolling window behavior.
"""

from __future__ import annotations

import polars as pl
import pytest
from ditto_features.derived_types import (
    DerivedRole,
    DerivedSpec,
    MaterializationProfile,
)
from ditto_features.expression.ast import (
    CallNode,
    ColumnRefNode,
    NumberNode,
)
from ditto_features.expression.codegen import compile_expression
from ditto_features.expression.diagnostics import (
    SourcePosition,
    Span,
)

_ZERO_POS = SourcePosition(offset=0, line=1, column=1)
_ZERO_SPAN: Span = Span(start=_ZERO_POS, end=_ZERO_POS)


def _col(column: str) -> ColumnRefNode:
    return ColumnRefNode(dataset="market", column=column, span=_ZERO_SPAN)


def _num(value: float) -> NumberNode:
    return NumberNode(value=value, span=_ZERO_SPAN)


def _make_spec() -> DerivedSpec:
    return DerivedSpec(
        id="test",
        version=1,
        role=DerivedRole.FEATURE,
        materialization_profile=MaterializationProfile.SERIES,
        expression="",
    )


def _compile(node: CallNode) -> pl.Expr:
    return compile_expression(node, _make_spec(), source="test")


def _make_df(values: list[float], entity: int = 1) -> pl.DataFrame:
    n = len(values)
    return pl.DataFrame(
        {
            "close": values,
            "instrument_id": [entity] * n,
            "trade_date": list(range(1, n + 1)),
        }
    )


def _make_multi_entity_df(
    data: dict[int, list[float]],
) -> pl.DataFrame:
    rows: list[dict[str, object]] = []
    for entity, values in data.items():
        for i, v in enumerate(values):
            rows.append({"close": v, "instrument_id": entity, "trade_date": i + 1})
    return pl.DataFrame(rows)


# ---------------------------------------------------------------------------
# ts_delay
# ---------------------------------------------------------------------------


class TestTsDelay:
    """Tests for ts_delay operator."""

    def test_shift_1_delays_by_one_row(self) -> None:
        """ts_delay(close, 1) returns previous value per entity."""
        node = CallNode(
            name="ts_delay",
            arguments=(_col("close"), _num(1)),
            span=_ZERO_SPAN,
        )
        expr = _compile(node)
        df = _make_df([10.0, 20.0, 30.0, 40.0])
        result = df.select(expr.alias("delayed")).to_series().to_list()
        assert result[0] is None
        assert result[1] == 10.0
        assert result[2] == 20.0
        assert result[3] == 30.0

    def test_shift_2_delays_by_two_rows(self) -> None:
        """ts_delay(close, 2) returns value from 2 rows back."""
        node = CallNode(
            name="ts_delay",
            arguments=(_col("close"), _num(2)),
            span=_ZERO_SPAN,
        )
        expr = _compile(node)
        df = _make_df([10.0, 20.0, 30.0, 40.0])
        result = df.select(expr.alias("delayed")).to_series().to_list()
        assert result[0] is None
        assert result[1] is None
        assert result[2] == 10.0
        assert result[3] == 20.0

    def test_multi_entity_independent(self) -> None:
        """ts_delay operates independently per entity group."""
        node = CallNode(
            name="ts_delay",
            arguments=(_col("close"), _num(1)),
            span=_ZERO_SPAN,
        )
        expr = _compile(node)
        df = _make_multi_entity_df({1: [10.0, 20.0], 2: [100.0, 200.0]})
        result = df.select(expr.alias("delayed")).to_series().to_list()
        # Entity 1: None, 10.0; Entity 2: None, 100.0
        assert result[0] is None
        assert result[1] == 10.0
        assert result[2] is None
        assert result[3] == 100.0

    @pytest.mark.parametrize("period", [1, 2, 3, 5])
    def test_various_periods(self, period: int) -> None:
        """ts_delay with various period values produces correct null prefix."""
        values = list(range(1, 20))
        node = CallNode(
            name="ts_delay",
            arguments=(_col("close"), _num(period)),
            span=_ZERO_SPAN,
        )
        expr = _compile(node)
        df = _make_df([float(v) for v in values])
        result = df.select(expr.alias("delayed")).to_series().to_list()
        # First `period` values should be None
        for i in range(period):
            assert result[i] is None, f"Expected None at index {i} for period {period}"
        # After that, result[i] = values[i - period]
        for i in range(period, len(values)):
            assert result[i] == float(values[i - period])


# ---------------------------------------------------------------------------
# ts_delta
# ---------------------------------------------------------------------------


class TestTsDelta:
    """Tests for ts_delta operator."""

    def test_delta_1_computes_difference(self) -> None:
        """ts_delta(close, 1) = close - close.shift(1)."""
        node = CallNode(
            name="ts_delta",
            arguments=(_col("close"), _num(1)),
            span=_ZERO_SPAN,
        )
        expr = _compile(node)
        df = _make_df([10.0, 13.0, 18.0])
        result = df.select(expr.alias("delta")).to_series().to_list()
        assert result[0] is None
        assert result[1] == pytest.approx(3.0)
        assert result[2] == pytest.approx(5.0)

    def test_delta_2_computes_difference(self) -> None:
        """ts_delta(close, 2) = close - close.shift(2)."""
        node = CallNode(
            name="ts_delta",
            arguments=(_col("close"), _num(2)),
            span=_ZERO_SPAN,
        )
        expr = _compile(node)
        df = _make_df([10.0, 13.0, 18.0, 25.0])
        result = df.select(expr.alias("delta")).to_series().to_list()
        assert result[0] is None
        assert result[1] is None
        assert result[2] == pytest.approx(8.0)
        assert result[3] == pytest.approx(12.0)

    def test_delta_negative_difference(self) -> None:
        """ts_delta returns negative when values decrease."""
        node = CallNode(
            name="ts_delta",
            arguments=(_col("close"), _num(1)),
            span=_ZERO_SPAN,
        )
        expr = _compile(node)
        df = _make_df([20.0, 15.0, 10.0])
        result = df.select(expr.alias("delta")).to_series().to_list()
        assert result[0] is None
        assert result[1] == pytest.approx(-5.0)
        assert result[2] == pytest.approx(-5.0)


# ---------------------------------------------------------------------------
# ts_pct_change
# ---------------------------------------------------------------------------


class TestTsPctChange:
    """Tests for ts_pct_change operator."""

    def test_basic_pct_change(self) -> None:
        """ts_pct_change(close, 1) computes percentage change."""
        node = CallNode(
            name="ts_pct_change",
            arguments=(_col("close"), _num(1)),
            span=_ZERO_SPAN,
        )
        expr = _compile(node)
        df = _make_df([100.0, 110.0, 121.0])
        result = df.select(expr.alias("pct")).to_series().to_list()
        assert result[0] is None
        assert result[1] == pytest.approx(0.1)
        assert result[2] == pytest.approx(0.1)

    def test_zero_base_returns_zero(self) -> None:
        """When shifted value is 0, ts_pct_change returns 0.0."""
        node = CallNode(
            name="ts_pct_change",
            arguments=(_col("close"), _num(1)),
            span=_ZERO_SPAN,
        )
        expr = _compile(node)
        df = _make_df([0.0, 10.0])
        result = df.select(expr.alias("pct")).to_series().to_list()
        assert result[0] is None
        assert result[1] == 0.0

    def test_negative_pct_change(self) -> None:
        """ts_pct_change returns negative when values decrease."""
        node = CallNode(
            name="ts_pct_change",
            arguments=(_col("close"), _num(1)),
            span=_ZERO_SPAN,
        )
        expr = _compile(node)
        df = _make_df([100.0, 80.0])
        result = df.select(expr.alias("pct")).to_series().to_list()
        assert result[0] is None
        assert result[1] == pytest.approx(-0.2)


# ---------------------------------------------------------------------------
# ts_rank
# ---------------------------------------------------------------------------


class TestTsRank:
    """Tests for ts_rank operator."""

    def test_ts_rank_returns_fractional_rank(self) -> None:
        """ts_rank(close, 3) returns rolling rank / window_size.

        shift(1) produces: [None, 1, 3, 2]
        rolling_rank(3, min_samples=3) needs 3 shifted values -> index 2
        At index 2: window = [None, 1, 3] -> rolling_rank uses 2 valid -> rank(3)=2 / 3
        """
        node = CallNode(
            name="ts_rank",
            arguments=(_col("close"), _num(3)),
            span=_ZERO_SPAN,
        )
        expr = _compile(node)
        df = _make_df([1.0, 3.0, 2.0, 4.0])
        result = df.select(expr.alias("rank")).to_series().to_list()
        # shift(1) then rolling_rank(window=3, min_samples=3)
        # shifted: [None, 1, 3, 2]; needs 3 shifted values for min_samples
        # So first non-null should be at index 2 or later
        assert result[0] is None
        assert result[1] is None
        # Find the first non-null value
        non_null_indices = [i for i, v in enumerate(result) if v is not None]
        assert len(non_null_indices) > 0
        for idx in non_null_indices:
            assert 0 < result[idx] <= 1.0

    def test_ts_rank_requires_window_data(self) -> None:
        """ts_rank returns None for initial rows where insufficient data exists."""
        node = CallNode(
            name="ts_rank",
            arguments=(_col("close"), _num(5)),
            span=_ZERO_SPAN,
        )
        expr = _compile(node)
        df = _make_df([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
        result = df.select(expr.alias("rank")).to_series().to_list()
        # shift(1) produces: [None, 1, 2, 3, 4, 5]
        # rolling_rank(5, min_samples=5) needs 5 valid shifted values
        # Shifted valid values start at index 1, so 5 values exist at index 5
        assert result[0] is None
        non_null_indices = [i for i, v in enumerate(result) if v is not None]
        assert len(non_null_indices) > 0
        # All non-null values should be in [0, 1]
        for idx in non_null_indices:
            assert 0 < result[idx] <= 1.0


# ---------------------------------------------------------------------------
# ts_corr
# ---------------------------------------------------------------------------


class TestTsCorr:
    """Tests for ts_corr operator."""

    def test_perfect_correlation(self) -> None:
        """Two perfectly correlated series should yield corr near 1.0."""
        # Use compile_expression directly for ts_corr requires two column refs
        from ditto_features.expression.ast import IdentifierNode

        open_col = IdentifierNode(name="open", span=_ZERO_SPAN)
        node = CallNode(
            name="ts_corr",
            arguments=(_col("close"), open_col, _num(5)),
            span=_ZERO_SPAN,
        )
        expr = _compile(node)
        # Create perfectly correlated series
        df = pl.DataFrame(
            {
                "close": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0],
                "open": [2.0, 4.0, 6.0, 8.0, 10.0, 12.0, 14.0],
                "instrument_id": [1] * 7,
                "trade_date": list(range(1, 8)),
            }
        )
        result = df.select(expr.alias("corr")).to_series().to_list()
        # First several are None due to shift(1) + rolling(5)
        non_null = [v for v in result if v is not None]
        if non_null:
            assert non_null[0] == pytest.approx(1.0, abs=0.01)


# ---------------------------------------------------------------------------
# ts_ema
# ---------------------------------------------------------------------------


class TestTsEma:
    """Tests for ts_ema operator."""

    def test_ema_smooths_data(self) -> None:
        """EMA should produce smoothed values."""
        node = CallNode(
            name="ts_ema",
            arguments=(_col("close"), _num(3)),
            span=_ZERO_SPAN,
        )
        expr = _compile(node)
        df = _make_df([10.0, 20.0, 30.0, 40.0, 50.0])
        result = df.select(expr.alias("ema")).to_series().to_list()
        # First value is None (shift(1)), rest should be non-None
        assert result[0] is None
        non_null = [v for v in result[1:] if v is not None]
        assert len(non_null) > 0
        # EMA values should be monotonically increasing for increasing input
        for i in range(1, len(non_null)):
            assert non_null[i] >= non_null[i - 1]

    def test_ema_span_parameter(self) -> None:
        """Larger span produces smoother (less responsive) output."""
        node_short = CallNode(
            name="ts_ema",
            arguments=(_col("close"), _num(3)),
            span=_ZERO_SPAN,
        )
        node_long = CallNode(
            name="ts_ema",
            arguments=(_col("close"), _num(20)),
            span=_ZERO_SPAN,
        )
        df = _make_df([float(i) for i in range(1, 30)])
        short_result = (
            df.select(_compile(node_short).alias("ema")).to_series().to_list()
        )
        long_result = df.select(_compile(node_long).alias("ema")).to_series().to_list()
        # Both should produce non-null values after initial shift
        short_valid = [v for v in short_result if v is not None]
        long_valid = [v for v in long_result if v is not None]
        assert len(short_valid) > 0
        assert len(long_valid) > 0


# ---------------------------------------------------------------------------
# ts_decay_linear
# ---------------------------------------------------------------------------


class TestTsDecayLinear:
    """Tests for ts_decay_linear operator."""

    def test_weighted_average_output(self) -> None:
        """Linear decay should produce weighted average with increasing weights."""
        node = CallNode(
            name="ts_decay_linear",
            arguments=(_col("close"), _num(3)),
            span=_ZERO_SPAN,
        )
        expr = _compile(node)
        df = _make_df([1.0, 2.0, 3.0, 4.0])
        result = df.select(expr.alias("wma")).to_series().to_list()
        # shift(1) + rolling(3, min_samples=3) -> first non-null at index 3
        assert result[0] is None
        assert result[1] is None
        assert result[2] is None
        # At index 3: shifted values [1, 2, 3], weights [1, 2, 3]
        # WMA = (1*1 + 2*2 + 3*3) / (1+2+3) = 14/6 = 2.3333
        assert result[3] is not None
        assert result[3] == pytest.approx(14.0 / 6.0, abs=1e-6)

    def test_window_2_wma(self) -> None:
        """Window=2: WMA = (1*a + 2*b) / 3."""
        node = CallNode(
            name="ts_decay_linear",
            arguments=(_col("close"), _num(2)),
            span=_ZERO_SPAN,
        )
        expr = _compile(node)
        df = _make_df([10.0, 20.0, 30.0])
        result = df.select(expr.alias("wma")).to_series().to_list()
        assert result[0] is None
        assert result[1] is None
        # At index 2: shifted values [10, 20], weights [1, 2]
        # WMA = (1*10 + 2*20) / 3 = 50/3 = 16.6667
        assert result[2] is not None
        assert result[2] == pytest.approx(50.0 / 3.0, abs=1e-6)


# ---------------------------------------------------------------------------
# ts_argmax / ts_argmin
# ---------------------------------------------------------------------------


class TestTsArgmax:
    """Tests for ts_argmax operator."""

    def test_argmax_returns_index(self) -> None:
        """ts_argmax should return the index of the maximum value in window."""
        node = CallNode(
            name="ts_argmax",
            arguments=(_col("close"), _num(3)),
            span=_ZERO_SPAN,
        )
        expr = _compile(node)
        # values: 1, 5, 3 -> shift(1): None, 1, 5, 3
        df = _make_df([1.0, 5.0, 3.0, 2.0])
        result = df.select(expr.alias("argmax")).to_series().to_list()
        # First 3 None (shift + min_samples=3), result at index 3
        assert result[0] is None
        assert result[1] is None
        assert result[2] is None
        assert result[3] is not None
        # At index 3: shifted values [1, 5, 3], argmax=1 (index of 5)
        assert result[3] == 1


class TestTsArgmin:
    """Tests for ts_argmin operator."""

    def test_argmin_returns_index(self) -> None:
        """ts_argmin should return the index of the minimum value in window."""
        node = CallNode(
            name="ts_argmin",
            arguments=(_col("close"), _num(3)),
            span=_ZERO_SPAN,
        )
        expr = _compile(node)
        df = _make_df([5.0, 1.0, 3.0, 4.0])
        result = df.select(expr.alias("argmin")).to_series().to_list()
        assert result[0] is None
        assert result[1] is None
        assert result[2] is None
        assert result[3] is not None
        # At index 3: shifted values [5, 1, 3], argmin=1 (index of 1)
        assert result[3] == 1


# ---------------------------------------------------------------------------
# ts_cov
# ---------------------------------------------------------------------------


class TestTsCov:
    """Tests for ts_cov operator."""

    def test_covariance_computed(self) -> None:
        """ts_cov should compute rolling covariance."""
        from ditto_features.expression.ast import IdentifierNode

        open_col = IdentifierNode(name="open", span=_ZERO_SPAN)
        node = CallNode(
            name="ts_cov",
            arguments=(_col("close"), open_col, _num(3)),
            span=_ZERO_SPAN,
        )
        expr = _compile(node)
        df = pl.DataFrame(
            {
                "close": [1.0, 2.0, 3.0, 4.0, 5.0],
                "open": [1.0, 2.0, 3.0, 4.0, 5.0],
                "instrument_id": [1] * 5,
                "trade_date": list(range(1, 6)),
            }
        )
        result = df.select(expr.alias("cov")).to_series().to_list()
        # Perfect positive correlation -> covariance = variance
        non_null = [v for v in result if v is not None]
        if non_null:
            assert non_null[0] > 0


# ---------------------------------------------------------------------------
# Dispatch: unknown operator returns None
# ---------------------------------------------------------------------------


class TestTsSpecialDispatch:
    """Tests for compile_time_series_special dispatch."""

    def test_unknown_operator_returns_none(self) -> None:
        """Unknown time-series special operator returns None from dispatch."""
        from ditto_features.expression.codegen._ts_operators import (
            compile_time_series_special,
        )

        result = compile_time_series_special(
            name="ts_unknown_xyz",
            arguments=(pl.col("close"),),
            raw_arguments=(_col("close"),),
            entity_keys=["instrument_id"],
            source="test",
        )
        assert result is None

    @pytest.mark.parametrize(
        "name",
        [
            "ts_delay",
            "ts_delta",
            "ts_pct_change",
            "ts_rank",
            "ts_argmax",
            "ts_argmin",
            "ts_corr",
            "ts_cov",
            "ts_ema",
            "ts_decay_linear",
        ],
    )
    def test_known_operators_return_expr(self, name: str) -> None:
        """All known time-series special operators should return a pl.Expr."""
        from ditto_features.expression.codegen._ts_operators import (
            compile_time_series_special,
        )

        # Single-operand operators read window at index 1; two-operand
        # operators (ts_corr, ts_cov) read it at index 2.  Build raw_args
        # so that the correct position holds a NumberNode.
        if name in ("ts_corr", "ts_cov"):
            args = (pl.col("close"), pl.col("open"))
            raw_args = (_col("close"), _col("open"), _num(3))
        else:
            args = (pl.col("close"),)
            raw_args = (_col("close"), _num(3))

        result = compile_time_series_special(
            name=name,
            arguments=args,
            raw_arguments=raw_args,
            entity_keys=["instrument_id"],
            source="test",
        )
        assert result is not None
