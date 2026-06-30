"""Unit tests for expression/codegen/_helpers.py.

Tests read_int_literal, read_float_literal, require_positive, and
read_window_at with various input types and edge cases.

Also includes extended tests for the expression/lexer.py token types
and expression/analyzer.py dependency collection.
"""

from __future__ import annotations

import pytest
from ditto_features.expression.ast import (
    ColumnRefNode,
    IdentifierNode,
    NumberNode,
    StringNode,
)
from ditto_features.expression.codegen._helpers import (
    read_float_literal,
    read_int_literal,
    read_window_at,
    require_positive,
)
from ditto_features.expression.diagnostics import (
    ExpressionCompileError,
    SourcePosition,
    Span,
)

_ZERO_POS = SourcePosition(offset=0, line=1, column=1)
_ZERO_SPAN: Span = Span(start=_ZERO_POS, end=_ZERO_POS)


def _num(value: float) -> NumberNode:
    return NumberNode(value=value, span=_ZERO_SPAN)


def _col(column: str) -> ColumnRefNode:
    return ColumnRefNode(dataset="market", column=column, span=_ZERO_SPAN)


def _str(value: str) -> StringNode:
    return StringNode(value=value, span=_ZERO_SPAN)


def _id(name: str) -> IdentifierNode:
    return IdentifierNode(name=name, span=_ZERO_SPAN)


# ---------------------------------------------------------------------------
# read_int_literal
# ---------------------------------------------------------------------------


class TestReadIntLiteral:
    """Tests for read_int_literal."""

    def test_integer_value(self) -> None:
        """Integer NumberNode returns int value."""
        args = (_num(5.0),)
        assert read_int_literal(args, 0, source="test") == 5

    def test_float_value_floored(self) -> None:
        """Float NumberNode is floored to int."""
        args = (_num(3.7),)
        assert read_int_literal(args, 0, source="test") == 3

    def test_negative_value(self) -> None:
        """Negative NumberNode is floored correctly (math.floor)."""
        args = (_num(-2.3),)
        # math.floor(-2.3) = -3 (floors toward negative infinity)
        assert read_int_literal(args, 0, source="test") == -3

    def test_non_number_raises(self) -> None:
        """Non-NumberNode raises ExpressionCompileError."""
        args = (_col("close"),)
        with pytest.raises(
            ExpressionCompileError, match="window size must be an integer"
        ):
            read_int_literal(args, 0, source="test")

    def test_string_node_raises(self) -> None:
        """StringNode raises ExpressionCompileError."""
        args = (_str("5"),)
        with pytest.raises(
            ExpressionCompileError, match="window size must be an integer"
        ):
            read_int_literal(args, 0, source="test")

    def test_identifier_node_raises(self) -> None:
        """IdentifierNode raises ExpressionCompileError."""
        args = (_id("x"),)
        with pytest.raises(
            ExpressionCompileError, match="window size must be an integer"
        ):
            read_int_literal(args, 0, source="test")

    def test_index_out_of_range_raises(self) -> None:
        """Index beyond arguments raises IndexError."""
        args = (_num(1.0),)
        with pytest.raises(IndexError):
            read_int_literal(args, 5, source="test")

    def test_zero_value(self) -> None:
        """Zero NumberNode returns 0."""
        args = (_num(0.0),)
        assert read_int_literal(args, 0, source="test") == 0

    def test_large_value(self) -> None:
        """Large NumberNode value is floored."""
        args = (_num(1000000.9),)
        assert read_int_literal(args, 0, source="test") == 1000000

    @pytest.mark.parametrize(
        ("value", "expected"), [(-1.0, -1), (0.0, 0), (1.0, 1), (10.5, 10)]
    )
    def test_various_values(self, value: float, expected: int) -> None:
        """Various numeric values produce correct floored ints."""
        args = (_num(value),)
        assert read_int_literal(args, 0, source="test") == expected


# ---------------------------------------------------------------------------
# read_float_literal
# ---------------------------------------------------------------------------


class TestReadFloatLiteral:
    """Tests for read_float_literal."""

    def test_integer_value(self) -> None:
        """Integer NumberNode returns float value."""
        args = (_num(5.0),)
        assert read_float_literal(args, 0, source="test") == 5.0

    def test_float_value(self) -> None:
        """Float NumberNode returns float value."""
        args = (_num(3.14),)
        assert read_float_literal(args, 0, source="test") == pytest.approx(3.14)

    def test_negative_value(self) -> None:
        """Negative NumberNode returns negative float."""
        args = (_num(-2.5),)
        assert read_float_literal(args, 0, source="test") == pytest.approx(-2.5)

    def test_non_number_raises(self) -> None:
        """Non-NumberNode raises ExpressionCompileError."""
        args = (_col("close"),)
        with pytest.raises(
            ExpressionCompileError, match="quantile value must be a number"
        ):
            read_float_literal(args, 0, source="test")

    def test_string_node_raises(self) -> None:
        """StringNode raises ExpressionCompileError."""
        args = (_str("0.5"),)
        with pytest.raises(
            ExpressionCompileError, match="quantile value must be a number"
        ):
            read_float_literal(args, 0, source="test")

    @pytest.mark.parametrize("value", [0.0, 0.25, 0.5, 0.75, 1.0])
    def test_quantile_values(self, value: float) -> None:
        """Typical quantile values are read correctly."""
        args = (_num(value),)
        assert read_float_literal(args, 0, source="test") == pytest.approx(value)


# ---------------------------------------------------------------------------
# require_positive
# ---------------------------------------------------------------------------


class TestRequirePositive:
    """Tests for require_positive."""

    def test_positive_passes(self) -> None:
        """Positive value does not raise."""
        require_positive(1, _ZERO_SPAN, source="test")

    def test_large_positive_passes(self) -> None:
        """Large positive value does not raise."""
        require_positive(1000, _ZERO_SPAN, source="test")

    def test_zero_raises(self) -> None:
        """Zero raises ExpressionCompileError."""
        with pytest.raises(ExpressionCompileError, match="must be positive"):
            require_positive(0, _ZERO_SPAN, source="test")

    def test_negative_raises(self) -> None:
        """Negative raises ExpressionCompileError."""
        with pytest.raises(ExpressionCompileError, match="must be positive"):
            require_positive(-1, _ZERO_SPAN, source="test")

    @pytest.mark.parametrize("value", [-100, -1, 0])
    def test_non_positive_raises(self, value: int) -> None:
        """All non-positive values raise."""
        with pytest.raises(ExpressionCompileError):
            require_positive(value, _ZERO_SPAN, source="test")

    @pytest.mark.parametrize("value", [1, 2, 10, 100])
    def test_positive_passes_all(self, value: int) -> None:
        """All positive values pass."""
        require_positive(value, _ZERO_SPAN, source="test")


# ---------------------------------------------------------------------------
# read_window_at
# ---------------------------------------------------------------------------


class TestReadWindowAt:
    """Tests for read_window_at (combines read_int_literal + require_positive)."""

    def test_valid_positive_window(self) -> None:
        """Valid positive window is returned."""
        args = (_col("close"), _num(5))
        assert read_window_at(args, 1, source="test") == 5

    def test_window_of_one(self) -> None:
        """Window of 1 is valid."""
        args = (_col("close"), _num(1))
        assert read_window_at(args, 1, source="test") == 1

    def test_window_of_zero_raises(self) -> None:
        """Window of 0 raises ExpressionCompileError."""
        args = (_col("close"), _num(0))
        with pytest.raises(ExpressionCompileError, match="must be positive"):
            read_window_at(args, 1, source="test")

    def test_negative_window_raises(self) -> None:
        """Negative window raises ExpressionCompileError."""
        args = (_col("close"), _num(-3))
        with pytest.raises(ExpressionCompileError, match="must be positive"):
            read_window_at(args, 1, source="test")

    def test_non_number_window_raises(self) -> None:
        """Non-number window raises ExpressionCompileError."""
        args = (_col("close"), _col("open"))
        with pytest.raises(
            ExpressionCompileError, match="window size must be an integer"
        ):
            read_window_at(args, 1, source="test")

    @pytest.mark.parametrize("window", [1, 2, 5, 10, 20, 60, 120, 250])
    def test_various_valid_windows(self, window: int) -> None:
        """Various valid window sizes."""
        args = (_col("close"), _num(float(window)))
        assert read_window_at(args, 1, source="test") == window

    def test_float_window_floored(self) -> None:
        """Float window value is floored."""
        args = (_col("close"), _num(5.9))
        assert read_window_at(args, 1, source="test") == 5

    def test_float_window_zero_after_floor_raises(self) -> None:
        """Float window that floors to 0 raises."""
        args = (_col("close"), _num(0.5))
        with pytest.raises(ExpressionCompileError, match="must be positive"):
            read_window_at(args, 1, source="test")


# ---------------------------------------------------------------------------
# Expression Lexer Token Types
# ---------------------------------------------------------------------------


class TestLexerTokenTypes:
    """Tests for expression/lexer.py token type coverage."""

    def test_lexer_import(self) -> None:
        """Lexer module can be imported."""
        from ditto_features.expression.lexer import tokenize

        assert callable(tokenize)

    def test_tokenize_simple_expression(self) -> None:
        """Simple expression tokenizes correctly."""
        from ditto_features.expression.lexer import tokenize

        tokens = tokenize("market.close + 1")
        assert len(tokens) > 0
        # Should contain: market, ., close, +, 1
        token_reprs = [str(t) for t in tokens]
        assert any("close" in r for r in token_reprs)

    def test_tokenize_number(self) -> None:
        """Number literal tokenizes correctly."""
        from ditto_features.expression.lexer import tokenize

        tokens = tokenize("42.5")
        assert len(tokens) >= 1

    def test_tokenize_function_call(self) -> None:
        """Function call tokenizes correctly."""
        from ditto_features.expression.lexer import tokenize

        tokens = tokenize("ts_mean(market.close, 5)")
        assert len(tokens) > 3  # name, (, arg, comma, arg, )

    def test_tokenize_empty_returns_eof(self) -> None:
        """Empty expression returns tuple with EOF token."""
        from ditto_features.expression.lexer import tokenize

        result = tokenize("")
        assert isinstance(result, tuple)
        # Should contain at least an EOF token
        assert len(result) >= 1

    def test_tokenize_string_literal(self) -> None:
        """String literal tokenizes correctly."""
        from ditto_features.expression.lexer import tokenize

        tokens = tokenize('"hello"')
        assert len(tokens) >= 1


# ---------------------------------------------------------------------------
# Expression Analyzer
# ---------------------------------------------------------------------------


class TestExpressionAnalyzer:
    """Tests for expression/analyzer.py analysis features."""

    def test_analyzer_import(self) -> None:
        """Analyzer module can be imported."""
        from ditto_features.expression.analyzer import analyze_expression

        assert callable(analyze_expression)

    def test_analyze_simple_expression(self) -> None:
        """Simple expression analysis returns analysis result."""
        from ditto_features.expression import ExpressionCompiler

        compiler = ExpressionCompiler()
        # Use the full compile pipeline to exercise analysis
        from ditto_features.derived_types import (
            DerivedRole,
            DerivedSpec,
            MaterializationProfile,
        )

        spec = DerivedSpec(
            id="test",
            version=1,
            role=DerivedRole.FEATURE,
            materialization_profile=MaterializationProfile.SERIES,
            expression="market.close + 1",
        )
        compiled = compiler.compile(spec)
        assert compiled is not None
        assert hasattr(compiled.analysis, "dependencies")

    def test_analyze_ts_function(self) -> None:
        """TS function analysis identifies dependencies."""
        from ditto_features.derived_types import (
            DerivedRole,
            DerivedSpec,
            MaterializationProfile,
        )
        from ditto_features.expression import ExpressionCompiler

        compiler = ExpressionCompiler()
        spec = DerivedSpec(
            id="test",
            version=1,
            role=DerivedRole.FEATURE,
            materialization_profile=MaterializationProfile.SERIES,
            expression="ts_mean(market.close, 5)",
        )
        compiled = compiler.compile(spec)
        assert "market.close" in compiled.analysis.dependencies

    def test_analyze_multiple_deps(self) -> None:
        """Expression with multiple dependencies."""
        from ditto_features.derived_types import (
            DerivedRole,
            DerivedSpec,
            MaterializationProfile,
        )
        from ditto_features.expression import ExpressionCompiler

        compiler = ExpressionCompiler()
        spec = DerivedSpec(
            id="test",
            version=1,
            role=DerivedRole.FEATURE,
            materialization_profile=MaterializationProfile.SERIES,
            expression="market.close + market.open",
        )
        compiled = compiler.compile(spec)
        deps = compiled.analysis.dependencies
        assert "market.close" in deps
        assert "market.open" in deps

    def test_analyze_operator_names(self) -> None:
        """Analysis identifies operator names."""
        from ditto_features.derived_types import (
            DerivedRole,
            DerivedSpec,
            MaterializationProfile,
        )
        from ditto_features.expression import ExpressionCompiler

        compiler = ExpressionCompiler()
        spec = DerivedSpec(
            id="test",
            version=1,
            role=DerivedRole.FEATURE,
            materialization_profile=MaterializationProfile.SERIES,
            expression="abs(market.close)",
        )
        compiled = compiler.compile(spec)
        assert "abs" in compiled.analysis.operator_names


# ---------------------------------------------------------------------------
# Expression Diagnostics
# ---------------------------------------------------------------------------


class TestExpressionDiagnostics:
    """Tests for expression/diagnostics.py error types."""

    def test_compile_error_creation(self) -> None:
        """ExpressionCompileError can be created via make_compile_error."""
        from ditto_features.expression.diagnostics import (
            ExpressionCompileError,
            SourcePosition,
            Span,
            make_compile_error,
        )

        span = Span(
            start=SourcePosition(offset=0, line=1, column=1),
            end=SourcePosition(offset=5, line=1, column=6),
        )
        error = make_compile_error(
            source="test_expr",
            message="test error",
            error_code="E001",
            span=span,
        )
        assert isinstance(error, ExpressionCompileError)
        assert "test error" in str(error)
        assert error.diagnostic.error_code == "E001"

    def test_compile_error_with_suggestions(self) -> None:
        """ExpressionCompileError can carry suggestions."""
        from ditto_features.expression.diagnostics import (
            SourcePosition,
            Span,
            make_compile_error,
        )

        span = Span(
            start=SourcePosition(offset=0, line=1, column=1),
            end=SourcePosition(offset=5, line=1, column=6),
        )
        error = make_compile_error(
            source="test",
            message="unknown op",
            error_code="E021",
            span=span,
            suggestions=("abs", "ceil"),
        )
        assert "abs" in error.diagnostic.suggestions
        assert "ceil" in error.diagnostic.suggestions

    def test_span_properties(self) -> None:
        """Span has start and end SourcePosition."""
        from ditto_features.expression.diagnostics import SourcePosition, Span

        start = SourcePosition(offset=0, line=1, column=1)
        end = SourcePosition(offset=5, line=1, column=6)
        span = Span(start=start, end=end)
        assert span.start.line == 1
        assert span.end.column == 6

    def test_make_compile_error(self) -> None:
        """make_compile_error creates ExpressionCompileError."""
        from ditto_features.expression.diagnostics import (
            ExpressionCompileError,
            SourcePosition,
            Span,
            make_compile_error,
        )

        span = Span(
            start=SourcePosition(offset=0, line=1, column=1),
            end=SourcePosition(offset=0, line=1, column=1),
        )
        error = make_compile_error(
            source="test",
            message="test error",
            error_code="E001",
            span=span,
        )
        assert isinstance(error, ExpressionCompileError)
