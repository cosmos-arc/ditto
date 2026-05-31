"""Unit tests for expression/codegen/_cs_operators.py and _scalar_operators.py.

Tests cross-section operators (cs_rank, cs_scale, cs_zscore, cs_demean,
cs_winsorize, group_rank, group_zscore) and scalar operators (abs, ceil, exp,
floor, log, round, clip, if_else, coalesce, etc.) via the compile_expression
public API.
"""

from __future__ import annotations

import math

import polars as pl
import pytest
from ditto_features.derived_types import (
    DerivedRole,
    DerivedSpec,
    MaterializationProfile,
)
from ditto_features.expression.ast import (
    BinaryOpNode,
    CallNode,
    ColumnRefNode,
    NumberNode,
    StringNode,
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


def _str(value: str) -> StringNode:
    return StringNode(value=value, span=_ZERO_SPAN)


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


# ---------------------------------------------------------------------------
# cs_rank
# ---------------------------------------------------------------------------


class TestCsRank:
    """Tests for cs_rank cross-section operator."""

    def test_basic_ranking(self) -> None:
        """cs_rank returns ordinal rank / count."""
        node = CallNode(
            name="cs_rank",
            arguments=(_col("close"),),
            span=_ZERO_SPAN,
        )
        expr = _compile(node)
        df = pl.DataFrame(
            {
                "close": [3.0, 1.0, 2.0],
                "instrument_id": [1, 2, 3],
                "trade_date": [1, 1, 1],
            }
        )
        result = df.select(expr.alias("rank")).to_series().to_list()
        # ordinal ranks: 3, 1, 2 -> divided by 3
        assert result[0] == pytest.approx(3.0 / 3)
        assert result[1] == pytest.approx(1.0 / 3)
        assert result[2] == pytest.approx(2.0 / 3)

    def test_equal_values_rank(self) -> None:
        """Equal values get consecutive ordinal ranks."""
        node = CallNode(
            name="cs_rank",
            arguments=(_col("close"),),
            span=_ZERO_SPAN,
        )
        expr = _compile(node)
        df = pl.DataFrame(
            {
                "close": [5.0, 5.0, 5.0],
                "instrument_id": [1, 2, 3],
                "trade_date": [1, 1, 1],
            }
        )
        result = df.select(expr.alias("rank")).to_series().to_list()
        # All same value -> all get some rank / 3
        for v in result:
            assert 0 < v <= 1.0

    def test_single_entity(self) -> None:
        """Single entity gets rank 1/1 = 1.0."""
        node = CallNode(
            name="cs_rank",
            arguments=(_col("close"),),
            span=_ZERO_SPAN,
        )
        expr = _compile(node)
        df = pl.DataFrame({"close": [42.0], "instrument_id": [1], "trade_date": [1]})
        result = df.select(expr.alias("rank")).to_series().to_list()
        assert result[0] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# cs_scale
# ---------------------------------------------------------------------------


class TestCsScale:
    """Tests for cs_scale cross-section operator."""

    def test_basic_scaling(self) -> None:
        """cs_scale divides each value by the sum of absolute values."""
        node = CallNode(
            name="cs_scale",
            arguments=(_col("close"),),
            span=_ZERO_SPAN,
        )
        expr = _compile(node)
        df = pl.DataFrame(
            {
                "close": [3.0, 1.0, 2.0],
                "instrument_id": [1, 2, 3],
                "trade_date": [1, 1, 1],
            }
        )
        result = df.select(expr.alias("scaled")).to_series().to_list()
        total = 3.0 + 1.0 + 2.0
        assert result[0] == pytest.approx(3.0 / total)
        assert result[1] == pytest.approx(1.0 / total)
        assert result[2] == pytest.approx(2.0 / total)

    def test_zero_sum_returns_zero(self) -> None:
        """When all values are zero, cs_scale returns 0.0."""
        node = CallNode(
            name="cs_scale",
            arguments=(_col("close"),),
            span=_ZERO_SPAN,
        )
        expr = _compile(node)
        df = pl.DataFrame(
            {
                "close": [0.0, 0.0, 0.0],
                "instrument_id": [1, 2, 3],
                "trade_date": [1, 1, 1],
            }
        )
        result = df.select(expr.alias("scaled")).to_series().to_list()
        assert all(v == 0.0 for v in result)


# ---------------------------------------------------------------------------
# cs_zscore
# ---------------------------------------------------------------------------


class TestCsZscore:
    """Tests for cs_zscore cross-section operator."""

    def test_basic_zscore(self) -> None:
        """cs_zscore returns (value - mean) / std per date group."""
        node = CallNode(
            name="cs_zscore",
            arguments=(_col("close"),),
            span=_ZERO_SPAN,
        )
        expr = _compile(node)
        df = pl.DataFrame(
            {
                "close": [1.0, 2.0, 3.0],
                "instrument_id": [1, 2, 3],
                "trade_date": [1, 1, 1],
            }
        )
        result = df.select(expr.alias("zscore")).to_series().to_list()
        # mean=2, std=1 => z-scores: -1, 0, 1
        assert result[0] == pytest.approx(-1.0, abs=0.01)
        assert result[1] == pytest.approx(0.0, abs=0.01)
        assert result[2] == pytest.approx(1.0, abs=0.01)

    def test_zero_std_returns_zero(self) -> None:
        """When all values are equal (std=0), cs_zscore returns 0.0."""
        node = CallNode(
            name="cs_zscore",
            arguments=(_col("close"),),
            span=_ZERO_SPAN,
        )
        expr = _compile(node)
        df = pl.DataFrame(
            {
                "close": [5.0, 5.0, 5.0],
                "instrument_id": [1, 2, 3],
                "trade_date": [1, 1, 1],
            }
        )
        result = df.select(expr.alias("zscore")).to_series().to_list()
        assert all(v == 0.0 for v in result)


# ---------------------------------------------------------------------------
# cs_demean
# ---------------------------------------------------------------------------


class TestCsDemean:
    """Tests for cs_demean cross-section operator."""

    def test_basic_demean(self) -> None:
        """cs_demean subtracts the group mean from each value."""
        node = CallNode(
            name="cs_demean",
            arguments=(_col("close"),),
            span=_ZERO_SPAN,
        )
        expr = _compile(node)
        df = pl.DataFrame(
            {
                "close": [10.0, 20.0, 30.0],
                "instrument_id": [1, 2, 3],
                "trade_date": [1, 1, 1],
            }
        )
        result = df.select(expr.alias("demean")).to_series().to_list()
        # mean = 20
        assert result[0] == pytest.approx(-10.0)
        assert result[1] == pytest.approx(0.0)
        assert result[2] == pytest.approx(10.0)

    def test_demean_sum_to_zero(self) -> None:
        """Demeaned values should sum to zero."""
        node = CallNode(
            name="cs_demean",
            arguments=(_col("close"),),
            span=_ZERO_SPAN,
        )
        expr = _compile(node)
        df = pl.DataFrame(
            {
                "close": [3.0, 7.0, 11.0],
                "instrument_id": [1, 2, 3],
                "trade_date": [1, 1, 1],
            }
        )
        result = df.select(expr.alias("demean")).to_series().to_list()
        assert sum(v for v in result) == pytest.approx(0.0, abs=1e-10)


# ---------------------------------------------------------------------------
# cs_winsorize (sigma mode, default)
# ---------------------------------------------------------------------------


class TestCsWinsorize:
    """Tests for cs_winsorize cross-section operator."""

    def test_sigma_mode_clips_outliers(self) -> None:
        """Sigma mode with n_sigma=1 clips at mean +/- 1*std."""
        node = CallNode(
            name="cs_winsorize",
            arguments=(_col("close"), _num(1)),
            span=_ZERO_SPAN,
        )
        expr = _compile(node)
        # Create data with an extreme outlier: mean=22, std≈44.3
        # 1-sigma upper bound = 22 + 44.3 ≈ 66.3, so 100.0 will be clipped
        df = pl.DataFrame(
            {
                "close": [1.0, 2.0, 3.0, 4.0, 100.0],
                "instrument_id": [1, 2, 3, 4, 5],
                "trade_date": [1, 1, 1, 1, 1],
            }
        )
        result = df.select(expr.alias("win")).to_series().to_list()
        # 100 should be clipped below 100
        assert result[-1] < 100.0

    def test_quantile_mode_clips(self) -> None:
        """Quantile mode clips at specified quantile bounds."""
        node = CallNode(
            name="cs_winsorize",
            arguments=(
                _col("close"),
                _str("quantile"),
                _num(0.25),
                _num(0.75),
            ),
            span=_ZERO_SPAN,
        )
        expr = _compile(node)
        df = pl.DataFrame(
            {
                "close": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 100.0],
                "instrument_id": list(range(10)),
                "trade_date": [1] * 10,
            }
        )
        result = df.select(expr.alias("win")).to_series().to_list()
        # The 100.0 outlier should be clipped down
        assert result[-1] < 100.0


# ---------------------------------------------------------------------------
# group_rank
# ---------------------------------------------------------------------------


class TestGroupRank:
    """Tests for group_rank grouped cross-section operator."""

    def test_basic_group_rank(self) -> None:
        """group_rank returns rank within group / group size."""
        node = CallNode(
            name="group_rank",
            arguments=(_col("close"), _col("sector")),
            span=_ZERO_SPAN,
        )
        expr = _compile(node)
        df = pl.DataFrame(
            {
                "close": [3.0, 1.0, 5.0, 2.0],
                "sector": ["A", "A", "B", "B"],
                "instrument_id": [1, 2, 3, 4],
                "trade_date": [1, 1, 1, 1],
            }
        )
        result = df.select(expr.alias("gr")).to_series().to_list()
        # Sector A: [3, 1] -> ranks [2, 1] / 2 = [1.0, 0.5]
        # Sector B: [5, 2] -> ranks [2, 1] / 2 = [1.0, 0.5]
        assert result[0] == pytest.approx(1.0)
        assert result[1] == pytest.approx(0.5)
        assert result[2] == pytest.approx(1.0)
        assert result[3] == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# group_zscore
# ---------------------------------------------------------------------------


class TestGroupZscore:
    """Tests for group_zscore grouped cross-section operator."""

    def test_basic_group_zscore(self) -> None:
        """group_zscore returns z-score within group.

        Note: polars std() uses ddof=1 by default, so for n=2 with values
        [1, 3], mean=2, std=sqrt(2).  z-scores: -1/sqrt(2), 1/sqrt(2).
        """
        node = CallNode(
            name="group_zscore",
            arguments=(_col("close"), _col("sector")),
            span=_ZERO_SPAN,
        )
        expr = _compile(node)
        df = pl.DataFrame(
            {
                "close": [1.0, 3.0, 10.0, 20.0],
                "sector": ["A", "A", "B", "B"],
                "instrument_id": [1, 2, 3, 4],
                "trade_date": [1, 1, 1, 1],
            }
        )
        result = df.select(expr.alias("gz")).to_series().to_list()
        # Sector A: mean=2, std(ddof=1)=sqrt(2) -> z: -1/sqrt(2), 1/sqrt(2)
        expected = 1.0 / math.sqrt(2)
        assert result[0] == pytest.approx(-expected, abs=0.01)
        assert result[1] == pytest.approx(expected, abs=0.01)


# ---------------------------------------------------------------------------
# Scalar unary operators
# ---------------------------------------------------------------------------


class TestScalarUnaryOperators:
    """Tests for scalar unary operators: abs, ceil, exp, floor, log, sign, sqrt."""

    @pytest.mark.parametrize(
        ("op", "input_val", "expected"),
        [
            ("abs", -5.0, 5.0),
            ("abs", 3.0, 3.0),
            ("ceil", 2.3, 3.0),
            ("ceil", -1.7, -1.0),
            ("floor", 2.7, 2.0),
            ("floor", -1.3, -2.0),
            ("sign", -5.0, -1.0),
            ("sign", 0.0, 0.0),
            ("sign", 3.0, 1.0),
        ],
    )
    def test_unary_integer_ops(
        self, op: str, input_val: float, expected: float
    ) -> None:
        """Scalar unary ops produce correct results on literals."""
        node = CallNode(
            name=op,
            arguments=(_num(input_val),),
            span=_ZERO_SPAN,
        )
        expr = _compile(node)
        df = pl.DataFrame({"instrument_id": [1], "trade_date": [1], "x": [0.0]})
        result = df.select(expr.alias("result")).to_series().to_list()
        assert result[0] == pytest.approx(expected, abs=1e-6)

    def test_exp_operator(self) -> None:
        """exp(1) = e."""
        node = CallNode(name="exp", arguments=(_num(1.0),), span=_ZERO_SPAN)
        expr = _compile(node)
        df = pl.DataFrame({"instrument_id": [1], "trade_date": [1], "x": [0.0]})
        result = df.select(expr.alias("result")).to_series().to_list()
        assert result[0] == pytest.approx(math.e, abs=1e-6)

    def test_log_operator(self) -> None:
        """log(e) = 1."""
        node = CallNode(name="log", arguments=(_num(math.e),), span=_ZERO_SPAN)
        expr = _compile(node)
        df = pl.DataFrame({"instrument_id": [1], "trade_date": [1], "x": [0.0]})
        result = df.select(expr.alias("result")).to_series().to_list()
        assert result[0] == pytest.approx(1.0, abs=1e-6)

    def test_log10_operator(self) -> None:
        """log10(100) = 2."""
        node = CallNode(name="log10", arguments=(_num(100.0),), span=_ZERO_SPAN)
        expr = _compile(node)
        df = pl.DataFrame({"instrument_id": [1], "trade_date": [1], "x": [0.0]})
        result = df.select(expr.alias("result")).to_series().to_list()
        assert result[0] == pytest.approx(2.0, abs=1e-6)

    def test_sqrt_operator(self) -> None:
        """sqrt(9) = 3."""
        node = CallNode(name="sqrt", arguments=(_num(9.0),), span=_ZERO_SPAN)
        expr = _compile(node)
        df = pl.DataFrame({"instrument_id": [1], "trade_date": [1], "x": [0.0]})
        result = df.select(expr.alias("result")).to_series().to_list()
        assert result[0] == pytest.approx(3.0, abs=1e-6)

    def test_unary_on_column(self) -> None:
        """Scalar unary ops work on column references too."""
        node = CallNode(
            name="abs",
            arguments=(_col("close"),),
            span=_ZERO_SPAN,
        )
        expr = _compile(node)
        df = pl.DataFrame(
            {
                "close": [-1.0, 2.0, -3.0],
                "instrument_id": [1, 1, 1],
                "trade_date": [1, 2, 3],
            }
        )
        result = df.select(expr.alias("result")).to_series().to_list()
        assert result == [1.0, 2.0, 3.0]


# ---------------------------------------------------------------------------
# Scalar binary operators: max2, min2, power
# ---------------------------------------------------------------------------


class TestScalarBinaryOperators:
    """Tests for max2, min2, power binary scalar operators."""

    def test_max2(self) -> None:
        """max2 returns the larger of two values."""
        node = CallNode(
            name="max2",
            arguments=(_num(3.0), _num(5.0)),
            span=_ZERO_SPAN,
        )
        expr = _compile(node)
        df = pl.DataFrame({"instrument_id": [1], "trade_date": [1], "x": [0.0]})
        result = df.select(expr.alias("result")).to_series().to_list()
        assert result[0] == pytest.approx(5.0)

    def test_min2(self) -> None:
        """min2 returns the smaller of two values."""
        node = CallNode(
            name="min2",
            arguments=(_num(3.0), _num(5.0)),
            span=_ZERO_SPAN,
        )
        expr = _compile(node)
        df = pl.DataFrame({"instrument_id": [1], "trade_date": [1], "x": [0.0]})
        result = df.select(expr.alias("result")).to_series().to_list()
        assert result[0] == pytest.approx(3.0)

    def test_power(self) -> None:
        """power(2, 3) = 8."""
        node = CallNode(
            name="power",
            arguments=(_num(2.0), _num(3.0)),
            span=_ZERO_SPAN,
        )
        expr = _compile(node)
        df = pl.DataFrame({"instrument_id": [1], "trade_date": [1], "x": [0.0]})
        result = df.select(expr.alias("result")).to_series().to_list()
        assert result[0] == pytest.approx(8.0)


# ---------------------------------------------------------------------------
# Scalar special operators: round, clip, if_else, coalesce
# ---------------------------------------------------------------------------


class TestScalarSpecialOperators:
    """Tests for round, clip, if_else, coalesce."""

    def test_round_2_decimals(self) -> None:
        """round(3.14159, 2) = 3.14."""
        node = CallNode(
            name="round",
            arguments=(_num(3.14159), _num(2)),
            span=_ZERO_SPAN,
        )
        expr = _compile(node)
        df = pl.DataFrame({"instrument_id": [1], "trade_date": [1], "x": [0.0]})
        result = df.select(expr.alias("result")).to_series().to_list()
        assert result[0] == pytest.approx(3.14, abs=0.01)

    def test_round_0_decimals(self) -> None:
        """round(3.7, 0) = 4."""
        node = CallNode(
            name="round",
            arguments=(_num(3.7), _num(0)),
            span=_ZERO_SPAN,
        )
        expr = _compile(node)
        df = pl.DataFrame({"instrument_id": [1], "trade_date": [1], "x": [0.0]})
        result = df.select(expr.alias("result")).to_series().to_list()
        assert result[0] == pytest.approx(4.0, abs=0.01)

    def test_clip_between_bounds(self) -> None:
        """clip clips values to [lower, upper]."""
        node = CallNode(
            name="clip",
            arguments=(_col("close"), _num(2.0), _num(5.0)),
            span=_ZERO_SPAN,
        )
        expr = _compile(node)
        df = pl.DataFrame(
            {
                "close": [1.0, 3.0, 7.0],
                "instrument_id": [1, 1, 1],
                "trade_date": [1, 2, 3],
            }
        )
        result = df.select(expr.alias("result")).to_series().to_list()
        assert result[0] == 2.0
        assert result[1] == 3.0
        assert result[2] == 5.0

    def test_if_else_true_branch(self) -> None:
        """if_else with true condition returns then-branch."""
        # Build: if_else(close > 3, close, 0)
        condition = BinaryOpNode(
            operator=">",
            left=_col("close"),
            right=_num(3.0),
            span=_ZERO_SPAN,
        )
        node = CallNode(
            name="if_else",
            arguments=(condition, _col("close"), _num(0.0)),
            span=_ZERO_SPAN,
        )
        expr = _compile(node)
        df = pl.DataFrame(
            {
                "close": [1.0, 5.0, 2.0, 8.0],
                "instrument_id": [1, 1, 1, 1],
                "trade_date": [1, 2, 3, 4],
            }
        )
        result = df.select(expr.alias("result")).to_series().to_list()
        assert result[0] == pytest.approx(0.0)
        assert result[1] == pytest.approx(5.0)
        assert result[2] == pytest.approx(0.0)
        assert result[3] == pytest.approx(8.0)

    def test_coalesce_first_non_null(self) -> None:
        """coalesce returns the first non-null value."""
        node = CallNode(
            name="coalesce",
            arguments=(_col("close"), _num(42.0)),
            span=_ZERO_SPAN,
        )
        expr = _compile(node)
        df = pl.DataFrame(
            {
                "close": [None, 5.0, None],
                "instrument_id": [1, 1, 1],
                "trade_date": [1, 2, 3],
            }
        )
        result = df.select(expr.alias("result")).to_series().to_list()
        assert result[0] == 42.0
        assert result[1] == 5.0
        assert result[2] == 42.0


# ---------------------------------------------------------------------------
# Dispatch: unknown operators
# ---------------------------------------------------------------------------


class TestCsDispatch:
    """Tests for cross-section operator dispatch."""

    def test_unknown_cs_operator_returns_none(self) -> None:
        """Unknown cross-section operator returns None from dispatch."""
        from ditto_features.expression.codegen._cs_operators import (
            compile_cross_section,
        )

        result = compile_cross_section(
            name="cs_unknown_xyz",
            arguments=(pl.col("close"),),
            raw_arguments=(_col("close"),),
            source="test",
            time_keys=["trade_date"],
        )
        assert result is None

    def test_unknown_grouped_operator_returns_none(self) -> None:
        """Unknown grouped cross-section operator returns None from dispatch."""
        from ditto_features.expression.codegen._cs_operators import (
            compile_grouped_cross_section,
        )

        result = compile_grouped_cross_section(
            name="group_unknown",
            arguments=(pl.col("close"), pl.col("sector")),
        )
        assert result is None

    def test_unknown_scalar_operator_returns_none(self) -> None:
        """Unknown scalar operator returns None from dispatch."""
        from ditto_features.expression.codegen._scalar_operators import compile_scalar

        result = compile_scalar(
            name="unknown_op",
            arguments=(pl.col("close"),),
            raw_arguments=(_col("close"),),
            source="test",
        )
        assert result is None
