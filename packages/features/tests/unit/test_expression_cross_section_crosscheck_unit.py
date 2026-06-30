"""D7 cross-check: cross-section operators vs independent polars reference.

References use the *correct* cross-section semantics — per trade_date grouping
via ``.over("trade_date")``. ``cs_rank`` in the engine historically omitted the
``.over`` (a real bug this suite was designed to catch); the multi-date
``sample_frame`` makes that divergence visible.
"""

from __future__ import annotations

from types import SimpleNamespace

import polars as pl
import pytest

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

    Single-date so the engine's whole-frame rank coincides with per-date rank;
    isolates the rank/len mapping from the multi-date cross-section defect.
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


@pytest.mark.xfail(
    reason=(
        "D7 known issue: cs_rank omits .over(time_keys), so on multi-date frames "
        "it ranks across all dates instead of per date. The correct fix is blocked "
        "by a polars limit — nested .over() with different group keys (cs over "
        "trade_date wrapping a ts over entity) returns all-null without intermediate "
        "materialization, and codegen emits one inlined expression, so every "
        "cs(ts(...)) factor (e.g. alpha.py cs_rank(ts_mean(...))) would silently go "
        "null. Real fix: codegen materializes ts results before cs ops."
    ),
    strict=False,
)
def test_cs_rank_multi_date_cross_section_known_issue(
    sample_frame: pl.DataFrame, cx: SimpleNamespace
) -> None:
    engine = cx.compile_call("cs_rank", cx.col("close"))
    reference = _cs_rank(pl.col("close"))
    cx.assert_expr_matches_reference(sample_frame, engine=engine, reference=reference)


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
