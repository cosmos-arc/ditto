"""Time-series special operator builders for code generation."""

from __future__ import annotations

from collections.abc import Callable

import polars as pl

from ditto_features.expression.ast import ExpressionNode
from ditto_features.expression.codegen._helpers import read_window_at

__all__ = ["compile_time_series_special"]

# ---------------------------------------------------------------------------
# Time-series special operators
# ---------------------------------------------------------------------------


def _ts_delay(
    arguments: tuple[pl.Expr, ...],
    raw_arguments: tuple[ExpressionNode, ...],
    entity_keys: list[str],
    source: str,
) -> pl.Expr:
    period = read_window_at(raw_arguments, 1, source=source)
    return arguments[0].shift(period).over(entity_keys)


def _ts_delta(
    arguments: tuple[pl.Expr, ...],
    raw_arguments: tuple[ExpressionNode, ...],
    entity_keys: list[str],
    source: str,
) -> pl.Expr:
    period = read_window_at(raw_arguments, 1, source=source)
    return arguments[0] - arguments[0].shift(period).over(entity_keys)


def _ts_pct_change(
    arguments: tuple[pl.Expr, ...],
    raw_arguments: tuple[ExpressionNode, ...],
    entity_keys: list[str],
    source: str,
) -> pl.Expr:
    period = read_window_at(raw_arguments, 1, source=source)
    shifted = arguments[0].shift(period).over(entity_keys)
    return pl.when(shifted == 0).then(0.0).otherwise((arguments[0] / shifted) - 1)


def _ts_rank(
    arguments: tuple[pl.Expr, ...],
    raw_arguments: tuple[ExpressionNode, ...],
    entity_keys: list[str],
    source: str,
) -> pl.Expr:
    window = read_window_at(raw_arguments, 1, source=source)
    # PIT safety: shift(1) excludes current row T; Expr.rolling_rank has
    # no ``closed`` parameter, so shift is the sole defense.
    shifted = arguments[0].shift(1)
    return (
        shifted.rolling_rank(window_size=window, min_samples=window)
        .cast(pl.Float64)
        .over(entity_keys)
        / window
    )


def _ts_argmax(
    arguments: tuple[pl.Expr, ...],
    raw_arguments: tuple[ExpressionNode, ...],
    entity_keys: list[str],
    source: str,
) -> pl.Expr:
    window = read_window_at(raw_arguments, 1, source=source)
    # PIT safety: shift(1) excludes current row T; Expr.rolling_map has
    # no ``closed`` parameter, so shift is the sole defense.
    shifted = arguments[0].shift(1)

    def _rolling_argmax(s: pl.Series) -> int:
        idx = s.arg_max()
        return idx if idx is not None else -1

    return shifted.rolling_map(
        _rolling_argmax,
        window_size=window,
        min_samples=window,
    ).over(entity_keys)


def _ts_argmin(
    arguments: tuple[pl.Expr, ...],
    raw_arguments: tuple[ExpressionNode, ...],
    entity_keys: list[str],
    source: str,
) -> pl.Expr:
    window = read_window_at(raw_arguments, 1, source=source)
    # PIT safety: shift(1) excludes current row T; Expr.rolling_map has
    # no ``closed`` parameter, so shift is the sole defense.
    shifted = arguments[0].shift(1)

    def _rolling_argmin(s: pl.Series) -> int:
        idx = s.arg_min()
        return idx if idx is not None else -1

    return shifted.rolling_map(
        _rolling_argmin,
        window_size=window,
        min_samples=window,
    ).over(entity_keys)


def _ts_corr(
    arguments: tuple[pl.Expr, ...],
    raw_arguments: tuple[ExpressionNode, ...],
    entity_keys: list[str],
    source: str,
) -> pl.Expr:
    window = read_window_at(raw_arguments, 2, source=source)
    # PIT safety: shift(1) excludes current row T; pl.rolling_corr has no
    # ``closed`` parameter, so shift is the sole defense.
    shifted_x = arguments[0].shift(1)
    shifted_y = arguments[1].shift(1)
    return pl.rolling_corr(
        shifted_x,
        shifted_y,
        window_size=window,
        min_samples=window,
    ).over(entity_keys)


def _ts_cov(
    arguments: tuple[pl.Expr, ...],
    raw_arguments: tuple[ExpressionNode, ...],
    entity_keys: list[str],
    source: str,
) -> pl.Expr:
    window = read_window_at(raw_arguments, 2, source=source)
    # PIT safety: shift(1) excludes current row T; pl.rolling_cov has no
    # ``closed`` parameter, so shift is the sole defense.
    shifted_x = arguments[0].shift(1)
    shifted_y = arguments[1].shift(1)
    return pl.rolling_cov(
        shifted_x,
        shifted_y,
        window_size=window,
        min_samples=window,
    ).over(entity_keys)


def _ts_ema(
    arguments: tuple[pl.Expr, ...],
    raw_arguments: tuple[ExpressionNode, ...],
    entity_keys: list[str],
    source: str,
) -> pl.Expr:
    window = read_window_at(raw_arguments, 1, source=source)
    shifted = arguments[0].shift(1)
    return shifted.ewm_mean(span=window, min_samples=1).over(
        entity_keys,
    )


def _ts_decay_linear(
    arguments: tuple[pl.Expr, ...],
    raw_arguments: tuple[ExpressionNode, ...],
    entity_keys: list[str],
    source: str,
) -> pl.Expr:
    window = read_window_at(raw_arguments, 1, source=source)
    # PIT safety: shift(1) excludes current row T; Expr.rolling_map has
    # no ``closed`` parameter, so shift is the sole defense.
    shifted = arguments[0].shift(1)

    def _wma(s: pl.Series) -> float:
        valid = s.drop_nulls()
        if valid.is_empty():
            return float("nan")
        n = len(valid)
        weights = list(range(1, n + 1))
        total_weight = n * (n + 1) // 2
        return (
            sum(w * v for w, v in zip(weights, valid.to_list(), strict=True))
            / total_weight
        )

    return shifted.rolling_map(
        _wma,
        window_size=window,
        min_samples=window,
    ).over(entity_keys)


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------

type _TsSpecialFn = Callable[
    [tuple[pl.Expr, ...], tuple[ExpressionNode, ...], list[str], str],
    pl.Expr,
]

_TS_SPECIAL_DISPATCH: dict[str, _TsSpecialFn] = {
    "ts_delay": _ts_delay,
    "ts_delta": _ts_delta,
    "ts_pct_change": _ts_pct_change,
    "ts_rank": _ts_rank,
    "ts_argmax": _ts_argmax,
    "ts_argmin": _ts_argmin,
    "ts_corr": _ts_corr,
    "ts_cov": _ts_cov,
    "ts_ema": _ts_ema,
    "ts_decay_linear": _ts_decay_linear,
}


def compile_time_series_special(
    *,
    name: str,
    arguments: tuple[pl.Expr, ...],
    raw_arguments: tuple[ExpressionNode, ...],
    entity_keys: list[str],
    source: str,
) -> pl.Expr | None:
    handler = _TS_SPECIAL_DISPATCH.get(name)
    if handler is None:
        return None
    return handler(arguments, raw_arguments, entity_keys, source)
