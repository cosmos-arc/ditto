"""D7 cross-check: scalar operators vs independent polars reference.

Each reference is hand-written polars, fully independent of the codegen engine.
Divergence flags a codegen mapping bug (wrong method, wrong argument order,
wrong literal handling). Covers positive / negative / fractional inputs and
explicit nulls.
"""

from __future__ import annotations

from types import SimpleNamespace

import polars as pl
import pytest

_UNARY_REFERENCES = {
    "abs": lambda e: e.abs(),
    "ceil": lambda e: e.ceil(),
    "exp": lambda e: e.exp(),
    "floor": lambda e: e.floor(),
    "log": lambda e: e.log(),
}


@pytest.mark.parametrize("name", list(_UNARY_REFERENCES))
def test_unary_scalar_matches_reference(name: str, cx: SimpleNamespace) -> None:
    """abs/ceil/exp/floor/log across positive, negative and fractional inputs."""
    df = pl.DataFrame({"x": [1.0, -2.5, 0.5, 10.0, -0.1]})
    engine = cx.compile_call(name, cx.col("x"))
    reference = _UNARY_REFERENCES[name](pl.col("x"))
    cx.assert_expr_matches_reference(df, engine=engine, reference=reference)


def test_round_matches_reference(cx: SimpleNamespace) -> None:
    df = pl.DataFrame({"x": [3.14159, 2.71828, 1.25, -0.9]})
    engine = cx.compile_call("round", cx.col("x"), cx.num(2))
    reference = pl.col("x").round(2)
    cx.assert_expr_matches_reference(df, engine=engine, reference=reference)


def test_clip_matches_reference(cx: SimpleNamespace) -> None:
    df = pl.DataFrame({"x": [-5.0, 0.0, 50.0, 100.0, 150.0]})
    engine = cx.compile_call("clip", cx.col("x"), cx.num(0.0), cx.num(100.0))
    reference = pl.col("x").clip(0.0, 100.0)
    cx.assert_expr_matches_reference(df, engine=engine, reference=reference)


def test_if_else_matches_reference(cx: SimpleNamespace) -> None:
    df = pl.DataFrame({"x": [1.0, 5.0, -3.0, 8.0, -0.5]})
    condition = cx.binary(">", cx.col("x"), cx.num(0.0))
    engine = cx.compile_call("if_else", condition, cx.col("x"), cx.num(0.0))
    reference = pl.when(pl.col("x") > 0.0).then(pl.col("x")).otherwise(0.0)
    cx.assert_expr_matches_reference(df, engine=engine, reference=reference)


def test_coalesce_matches_reference(cx: SimpleNamespace) -> None:
    df = pl.DataFrame({"x": [None, 5.0, None, 8.0], "fallback": [42.0, 99.0, 7.0, 1.0]})
    engine = cx.compile_call("coalesce", cx.col("x"), cx.col("fallback"))
    reference = pl.coalesce(pl.col("x"), pl.col("fallback"))
    cx.assert_expr_matches_reference(df, engine=engine, reference=reference)
