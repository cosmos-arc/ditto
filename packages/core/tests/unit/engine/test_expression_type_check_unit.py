"""Tests for lightweight expression type checking (analyzer-level diagnostics)."""

from __future__ import annotations

from ditto_core.engine.expression.analyzer import analyze_expression
from ditto_core.engine.expression.lexer import tokenize
from ditto_core.engine.expression.parser import ExpressionParser


def _parse(expression: str):
    """Parse an expression string into an AST."""
    tokens = tokenize(expression)
    return ExpressionParser(tokens, expression).parse()


def _analyze(expression: str):
    """Analyze an expression string and return the Analysis."""
    return analyze_expression(_parse(expression))


class TestTypeInferenceBasics:
    """Type inference should assign ExprType to each AST node."""

    def test_column_ref_inferred_as_float(self) -> None:
        """Column references should default to Float type."""
        analysis = _analyze("market.close")
        assert analysis.warnings == ()

    def test_number_literal_inferred_as_float(self) -> None:
        """Number literals should be inferred as Float type."""
        analysis = _analyze("100")
        assert analysis.warnings == ()

    def test_string_literal_inferred_as_string(self) -> None:
        """String literals should be inferred as String type."""
        analysis = _analyze('"hello"')
        assert analysis.warnings == ()

    def test_binary_op_combines_types(self) -> None:
        """Binary operations between float operands should produce Float."""
        analysis = _analyze("market.close / 100")
        assert analysis.warnings == ()


class TestTypeMismatchDiagnostics:
    """Type mismatches should emit W031 warnings in Analysis.warnings."""

    def test_cs_rank_string_literal_emits_warning(self) -> None:
        """cs_rank('string') should produce a type mismatch diagnostic."""
        analysis = _analyze('cs_rank("string")')
        assert len(analysis.warnings) == 1
        warning = analysis.warnings[0]
        assert warning.error_code == "W031_TYPE_MISMATCH"
        assert "numeric" in warning.message.lower()
        assert "string" in warning.message.lower()

    def test_cs_zscore_string_literal_emits_warning(self) -> None:
        """cs_zscore('string') should produce a type mismatch diagnostic."""
        analysis = _analyze('cs_zscore("string")')
        assert len(analysis.warnings) == 1
        assert analysis.warnings[0].error_code == "W031_TYPE_MISMATCH"

    def test_cs_scale_string_literal_emits_warning(self) -> None:
        """cs_scale('string') should produce a type mismatch diagnostic."""
        analysis = _analyze('cs_scale("string")')
        assert len(analysis.warnings) == 1
        assert analysis.warnings[0].error_code == "W031_TYPE_MISMATCH"

    def test_cs_demean_string_literal_emits_warning(self) -> None:
        """cs_demean('string') should produce a type mismatch diagnostic."""
        analysis = _analyze('cs_demean("string")')
        assert len(analysis.warnings) == 1
        assert analysis.warnings[0].error_code == "W031_TYPE_MISMATCH"

    def test_cs_winsorize_string_literal_emits_warning(self) -> None:
        """cs_winsorize('string') should produce a type mismatch diagnostic."""
        analysis = _analyze('cs_winsorize("string")')
        assert len(analysis.warnings) == 1
        assert analysis.warnings[0].error_code == "W031_TYPE_MISMATCH"

    def test_ts_rank_string_literal_emits_warning(self) -> None:
        """ts_rank('string', 5) should produce a type mismatch diagnostic."""
        analysis = _analyze('ts_rank("string", 5)')
        assert len(analysis.warnings) == 1
        assert analysis.warnings[0].error_code == "W031_TYPE_MISMATCH"


class TestValidExpressionsNoWarning:
    """Valid expressions should not produce any type mismatch diagnostics."""

    def test_cs_rank_column_ref_no_warning(self) -> None:
        """cs_rank(close) with a column reference should produce no warning."""
        analysis = _analyze("cs_rank(market.close)")
        assert analysis.warnings == ()

    def test_cs_rank_binary_expr_no_warning(self) -> None:
        """cs_rank(close / 100) should produce no warning."""
        analysis = _analyze("cs_rank(market.close / 100)")
        assert analysis.warnings == ()

    def test_cs_rank_number_literal_no_warning(self) -> None:
        """cs_rank(3.14) with a number literal should produce no warning."""
        analysis = _analyze("cs_rank(3.14)")
        assert analysis.warnings == ()

    def test_ts_mean_column_ref_no_warning(self) -> None:
        """ts_mean(close, 20) should produce no warning."""
        analysis = _analyze("ts_mean(market.close, 20)")
        assert analysis.warnings == ()

    def test_complex_expression_no_warning(self) -> None:
        """Complex nested expressions with valid types should not warn."""
        analysis = _analyze(
            "cs_rank(ts_delta(market.close, 2) / ts_mean(market.volume, 2))"
        )
        assert analysis.warnings == ()

    def test_abs_column_ref_no_warning(self) -> None:
        """abs(close) should produce no warning."""
        analysis = _analyze("abs(market.close)")
        assert analysis.warnings == ()

    def test_if_else_mixed_types_no_warning(self) -> None:
        """if_else with condition, numeric branches, and string branches is valid."""
        analysis = _analyze('if_else(market.close > 10, "block", "pass")')
        assert analysis.warnings == ()


class TestWarningMessageContent:
    """Warning messages should include the operator name and argument info."""

    def test_warning_includes_operator_name(self) -> None:
        """Warning message should name the offending operator."""
        analysis = _analyze('cs_rank("oops")')
        assert len(analysis.warnings) == 1
        assert "cs_rank" in analysis.warnings[0].message

    def test_warning_includes_argument_position(self) -> None:
        """Warning message should mention which argument has the problem."""
        analysis = _analyze('cs_rank("oops")')
        assert len(analysis.warnings) == 1
        assert "argument 0" in analysis.warnings[0].message


class TestMultipleWarningsInOneExpression:
    """Multiple type mismatches in one expression should all be reported."""

    def test_two_string_args_to_numeric_ops(self) -> None:
        """Both cs_rank and ts_mean with string args should produce two warnings."""
        analysis = _analyze('cs_rank("x") + ts_mean("y", 5)')
        type_warnings = [
            w for w in analysis.warnings if w.error_code == "W031_TYPE_MISMATCH"
        ]
        assert len(type_warnings) == 2
