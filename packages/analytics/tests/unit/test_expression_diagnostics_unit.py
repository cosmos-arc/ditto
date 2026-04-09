"""Tests for expression diagnostics and compile-time error reporting."""

from __future__ import annotations

import pytest
from ditto_analytics.expression import ExpressionCompiler
from ditto_analytics.expression.diagnostics import ExpressionCompileError
from ditto_kernel.specs import DerivedRole, DerivedSpec, MaterializationProfile


def _make_spec(expression: str) -> DerivedSpec:
    return DerivedSpec(
        id="factor.alpha_diagnostic",
        version=1,
        role=DerivedRole.FACTOR,
        materialization_profile=MaterializationProfile.SERIES,
        expression=expression,
    )


class TestExpressionDiagnostics:
    """Diagnostics should surface stable error codes, spans, and suggestions."""

    def test_unknown_operator_reports_suggestion_and_span(self) -> None:
        """Unknown operators should raise a semantic diagnostic with suggestions."""
        compiler = ExpressionCompiler()

        with pytest.raises(ExpressionCompileError) as exc_info:
            compiler.compile(_make_spec("ts_meanx(market.close, 20)"))

        diagnostic = exc_info.value.diagnostic
        assert diagnostic.error_code == "E021_UNKNOWN_OPERATOR"
        assert diagnostic.span.start.line == 1
        assert diagnostic.span.start.column == 1
        assert "ts_mean" in diagnostic.suggestions
        assert "did you mean 'ts_mean'" in str(exc_info.value)

    def test_window_argument_type_error_points_to_string_literal(self) -> None:
        """Window functions should reject string literals with a typed diagnostic."""
        compiler = ExpressionCompiler()

        with pytest.raises(ExpressionCompileError) as exc_info:
            compiler.compile(_make_spec('ts_mean(market.close, "20")'))

        diagnostic = exc_info.value.diagnostic
        assert diagnostic.error_code == "E031_TYPE_MISMATCH"
        assert diagnostic.span.start.line == 1
        assert diagnostic.span.start.column > 20
        assert "must be numeric" in diagnostic.message

    def test_unterminated_string_reports_lexical_error(self) -> None:
        """Lexer should emit a lexical diagnostic for unterminated strings."""
        compiler = ExpressionCompiler()

        with pytest.raises(ExpressionCompileError) as exc_info:
            compiler.compile(_make_spec('if_else(market.close > 0, "halt, "pass")'))

        diagnostic = exc_info.value.diagnostic
        assert diagnostic.error_code == "E002_UNTERMINATED_STRING"
        assert diagnostic.span.start.line == 1
        assert diagnostic.message == "unterminated string literal"
