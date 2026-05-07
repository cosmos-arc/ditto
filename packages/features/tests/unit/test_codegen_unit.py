"""Codegen 子模块独立单元测试.

测试 compile_expression 公开 API 及内部代码生成行为。
"""

from __future__ import annotations

import polars as pl
import pytest
from ditto_features.expression.ast import (
    BinaryOpNode,
    CallNode,
    ColumnRefNode,
    NumberNode,
    UnaryOpNode,
)
from ditto_features.expression.codegen import compile_expression
from ditto_features.expression.diagnostics import (
    SourcePosition,
    Span,
)
from ditto_kernel.strategy import DerivedRole, DerivedSpec, MaterializationProfile

_ZERO_POS = SourcePosition(offset=0, line=1, column=1)
_ZERO_SPAN: Span = Span(start=_ZERO_POS, end=_ZERO_POS)


def _col(dataset: str, column: str) -> ColumnRefNode:
    return ColumnRefNode(dataset=dataset, column=column, span=_ZERO_SPAN)


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


def _compile(node, source: str = "test") -> pl.Expr:
    return compile_expression(node, _make_spec(), source=source)


class TestCompileExpressionAPI:
    """compile_expression 公开 API 测试."""

    def test_simple_column_ref(self) -> None:
        node = _col("market", "close")
        expr = _compile(node)
        df = pl.DataFrame(
            {"close": [1.0, 2.0], "instrument_id": [1, 1], "trade_date": [1, 2]}
        )
        result = df.select(expr).to_series().to_list()
        assert result == [1.0, 2.0]

    def test_binary_addition(self) -> None:
        node = BinaryOpNode(
            operator="+",
            left=_col("market", "close"),
            right=_num(1.0),
            span=_ZERO_SPAN,
        )
        expr = _compile(node)
        df = pl.DataFrame(
            {"close": [1.0, 2.0], "instrument_id": [1, 1], "trade_date": [1, 2]}
        )
        result = df.select(expr).to_series().to_list()
        assert result == [2.0, 3.0]

    def test_binary_subtraction(self) -> None:
        node = BinaryOpNode(
            operator="-",
            left=_col("market", "close"),
            right=_col("market", "open"),
            span=_ZERO_SPAN,
        )
        expr = _compile(node)
        df = pl.DataFrame(
            {
                "close": [5.0, 3.0],
                "open": [2.0, 1.0],
                "instrument_id": [1, 1],
                "trade_date": [1, 2],
            }
        )
        result = df.select(expr).to_series().to_list()
        assert result == [3.0, 2.0]

    def test_unary_negation(self) -> None:
        node = UnaryOpNode(
            operator="-", operand=_col("market", "close"), span=_ZERO_SPAN
        )
        expr = _compile(node)
        df = pl.DataFrame(
            {"close": [1.0, -2.0], "instrument_id": [1, 1], "trade_date": [1, 2]}
        )
        result = df.select(expr).to_series().to_list()
        assert result == [-1.0, 2.0]

    def test_call_abs(self) -> None:
        node = CallNode(
            name="abs", arguments=(_col("market", "close"),), span=_ZERO_SPAN
        )
        expr = _compile(node)
        df = pl.DataFrame(
            {"close": [-1.0, 2.0], "instrument_id": [1, 1], "trade_date": [1, 2]}
        )
        result = df.select(expr).to_series().to_list()
        assert result == [1.0, 2.0]

    def test_call_sqrt(self) -> None:
        node = CallNode(name="sqrt", arguments=(_num(4.0),), span=_ZERO_SPAN)
        expr = _compile(node)
        df = pl.DataFrame({"instrument_id": [1], "trade_date": [1], "x": [0.0]})
        result = df.select(expr.alias("sqrt")).to_series().to_list()
        assert abs(result[0] - 2.0) < 1e-6

    def test_call_rolling_mean(self) -> None:
        node = CallNode(
            name="ts_mean",
            arguments=(_col("market", "close"), _num(3)),
            span=_ZERO_SPAN,
        )
        expr = _compile(node)
        df = pl.DataFrame(
            {
                "close": [1.0, 2.0, 3.0, 4.0],
                "instrument_id": [1, 1, 1, 1],
                "trade_date": [1, 2, 3, 4],
            }
        )
        result = df.select(expr).to_series().to_list()
        # shift(1) + rolling_mean(3, min_samples=3): first non-null at index 3
        assert result[0] is None
        assert result[1] is None
        assert result[2] is None
        assert abs(result[3] - 2.0) < 1e-6

    def test_call_cs_rank(self) -> None:
        node = CallNode(
            name="cs_rank",
            arguments=(_col("market", "close"),),
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
        result = df.select(expr).to_series().to_list()
        # cs_rank returns rank/len as fractional rank
        assert result == [3.0 / 3, 1.0 / 3, 2.0 / 3]

    def test_nested_binary(self) -> None:
        inner = BinaryOpNode(
            operator="-",
            left=_col("market", "close"),
            right=_col("market", "open"),
            span=_ZERO_SPAN,
        )
        node = BinaryOpNode(
            operator="/", left=inner, right=_col("market", "open"), span=_ZERO_SPAN
        )
        expr = _compile(node)
        df = pl.DataFrame(
            {
                "close": [11.0, 6.0],
                "open": [10.0, 2.0],
                "instrument_id": [1, 1],
                "trade_date": [1, 2],
            }
        )
        result = df.select(expr).to_series().to_list()
        assert abs(result[0] - 0.1) < 1e-6
        assert abs(result[1] - 2.0) < 1e-6

    def test_unknown_call_raises(self) -> None:
        node = CallNode(
            name="nonexistent_func_xyz",
            arguments=(_col("market", "close"),),
            span=_ZERO_SPAN,
        )
        with pytest.raises(Exception, match="unknown operator"):
            _compile(node)

    def test_unknown_literal_node_raises(self) -> None:
        """未知字面量 AST 节点应在 _compile 中直接抛出错误."""
        from dataclasses import dataclass
        from typing import cast as _cast

        from ditto_features.expression.ast import (
            ExpressionNode as _ExpressionNode,
        )
        from ditto_features.expression.diagnostics import (
            ExpressionCompileError,
        )

        @dataclass(frozen=True)
        class _FakeNode:
            span: Span = _ZERO_SPAN

        node = _cast(  # type: ignore[invalid-argument]
            _ExpressionNode, _FakeNode()
        )
        with pytest.raises(ExpressionCompileError):
            _compile(node)


class TestExpressionCompilerIntegration:
    """通过 ExpressionCompiler 端到端测试 codegen."""

    def test_compile_simple_expression(self) -> None:
        from ditto_features.expression import ExpressionCompiler

        compiler = ExpressionCompiler()
        spec = DerivedSpec(
            id="test_add",
            version=1,
            role=DerivedRole.FEATURE,
            materialization_profile=MaterializationProfile.SERIES,
            expression="market.close + 1",
        )
        compiled = compiler.compile(spec)
        df = pl.DataFrame(
            {"close": [1.0, 2.0], "instrument_id": [1, 1], "trade_date": [1, 2]}
        )
        result = df.select(compiled.expr).to_series().to_list()
        assert result == [2.0, 3.0]

    def test_compile_rolling(self) -> None:
        from ditto_features.expression import ExpressionCompiler

        compiler = ExpressionCompiler()
        spec = DerivedSpec(
            id="test_ts_mean",
            version=1,
            role=DerivedRole.FEATURE,
            materialization_profile=MaterializationProfile.SERIES,
            expression="ts_mean(market.close, 3)",
        )
        compiled = compiler.compile(spec)
        df = pl.DataFrame(
            {
                "close": [1.0, 2.0, 3.0, 4.0],
                "instrument_id": [1, 1, 1, 1],
                "trade_date": [1, 2, 3, 4],
            }
        )
        result = df.select(compiled.expr).to_series().to_list()
        # shift(1) + rolling_mean(3, min_samples=3): first non-null at index 3
        assert result[0] is None
        assert result[1] is None
        assert result[2] is None
        assert abs(result[3] - 2.0) < 1e-6
