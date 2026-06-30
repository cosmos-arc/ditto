"""Shared fixtures & helpers for D7 factor cross-check tests.

Under ``--import-mode=importlib`` the test directory is not on ``sys.path``, so
cross-file helper modules cannot be imported directly. Instead the hand-written
polars reference helpers (AST builders, engine ``compile_call`` and the
value-tolerant comparator) live here and are exposed to tests via the ``cx``
fixture. Reference implementations themselves stay in each test module — they
MUST be independent of the codegen engine (the system under test).
"""

from __future__ import annotations

import math
from types import SimpleNamespace

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
    ExpressionNode,
    NumberNode,
    StringNode,
)
from ditto_features.expression.codegen import compile_expression
from ditto_features.expression.diagnostics import SourcePosition, Span

ENTITY_KEYS: tuple[str, ...] = ("instrument_id",)
TIME_KEYS: tuple[str, ...] = ("trade_date",)

_ZERO_POS = SourcePosition(offset=0, line=1, column=1)
_ZERO_SPAN = Span(start=_ZERO_POS, end=_ZERO_POS)


def _col(column: str) -> ColumnRefNode:
    return ColumnRefNode(dataset="market", column=column, span=_ZERO_SPAN)


def _num(value: float) -> NumberNode:
    return NumberNode(value=value, span=_ZERO_SPAN)


def _lit_str(value: str) -> StringNode:
    return StringNode(value=value, span=_ZERO_SPAN)


def _binary(operator: str, left: ExpressionNode, right: ExpressionNode) -> BinaryOpNode:
    return BinaryOpNode(operator=operator, left=left, right=right, span=_ZERO_SPAN)


def _spec() -> DerivedSpec:
    return DerivedSpec(
        id="crosscheck",
        version=1,
        role=DerivedRole.FEATURE,
        materialization_profile=MaterializationProfile.SERIES,
        expression="",
    )


def _call_node(name: str, *arguments: ExpressionNode) -> CallNode:
    return CallNode(name=name, arguments=tuple(arguments), span=_ZERO_SPAN)


def _compile_call(name: str, *arguments: ExpressionNode) -> pl.Expr:
    node = CallNode(name=name, arguments=tuple(arguments), span=_ZERO_SPAN)
    return compile_expression(node, _spec(), source=f"{name}(...)")


def _compile(node: ExpressionNode) -> pl.Expr:
    """Compile an arbitrary (possibly nested) AST node via the codegen engine."""
    return compile_expression(node, _spec(), source="crosscheck")


def _assert_expr_matches_reference(
    df: pl.DataFrame,
    *,
    engine: pl.Expr,
    reference: pl.Expr,
    column: str = "_cmp",
) -> None:
    """Assert engine expression matches an independent polars reference.

    Tolerant of NaN (both must be NaN), null (both must be null) and float
    rounding (relative + absolute tolerance). Row-level divergence is reported
    with its index so PIT / window-edge leaks point at the offender.
    """
    engine_vals = df.select(engine.alias(column)).to_series().to_list()
    reference_vals = df.select(reference.alias(column)).to_series().to_list()
    assert len(engine_vals) == len(reference_vals)
    for index, (engine_val, reference_val) in enumerate(
        zip(engine_vals, reference_vals, strict=True)
    ):
        _assert_value_matches(index, engine_val, reference_val)


def _assert_value_matches(index: int, engine: object, reference: object) -> None:
    if engine is None or reference is None:
        null_msg = (
            f"row {index}: null mismatch engine={engine!r} reference={reference!r}"
        )
        assert engine is None, null_msg
        assert reference is None, null_msg
        return
    if isinstance(engine, float) and isinstance(reference, float):
        if math.isnan(engine) or math.isnan(reference):
            nan_msg = (
                f"row {index}: NaN mismatch engine={engine!r} reference={reference!r}"
            )
            assert math.isnan(engine), nan_msg
            assert math.isnan(reference), nan_msg
            return
        assert engine == pytest.approx(reference, rel=1e-6, abs=1e-9), (
            f"row {index}: engine={engine!r} reference={reference!r}"
        )
        return
    assert engine == reference, (
        f"row {index}: engine={engine!r} reference={reference!r}"
    )


@pytest.fixture
def sample_frame() -> pl.DataFrame:
    """Controlled 3-entity x 6-date frame, sorted by [instrument_id, trade_date].

    Within every trade_date the ordering is stable (close_A < close_B < close_C
    and volume_A < volume_B < volume_C), making cross-section reference values
    trivial to derive by hand, while across-date variation exercises time-series
    operators. ``nullable`` carries an explicit null pattern for coalesce /
    if_else / ts null-edge coverage.
    """
    return pl.DataFrame(
        {
            "instrument_id": [
                "A",
                "A",
                "A",
                "A",
                "A",
                "A",
                "B",
                "B",
                "B",
                "B",
                "B",
                "B",
                "C",
                "C",
                "C",
                "C",
                "C",
                "C",
            ],
            "trade_date": [1, 2, 3, 4, 5, 6] * 3,
            "close": [
                10.0,
                12.0,
                11.0,
                13.0,
                10.0,
                14.0,
                20.0,
                19.0,
                22.0,
                21.0,
                23.0,
                20.0,
                30.0,
                32.0,
                29.0,
                33.0,
                31.0,
                34.0,
            ],
            "volume": [
                100.0,
                120.0,
                110.0,
                130.0,
                100.0,
                140.0,
                200.0,
                190.0,
                220.0,
                210.0,
                230.0,
                200.0,
                300.0,
                320.0,
                290.0,
                330.0,
                310.0,
                340.0,
            ],
            "nullable": [
                1.0,
                None,
                3.0,
                None,
                5.0,
                6.0,
                None,
                2.0,
                None,
                4.0,
                None,
                6.0,
                1.0,
                2.0,
                None,
                None,
                5.0,
                1.0,
            ],
        }
    ).sort(["instrument_id", "trade_date"])


@pytest.fixture
def cx() -> SimpleNamespace:
    """Crosscheck helper namespace exposed to D7 test modules."""
    return SimpleNamespace(
        col=_col,
        num=_num,
        lit_str=_lit_str,
        binary=_binary,
        call_node=_call_node,
        compile_call=_compile_call,
        compile=_compile,
        assert_expr_matches_reference=_assert_expr_matches_reference,
        ENTITY_KEYS=ENTITY_KEYS,
        TIME_KEYS=TIME_KEYS,
    )
