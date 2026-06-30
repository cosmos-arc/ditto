"""D7 cross-check: composite (nested) expressions vs independent polars reference.

Compositions cover scalar(ts), cs(scalar), ts+binary+if_else, multi-arg
coalesce, and scalar-wrapped rolling-window / correlation ops. Combinations of
the form cs(ts(...)) are intentionally avoided: polars nested ``.over()`` with
different group keys returns all-null without materialization (see the cs_rank
known-issue note), which is a codegen-architecture matter outside D7 scope.
"""

from __future__ import annotations

from types import SimpleNamespace

import polars as pl

_ENTITY = "instrument_id"
_TIME = "trade_date"


def test_abs_of_ts_delta_matches_reference(
    sample_frame: pl.DataFrame, cx: SimpleNamespace
) -> None:
    """abs(ts_delta(close, 1)) — scalar wrapping a ts operator."""
    node = cx.call_node("abs", cx.call_node("ts_delta", cx.col("close"), cx.num(1)))
    engine = cx.compile(node)
    delta = pl.col("close") - pl.col("close").shift(1).over(_ENTITY)
    reference = delta.abs()
    cx.assert_expr_matches_reference(sample_frame, engine=engine, reference=reference)


def test_cs_zscore_of_abs_matches_reference(
    sample_frame: pl.DataFrame, cx: SimpleNamespace
) -> None:
    """cs_zscore(abs(close)) — cs wrapping a scalar (no ts, so no nested over)."""
    node = cx.call_node("cs_zscore", cx.call_node("abs", cx.col("close")))
    engine = cx.compile(node)
    x = pl.col("close").abs()
    mean = x.mean().over(_TIME)
    std = x.std().over(_TIME)
    reference = pl.when(std == 0).then(0.0).otherwise((x - mean) / std)
    cx.assert_expr_matches_reference(sample_frame, engine=engine, reference=reference)


def test_if_else_on_ts_delta_matches_reference(
    sample_frame: pl.DataFrame, cx: SimpleNamespace
) -> None:
    """if_else(ts_delta(close,1) > 0, volume, close) — binary + ts + if_else."""
    cond = cx.binary(
        ">", cx.call_node("ts_delta", cx.col("close"), cx.num(1)), cx.num(0)
    )
    node = cx.call_node("if_else", cond, cx.col("volume"), cx.col("close"))
    engine = cx.compile(node)
    delta = pl.col("close") - pl.col("close").shift(1).over(_ENTITY)
    reference = pl.when(delta > 0).then(pl.col("volume")).otherwise(pl.col("close"))
    cx.assert_expr_matches_reference(sample_frame, engine=engine, reference=reference)


def test_coalesce_of_ts_delays_matches_reference(
    sample_frame: pl.DataFrame, cx: SimpleNamespace
) -> None:
    """coalesce(ts_delay(close,2), ts_delay(close,1), close) — multi-arg coalesce."""
    node = cx.call_node(
        "coalesce",
        cx.call_node("ts_delay", cx.col("close"), cx.num(2)),
        cx.call_node("ts_delay", cx.col("close"), cx.num(1)),
        cx.col("close"),
    )
    engine = cx.compile(node)
    reference = pl.coalesce(
        pl.col("close").shift(2).over(_ENTITY),
        pl.col("close").shift(1).over(_ENTITY),
        pl.col("close"),
    )
    cx.assert_expr_matches_reference(sample_frame, engine=engine, reference=reference)


def test_round_of_ts_mean_matches_reference(
    sample_frame: pl.DataFrame, cx: SimpleNamespace
) -> None:
    """round(ts_mean(close, 3), 2) — scalar wrapping a rolling-window ts op."""
    node = cx.call_node(
        "round", cx.call_node("ts_mean", cx.col("close"), cx.num(3)), cx.num(2)
    )
    engine = cx.compile(node)
    mean = (
        pl.col("close")
        .shift(1)
        .rolling_mean(window_size=3, min_samples=3)
        .over(_ENTITY)
    )
    reference = mean.round(2)
    cx.assert_expr_matches_reference(sample_frame, engine=engine, reference=reference)


def test_clip_of_ts_corr_matches_reference(
    sample_frame: pl.DataFrame, cx: SimpleNamespace
) -> None:
    """clip(ts_corr(close, volume, 3), -1, 1) — scalar wrapping ts_corr."""
    node = cx.call_node(
        "clip",
        cx.call_node("ts_corr", cx.col("close"), cx.col("volume"), cx.num(3)),
        cx.num(-1),
        cx.num(1),
    )
    engine = cx.compile(node)
    corr = pl.rolling_corr(
        pl.col("close").shift(1),
        pl.col("volume").shift(1),
        window_size=3,
        min_samples=3,
    ).over(_ENTITY)
    reference = corr.clip(-1.0, 1.0)
    cx.assert_expr_matches_reference(sample_frame, engine=engine, reference=reference)


def test_abs_of_cs_zscore_minus_cs_demean_matches_reference(
    sample_frame: pl.DataFrame, cx: SimpleNamespace
) -> None:
    """abs(cs_zscore(close)) - cs_demean(volume) — composed cs + scalar ops."""
    node = cx.binary(
        "-",
        cx.call_node("abs", cx.call_node("cs_zscore", cx.col("close"))),
        cx.call_node("cs_demean", cx.col("volume")),
    )
    engine = cx.compile(node)
    x = pl.col("close")
    x_mean = x.mean().over(_TIME)
    x_std = x.std().over(_TIME)
    z = pl.when(x_std == 0).then(0.0).otherwise((x - x_mean) / x_std)
    reference = z.abs() - (pl.col("volume") - pl.col("volume").mean().over(_TIME))
    cx.assert_expr_matches_reference(sample_frame, engine=engine, reference=reference)
