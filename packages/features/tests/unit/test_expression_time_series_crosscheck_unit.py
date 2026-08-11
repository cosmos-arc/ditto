"""D7 cross-check: time-series operators vs independent polars reference.

Each reference is hand-written polars, fully independent of the codegen engine,
and **strictly replicates the engine's PIT semantics**: ``shift(1)`` first, then
the rolling/window op, then ``.over(entity_keys)`` — equivalent to
``rolling(window, closed="left")`` (see .claude/rules/pit.md). ``ts_delay`` /
``ts_delta`` / ``ts_pct_change`` shift by the user ``period`` (not a PIT guard).

A deliberate "wrong shift" reverse-check proves the reference's ``shift(1)`` is
load-bearing — drop it and the reference diverges from the engine (i.e. the
suite really would catch a PIT leak).
"""

from __future__ import annotations

from types import SimpleNamespace

import polars as pl
import pytest

_ENTITY = "instrument_id"


def _ts_delay(x: pl.Expr, period: int) -> pl.Expr:
    return x.shift(period).over(_ENTITY)


def _ts_delta(x: pl.Expr, period: int) -> pl.Expr:
    return x - x.shift(period).over(_ENTITY)


def _ts_pct_change(x: pl.Expr, period: int) -> pl.Expr:
    prev = x.shift(period).over(_ENTITY)
    return pl.when(prev == 0).then(0.0).otherwise(x / prev - 1)


def _ts_rank(x: pl.Expr, window: int) -> pl.Expr:
    def _rank_latest(s: pl.Series) -> float:
        valid = s.drop_nulls()
        latest = valid[-1]
        below = sum(value < latest for value in valid)
        equal = sum(value == latest for value in valid)
        return float(below + (equal + 1) / 2)

    shifted = x.shift(1)
    ranked = shifted.rolling_map(_rank_latest, window_size=window, min_samples=1).over(
        _ENTITY
    ) / float(window)
    position = pl.int_range(0, pl.len()).over(_ENTITY)
    return pl.when(position >= window - 1).then(ranked).otherwise(None)


def _ts_argmax(x: pl.Expr, window: int) -> pl.Expr:
    def _argmax(s: pl.Series) -> int:
        idx = s.arg_max()
        return idx if idx is not None else -1

    shifted = x.shift(1)
    return shifted.rolling_map(_argmax, window_size=window, min_samples=window).over(
        _ENTITY
    )


def _ts_argmin(x: pl.Expr, window: int) -> pl.Expr:
    def _argmin(s: pl.Series) -> int:
        idx = s.arg_min()
        return idx if idx is not None else -1

    shifted = x.shift(1)
    return shifted.rolling_map(_argmin, window_size=window, min_samples=window).over(
        _ENTITY
    )


def _ts_corr(x: pl.Expr, y: pl.Expr, window: int) -> pl.Expr:
    return pl.rolling_corr(
        x.shift(1), y.shift(1), window_size=window, min_samples=window
    ).over(_ENTITY)


def _ts_cov(x: pl.Expr, y: pl.Expr, window: int) -> pl.Expr:
    return pl.rolling_cov(
        x.shift(1), y.shift(1), window_size=window, min_samples=window
    ).over(_ENTITY)


def _ts_ema(x: pl.Expr, window: int) -> pl.Expr:
    return x.shift(1).ewm_mean(span=window, min_samples=1).over(_ENTITY)


def _ts_decay_linear(x: pl.Expr, window: int) -> pl.Expr:
    def _wma(s: pl.Series) -> float:
        valid = s.drop_nulls()
        if valid.is_empty():
            return float("nan")
        n = len(valid)
        weights = list(range(1, n + 1))
        total = n * (n + 1) // 2
        return sum(w * v for w, v in zip(weights, valid.to_list(), strict=True)) / total

    shifted = x.shift(1)
    return shifted.rolling_map(_wma, window_size=window, min_samples=window).over(
        _ENTITY
    )


def test_ts_delay_matches_reference(
    sample_frame: pl.DataFrame, cx: SimpleNamespace
) -> None:
    engine = cx.compile_call("ts_delay", cx.col("close"), cx.num(2))
    reference = _ts_delay(pl.col("close"), 2)
    cx.assert_expr_matches_reference(sample_frame, engine=engine, reference=reference)


def test_ts_delta_matches_reference(
    sample_frame: pl.DataFrame, cx: SimpleNamespace
) -> None:
    engine = cx.compile_call("ts_delta", cx.col("close"), cx.num(1))
    reference = _ts_delta(pl.col("close"), 1)
    cx.assert_expr_matches_reference(sample_frame, engine=engine, reference=reference)


def test_ts_pct_change_matches_reference(
    sample_frame: pl.DataFrame, cx: SimpleNamespace
) -> None:
    engine = cx.compile_call("ts_pct_change", cx.col("close"), cx.num(1))
    reference = _ts_pct_change(pl.col("close"), 1)
    cx.assert_expr_matches_reference(sample_frame, engine=engine, reference=reference)


def test_ts_rank_matches_reference(
    sample_frame: pl.DataFrame, cx: SimpleNamespace
) -> None:
    engine = cx.compile_call("ts_rank", cx.col("close"), cx.num(3))
    reference = _ts_rank(pl.col("close"), 3)
    cx.assert_expr_matches_reference(sample_frame, engine=engine, reference=reference)


def test_ts_argmax_matches_reference(
    sample_frame: pl.DataFrame, cx: SimpleNamespace
) -> None:
    engine = cx.compile_call("ts_argmax", cx.col("close"), cx.num(3))
    reference = _ts_argmax(pl.col("close"), 3)
    cx.assert_expr_matches_reference(sample_frame, engine=engine, reference=reference)


def test_ts_argmin_matches_reference(
    sample_frame: pl.DataFrame, cx: SimpleNamespace
) -> None:
    engine = cx.compile_call("ts_argmin", cx.col("close"), cx.num(3))
    reference = _ts_argmin(pl.col("close"), 3)
    cx.assert_expr_matches_reference(sample_frame, engine=engine, reference=reference)


def test_ts_corr_matches_reference(
    sample_frame: pl.DataFrame, cx: SimpleNamespace
) -> None:
    engine = cx.compile_call("ts_corr", cx.col("close"), cx.col("volume"), cx.num(3))
    reference = _ts_corr(pl.col("close"), pl.col("volume"), 3)
    cx.assert_expr_matches_reference(sample_frame, engine=engine, reference=reference)


def test_ts_cov_matches_reference(
    sample_frame: pl.DataFrame, cx: SimpleNamespace
) -> None:
    engine = cx.compile_call("ts_cov", cx.col("close"), cx.col("volume"), cx.num(3))
    reference = _ts_cov(pl.col("close"), pl.col("volume"), 3)
    cx.assert_expr_matches_reference(sample_frame, engine=engine, reference=reference)


def test_ts_ema_matches_reference(
    sample_frame: pl.DataFrame, cx: SimpleNamespace
) -> None:
    engine = cx.compile_call("ts_ema", cx.col("close"), cx.num(3))
    reference = _ts_ema(pl.col("close"), 3)
    cx.assert_expr_matches_reference(sample_frame, engine=engine, reference=reference)


def test_ts_decay_linear_matches_reference(
    sample_frame: pl.DataFrame, cx: SimpleNamespace
) -> None:
    engine = cx.compile_call("ts_decay_linear", cx.col("close"), cx.num(3))
    reference = _ts_decay_linear(pl.col("close"), 3)
    cx.assert_expr_matches_reference(sample_frame, engine=engine, reference=reference)


def test_reference_catches_missing_pit_shift(
    sample_frame: pl.DataFrame, cx: SimpleNamespace
) -> None:
    """Reverse-check: a reference that drops ``shift(1)`` (PIT leak) must diverge.

    The engine applies ``shift(1)`` (PIT-safe). If the reference forgot it, the
    window would include the current row T and the values would mismatch —
    proving the cross-check really detects PIT leaks rather than passing trivially.
    """
    engine = cx.compile_call("ts_rank", cx.col("close"), cx.num(3))
    leaky_reference = (
        pl.col("close")
        .rolling_rank(window_size=3, min_samples=3)
        .cast(pl.Float64)
        .over(_ENTITY)
        / 3
    )
    with pytest.raises(AssertionError):
        cx.assert_expr_matches_reference(
            sample_frame, engine=engine, reference=leaky_reference
        )
