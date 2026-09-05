"""D7 cross-check: cross-section operators vs independent polars reference.

References use per-trade-date grouping via ``.over("trade_date")``. The
multi-date ``cs_rank`` regression guards against the historical defect where
the engine ranked across the entire frame.
"""

from __future__ import annotations

from types import SimpleNamespace

import polars as pl
import pytest

_ENTITY = "instrument_id"
_TIME = "trade_date"


def _cs_rank(x: pl.Expr) -> pl.Expr:
    ranked = x.rank(method="ordinal").over(_TIME).cast(pl.Float64)
    group_len = pl.len().over(_TIME).cast(pl.Float64)
    return ranked / group_len


def _cs_scale(x: pl.Expr) -> pl.Expr:
    denom = x.abs().sum().over(_TIME)
    return pl.when(denom == 0).then(0.0).otherwise(x / denom)


def _cs_zscore(x: pl.Expr) -> pl.Expr:
    mean = x.mean().over(_TIME)
    std = x.std().over(_TIME)
    return pl.when(std == 0).then(0.0).otherwise((x - mean) / std)


def _cs_demean(x: pl.Expr) -> pl.Expr:
    return x - x.mean().over(_TIME)


def _cs_winsorize_sigma(x: pl.Expr, n_sigma: int = 3) -> pl.Expr:
    mean = x.mean().over(_TIME)
    std = x.std().over(_TIME)
    return x.clip(mean - n_sigma * std, mean + n_sigma * std)


def _cs_winsorize_quantile(x: pl.Expr, lo: float, hi: float) -> pl.Expr:
    q_lo = x.quantile(lo).over(_TIME)
    q_hi = x.quantile(hi).over(_TIME)
    return x.clip(q_lo, q_hi)


def test_cs_rank_single_date_matches_reference(cx: SimpleNamespace) -> None:
    """cs_rank basic mapping: ordinal rank / count within a single date group.

    A single date isolates the rank/len mapping from partition-boundary behavior.
    """
    df = pl.DataFrame(
        {
            "instrument_id": ["A", "B", "C", "D"],
            "trade_date": [1, 1, 1, 1],
            "close": [40.0, 10.0, 30.0, 20.0],
        }
    )
    engine = cx.compile_call("cs_rank", cx.col("close"))
    reference = _cs_rank(pl.col("close"))
    cx.assert_expr_matches_reference(df, engine=engine, reference=reference)


@pytest.mark.pit
def test_cs_rank_multi_date_matches_reference(
    sample_frame: pl.DataFrame, cx: SimpleNamespace
) -> None:
    """Later trade dates must not participate in an earlier date's rank."""
    engine = cx.compile_call("cs_rank", cx.col("close"))
    reference = _cs_rank(pl.col("close"))
    cx.assert_expr_matches_reference(sample_frame, engine=engine, reference=reference)


@pytest.mark.pit
def test_cs_rank_excludes_future_date_and_includes_same_date_peer(
    cx: SimpleNamespace,
) -> None:
    """A future sentinel is inert, while a same-date peer changes the rank."""
    decision_rows = pl.DataFrame(
        {
            "instrument_id": ["A", "B", "C"],
            "trade_date": [1, 1, 1],
            "close": [10.0, 20.0, 30.0],
        }
    )
    future_sentinel = pl.DataFrame(
        {
            "instrument_id": ["D", "E"],
            "trade_date": [2, 2],
            "close": [-1.0e12, 1.0e12],
        }
    )
    same_date_peer = pl.DataFrame(
        {"instrument_id": ["D"], "trade_date": [1], "close": [15.0]}
    )
    engine = cx.compile_call("cs_rank", cx.col("close"))

    baseline = decision_rows.select(engine.alias("rank"))["rank"].to_list()
    with_future = (
        pl.concat([decision_rows, future_sentinel])
        .select(engine.alias("rank"))["rank"]
        .to_list()
    )
    with_same_date_peer = (
        pl.concat([decision_rows, same_date_peer])
        .select(engine.alias("rank"))["rank"]
        .to_list()
    )

    assert with_future[: decision_rows.height] == baseline
    assert with_same_date_peer[: decision_rows.height] != baseline


def test_cs_rank_with_nulls_matches_reference(
    sample_frame: pl.DataFrame, cx: SimpleNamespace
) -> None:
    """Null inputs stay null and do not consume an ordinal rank within a date."""
    engine = cx.compile_call("cs_rank", cx.col("nullable"))
    reference = _cs_rank(pl.col("nullable"))
    cx.assert_expr_matches_reference(sample_frame, engine=engine, reference=reference)


def test_cs_rank_preserves_ordinal_tie_order(cx: SimpleNamespace) -> None:
    """Tied values retain their input order when the rank sort exceeds 20 rows."""
    df = pl.DataFrame(
        {
            "instrument_id": [str(index) for index in range(21)],
            "trade_date": [1] * 21,
            "close": [float(index % 2) for index in range(21)],
        }
    )
    engine = cx.compile_call("cs_rank", cx.col("close"))
    reference = _cs_rank(pl.col("close"))
    cx.assert_expr_matches_reference(df, engine=engine, reference=reference)


@pytest.mark.pit
def test_cs_rank_of_ts_mean_matches_materialized_reference(
    sample_frame: pl.DataFrame, cx: SimpleNamespace
) -> None:
    """A PIT-safe history expression remains rankable within each trade date."""
    node = cx.call_node("cs_rank", cx.call_node("ts_mean", cx.col("close"), cx.num(2)))
    engine = cx.compile(node)
    history = (
        pl.col("close")
        .shift(1)
        .rolling_mean(window_size=2, min_samples=2)
        .over(_ENTITY)
    )
    materialized = sample_frame.with_columns(history.alias("_history"))
    reference = _cs_rank(pl.col("_history"))
    cx.assert_expr_matches_reference(materialized, engine=engine, reference=reference)


def test_cs_scale_matches_reference(
    sample_frame: pl.DataFrame, cx: SimpleNamespace
) -> None:
    engine = cx.compile_call("cs_scale", cx.col("close"))
    reference = _cs_scale(pl.col("close"))
    cx.assert_expr_matches_reference(sample_frame, engine=engine, reference=reference)


def test_cs_zscore_matches_reference(
    sample_frame: pl.DataFrame, cx: SimpleNamespace
) -> None:
    engine = cx.compile_call("cs_zscore", cx.col("close"))
    reference = _cs_zscore(pl.col("close"))
    cx.assert_expr_matches_reference(sample_frame, engine=engine, reference=reference)


def test_cs_demean_matches_reference(
    sample_frame: pl.DataFrame, cx: SimpleNamespace
) -> None:
    engine = cx.compile_call("cs_demean", cx.col("close"))
    reference = _cs_demean(pl.col("close"))
    cx.assert_expr_matches_reference(sample_frame, engine=engine, reference=reference)


def test_cs_winsorize_sigma_matches_reference(
    sample_frame: pl.DataFrame, cx: SimpleNamespace
) -> None:
    engine = cx.compile_call("cs_winsorize", cx.col("close"), cx.num(1))
    reference = _cs_winsorize_sigma(pl.col("close"), n_sigma=1)
    cx.assert_expr_matches_reference(sample_frame, engine=engine, reference=reference)


def test_cs_winsorize_quantile_matches_reference(
    sample_frame: pl.DataFrame, cx: SimpleNamespace
) -> None:
    engine = cx.compile_call(
        "cs_winsorize",
        cx.col("close"),
        cx.lit_str("quantile"),
        cx.num(0.01),
        cx.num(0.99),
    )
    reference = _cs_winsorize_quantile(pl.col("close"), 0.01, 0.99)
    cx.assert_expr_matches_reference(sample_frame, engine=engine, reference=reference)


@pytest.fixture
def group_frame() -> pl.DataFrame:
    """4 instruments across 2 sectors over 2 dates, for grouped cross-sections."""
    return pl.DataFrame(
        {
            "instrument_id": ["A", "B", "C", "D"] * 2,
            "trade_date": [1, 1, 1, 1, 2, 2, 2, 2],
            "close": [10.0, 20.0, 30.0, 40.0, 12.0, 18.0, 33.0, 36.0],
            "sector": ["tech", "tech", "energy", "energy"] * 2,
        }
    )


def test_group_rank_matches_reference(
    group_frame: pl.DataFrame, cx: SimpleNamespace
) -> None:
    engine = cx.compile_call("group_rank", cx.col("close"), cx.col("sector"))
    sector = pl.col("sector")
    reference = pl.col("close").rank(method="ordinal").over(sector).cast(
        pl.Float64
    ) / pl.len().over(sector).cast(pl.Float64)
    cx.assert_expr_matches_reference(group_frame, engine=engine, reference=reference)


def test_group_zscore_matches_reference(
    group_frame: pl.DataFrame, cx: SimpleNamespace
) -> None:
    engine = cx.compile_call("group_zscore", cx.col("close"), cx.col("sector"))
    sector = pl.col("sector")
    mean = pl.col("close").mean().over(sector)
    std = pl.col("close").std().over(sector)
    reference = pl.when(std == 0).then(0.0).otherwise((pl.col("close") - mean) / std)
    cx.assert_expr_matches_reference(group_frame, engine=engine, reference=reference)
