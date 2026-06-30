"""Framework self-check for the D7 cross-check helpers.

Verifies the comparator and engine compilation helper behave as expected before
the per-operator cross-check suites rely on them.
"""

from __future__ import annotations

from types import SimpleNamespace

import polars as pl
import pytest


def test_assert_passes_when_engine_equals_reference(cx: SimpleNamespace) -> None:
    df = pl.DataFrame({"x": [1.0, -2.0, 3.0]})
    cx.assert_expr_matches_reference(
        df, engine=pl.col("x").abs(), reference=pl.col("x").abs()
    )


def test_assert_catches_a_known_mismatch(cx: SimpleNamespace) -> None:
    df = pl.DataFrame({"x": [1.0, 2.0, 3.0]})
    with pytest.raises(AssertionError, match="row 0"):
        cx.assert_expr_matches_reference(
            df, engine=pl.col("x"), reference=pl.col("x") + 1.0
        )


def test_assert_requires_both_null(cx: SimpleNamespace) -> None:
    df = pl.DataFrame({"x": [1.0, None, 3.0]})
    cx.assert_expr_matches_reference(df, engine=pl.col("x"), reference=pl.col("x"))
    with pytest.raises(AssertionError, match="null mismatch"):
        cx.assert_expr_matches_reference(
            df, engine=pl.col("x"), reference=pl.col("x").fill_null(0.0)
        )


def test_compile_call_matches_handwritten_abs_on_sample(
    sample_frame: pl.DataFrame,
    cx: SimpleNamespace,
) -> None:
    """Trivial case: engine abs(close) equals a hand-written polars abs."""
    engine = cx.compile_call("abs", cx.col("close"))
    reference = pl.col("close").abs()
    cx.assert_expr_matches_reference(sample_frame, engine=engine, reference=reference)
