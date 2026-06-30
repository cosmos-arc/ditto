"""Unit tests for expression/codegen/_visitor.py edge cases.

Tests binary operators, unary not, identifier/feature nodes,
_compile_literal_or_reference, and error paths.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

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
    FeatureRefNode,
    IdentifierNode,
    NumberNode,
    StringNode,
    UnaryOpNode,
)
from ditto_features.expression.codegen import compile_expression
from ditto_features.expression.diagnostics import (
    ExpressionCompileError,
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


def _id(name: str) -> IdentifierNode:
    return IdentifierNode(name=name, span=_ZERO_SPAN)


def _feat(name: str) -> FeatureRefNode:
    return FeatureRefNode(name=name, span=_ZERO_SPAN)


def _make_spec() -> DerivedSpec:
    return DerivedSpec(
        id="test",
        version=1,
        role=DerivedRole.FEATURE,
        materialization_profile=MaterializationProfile.SERIES,
        expression="",
    )


def _compile(node) -> pl.Expr:
    return compile_expression(node, _make_spec(), source="test")


# ---------------------------------------------------------------------------
# Binary operators
# ---------------------------------------------------------------------------


class TestBinaryOperators:
    """Tests for all supported binary operators."""

    @pytest.mark.parametrize(
        ("op", "left", "right", "expected"),
        [
            ("+", 3.0, 2.0, 5.0),
            ("-", 3.0, 2.0, 1.0),
            ("*", 3.0, 2.0, 6.0),
            ("/", 6.0, 2.0, 3.0),
        ],
    )
    def test_arithmetic_ops(
        self, op: str, left: float, right: float, expected: float
    ) -> None:
        """Arithmetic binary operators produce correct results."""
        node = BinaryOpNode(
            operator=op, left=_num(left), right=_num(right), span=_ZERO_SPAN
        )
        expr = _compile(node)
        df = pl.DataFrame({"instrument_id": [1], "trade_date": [1]})
        result = df.select(expr.alias("result")).to_series().to_list()
        assert result[0] == pytest.approx(expected)

    def test_comparison_ops(self) -> None:
        """Comparison operators return boolean results."""
        for op, expected in [("<", True), ("<=", True), (">", False), (">=", False)]:
            node = BinaryOpNode(
                operator=op, left=_num(1.0), right=_num(2.0), span=_ZERO_SPAN
            )
            expr = _compile(node)
            df = pl.DataFrame({"instrument_id": [1], "trade_date": [1]})
            result = df.select(expr.alias("result")).to_series().to_list()
            assert result[0] == expected

    def test_equality_ops(self) -> None:
        """== and != operators work correctly."""
        eq_node = BinaryOpNode(
            operator="==", left=_num(1.0), right=_num(1.0), span=_ZERO_SPAN
        )
        ne_node = BinaryOpNode(
            operator="!=", left=_num(1.0), right=_num(2.0), span=_ZERO_SPAN
        )
        df = pl.DataFrame({"instrument_id": [1], "trade_date": [1]})
        assert df.select(_compile(eq_node)).to_series().to_list()[0] is True
        assert df.select(_compile(ne_node)).to_series().to_list()[0] is True

    def test_and_operator(self) -> None:
        """'and' operator performs logical AND."""
        node = BinaryOpNode(
            operator="and",
            left=BinaryOpNode(
                operator=">", left=_num(2.0), right=_num(1.0), span=_ZERO_SPAN
            ),
            right=BinaryOpNode(
                operator="<", left=_num(1.0), right=_num(2.0), span=_ZERO_SPAN
            ),
            span=_ZERO_SPAN,
        )
        expr = _compile(node)
        df = pl.DataFrame({"instrument_id": [1], "trade_date": [1]})
        result = df.select(expr.alias("result")).to_series().to_list()
        assert result[0] is True

    def test_or_operator(self) -> None:
        """'or' operator performs logical OR."""
        node = BinaryOpNode(
            operator="or",
            left=BinaryOpNode(
                operator=">", left=_num(1.0), right=_num(2.0), span=_ZERO_SPAN
            ),
            right=BinaryOpNode(
                operator="<", left=_num(1.0), right=_num(2.0), span=_ZERO_SPAN
            ),
            span=_ZERO_SPAN,
        )
        expr = _compile(node)
        df = pl.DataFrame({"instrument_id": [1], "trade_date": [1]})
        result = df.select(expr.alias("result")).to_series().to_list()
        assert result[0] is True

    def test_unsupported_binary_raises(self) -> None:
        """Unsupported binary operator raises ExpressionCompileError."""
        node = BinaryOpNode(
            operator="^", left=_num(1.0), right=_num(2.0), span=_ZERO_SPAN
        )
        with pytest.raises(ExpressionCompileError, match="unsupported binary operator"):
            _compile(node)


# ---------------------------------------------------------------------------
# Unary operators
# ---------------------------------------------------------------------------


class TestUnaryOperators:
    """Tests for unary operators."""

    def test_negation(self) -> None:
        """Unary minus negates the value."""
        node = UnaryOpNode(operator="-", operand=_num(5.0), span=_ZERO_SPAN)
        expr = _compile(node)
        df = pl.DataFrame({"instrument_id": [1], "trade_date": [1]})
        result = df.select(expr.alias("result")).to_series().to_list()
        assert result[0] == pytest.approx(-5.0)

    def test_not_operator(self) -> None:
        """Unary 'not' inverts boolean."""
        inner = BinaryOpNode(
            operator=">", left=_num(1.0), right=_num(2.0), span=_ZERO_SPAN
        )
        node = UnaryOpNode(operator="not", operand=inner, span=_ZERO_SPAN)
        expr = _compile(node)
        df = pl.DataFrame({"instrument_id": [1], "trade_date": [1]})
        result = df.select(expr.alias("result")).to_series().to_list()
        assert result[0] is True  # not(1 > 2) = not(False) = True

    def test_unsupported_unary_raises(self) -> None:
        """Unsupported unary operator raises ExpressionCompileError."""
        node = UnaryOpNode(operator="~", operand=_num(5.0), span=_ZERO_SPAN)
        with pytest.raises(ExpressionCompileError, match="unsupported unary operator"):
            _compile(node)


# ---------------------------------------------------------------------------
# Literal and reference nodes
# ---------------------------------------------------------------------------


class TestLiteralAndReferenceNodes:
    """Tests for _compile_literal_or_reference."""

    def test_integer_number_node(self) -> None:
        """Integer-valued NumberNode produces int literal."""
        node = _num(5.0)
        expr = _compile(node)
        df = pl.DataFrame({"instrument_id": [1], "trade_date": [1]})
        result = df.select(expr.alias("result")).to_series().to_list()
        assert result[0] == 5

    def test_float_number_node(self) -> None:
        """Float-valued NumberNode produces float literal."""
        node = _num(3.14)
        expr = _compile(node)
        df = pl.DataFrame({"instrument_id": [1], "trade_date": [1]})
        result = df.select(expr.alias("result")).to_series().to_list()
        assert result[0] == pytest.approx(3.14)

    def test_string_node(self) -> None:
        """StringNode produces string literal."""
        node = _str("hello")
        expr = _compile(node)
        df = pl.DataFrame({"instrument_id": [1], "trade_date": [1]})
        result = df.select(expr.alias("result")).to_series().to_list()
        assert result[0] == "hello"

    def test_identifier_node(self) -> None:
        """IdentifierNode produces column reference."""
        node = _id("close")
        expr = _compile(node)
        df = pl.DataFrame({"close": [42.0], "instrument_id": [1], "trade_date": [1]})
        result = df.select(expr.alias("result")).to_series().to_list()
        assert result[0] == 42.0

    def test_feature_ref_node(self) -> None:
        """FeatureRefNode produces column reference by name."""
        node = _feat("my_feature")
        expr = _compile(node)
        df = pl.DataFrame(
            {"my_feature": [99.0], "instrument_id": [1], "trade_date": [1]}
        )
        result = df.select(expr.alias("result")).to_series().to_list()
        assert result[0] == 99.0

    def test_column_ref_node(self) -> None:
        """ColumnRefNode produces column reference by column name."""
        node = _col("open")
        expr = _compile(node)
        df = pl.DataFrame({"open": [10.0], "instrument_id": [1], "trade_date": [1]})
        result = df.select(expr.alias("result")).to_series().to_list()
        assert result[0] == 10.0


# ---------------------------------------------------------------------------
# Unsupported node type
# ---------------------------------------------------------------------------


class TestUnsupportedNode:
    """Tests for unsupported AST node types."""

    def test_unknown_node_type_raises(self) -> None:
        """Unsupported AST node raises ExpressionCompileError."""

        @dataclass(frozen=True)
        class FakeNode:
            span: Span = _ZERO_SPAN

        node = cast(FakeNode, FakeNode())  # type: ignore[invalid-argument]
        with pytest.raises(ExpressionCompileError):
            _compile(node)


# ---------------------------------------------------------------------------
# Operator call validation
# ---------------------------------------------------------------------------


class TestOperatorCallValidation:
    """Tests for _validate_operator_call edge cases."""

    def test_unknown_operator_raises(self) -> None:
        """Unknown operator raises ExpressionCompileError."""
        node = CallNode(
            name="nonexistent_func",
            arguments=(_num(1.0),),
            span=_ZERO_SPAN,
        )
        with pytest.raises(ExpressionCompileError, match="unknown operator"):
            _compile(node)

    def test_wrong_arity_raises(self) -> None:
        """Wrong number of arguments raises ExpressionCompileError."""
        node = CallNode(
            name="abs",
            arguments=(_num(1.0), _num(2.0)),
            span=_ZERO_SPAN,
        )
        with pytest.raises(ExpressionCompileError, match="arguments"):
            _compile(node)

    def test_string_arg_in_ts_operator_raises(self) -> None:
        """String argument in ts_ operator raises ExpressionCompileError."""
        node = CallNode(
            name="ts_mean",
            arguments=(_col("close"), _str("bad")),
            span=_ZERO_SPAN,
        )
        with pytest.raises(ExpressionCompileError, match="must be numeric"):
            _compile(node)


# ---------------------------------------------------------------------------
# Rolling window operators via _builders dispatch
# ---------------------------------------------------------------------------


class TestRollingWindowOperators:
    """Tests for all rolling window operators via _WINDOW_KIND_BY_NAME."""

    @pytest.mark.parametrize(
        "op",
        [
            "ts_count",
            "ts_max",
            "ts_mean",
            "ts_median",
            "ts_min",
            "ts_std",
            "ts_sum",
            "ts_var",
        ],
    )
    def test_rolling_operator_produces_expr(self, op: str) -> None:
        """Each rolling window operator produces a valid expression."""
        node = CallNode(
            name=op,
            arguments=(_col("close"), _num(3)),
            span=_ZERO_SPAN,
        )
        expr = _compile(node)
        df = pl.DataFrame(
            {
                "close": [1.0, 2.0, 3.0, 4.0, 5.0],
                "instrument_id": [1, 1, 1, 1, 1],
                "trade_date": [1, 2, 3, 4, 5],
            }
        )
        result = df.select(expr.alias("result")).to_series().to_list()
        # shift(1) + rolling(3, min_samples=3) -> first non-null at index 3
        # Exception: ts_count counts non-nulls so may produce values earlier
        assert result[0] is None
        assert result[-1] is not None

    def test_ts_sum_values(self) -> None:
        """ts_sum computes correct rolling sum with shift(1)."""
        node = CallNode(
            name="ts_sum",
            arguments=(_col("close"), _num(3)),
            span=_ZERO_SPAN,
        )
        expr = _compile(node)
        df = pl.DataFrame(
            {
                "close": [1.0, 2.0, 3.0, 4.0, 5.0],
                "instrument_id": [1, 1, 1, 1, 1],
                "trade_date": [1, 2, 3, 4, 5],
            }
        )
        result = df.select(expr.alias("result")).to_series().to_list()
        # At index 3: shifted=[None,1,2,3], rolling_sum(3) on [1,2,3] = 6
        assert result[3] == pytest.approx(6.0)

    def test_ts_count_values(self) -> None:
        """ts_count counts non-null values in window."""
        node = CallNode(
            name="ts_count",
            arguments=(_col("close"), _num(3)),
            span=_ZERO_SPAN,
        )
        expr = _compile(node)
        df = pl.DataFrame(
            {
                "close": [1.0, 2.0, 3.0, 4.0, 5.0],
                "instrument_id": [1, 1, 1, 1, 1],
                "trade_date": [1, 2, 3, 4, 5],
            }
        )
        result = df.select(expr.alias("result")).to_series().to_list()
        # At index 3: shifted values [1,2,3], count of non-null = 3
        assert result[3] == 3.0
