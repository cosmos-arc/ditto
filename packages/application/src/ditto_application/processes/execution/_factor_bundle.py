"""Build PIT-aware strategy input bundles from compiled factor signals."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import TYPE_CHECKING

import polars as pl
from ditto_backtest.data_feed import DataFeed
from ditto_backtest.steps import StepContext
from ditto_kernel.identity import InstrumentId
from ditto_strategy.alpha.pipeline import StrategyInputBundle

from ditto_application.contracts import REGIME_DEFAULT_LOOKBACK
from ditto_application.exceptions import AppProcessError

if TYPE_CHECKING:
    from ditto_application.processes.execution.factor_bridge import (
        CompiledExpressions,
        FactorBridge,
    )

__all__ = ["build_factor_aware_bundle_builder", "build_factor_bundle"]


def register_factor_bridge_runtime_types(
    *,
    bridge_type: type[object],
    compiled_type: type[object],
) -> None:
    """Resolve public forward annotations after the bridge module is initialized."""
    globals()["FactorBridge"] = bridge_type
    globals()["CompiledExpressions"] = compiled_type


def build_factor_aware_bundle_builder(
    *,
    bridge: FactorBridge,
    compiled: CompiledExpressions,
    data_feed: DataFeed,
    strategy_id: str,
    run_id: str,
) -> Callable[[StepContext], StrategyInputBundle]:
    """Build a reusable factor-aware input-bundle factory for one run."""
    lookback_days = max(
        (expr.analysis.lookback for expr in compiled.expressions),
        default=REGIME_DEFAULT_LOOKBACK,
    )

    def _build(ctx: StepContext) -> StrategyInputBundle:
        return build_factor_bundle(
            ctx=ctx,
            strategy_id=strategy_id,
            run_id=run_id,
            bridge=bridge,
            compiled=compiled,
            data_feed=data_feed,
            lookback_days=lookback_days,
        )

    return _build


def build_factor_bundle(
    *,
    ctx: StepContext,
    strategy_id: str,
    run_id: str,
    bridge: FactorBridge,
    compiled: CompiledExpressions,
    data_feed: DataFeed,
    lookback_days: int,
) -> StrategyInputBundle:
    """Build one PIT-aware daily bundle and its compiled factor signal values."""
    slice_ = ctx.slice_
    if slice_ is None:
        msg = "slice_ required"
        raise AppProcessError(msg)
    bars = slice_.bars
    instrument_ids = list(bars.keys())

    instruments = pl.DataFrame({"instrument_id": instrument_ids})
    market_rows: list[dict[str, object]] = []
    for iid, bar in bars.items():
        market_rows.append(
            {
                "instrument_id": int(iid),
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
                "trade_date": ctx.time_context.trade_date,
            },
        )

    history_df = data_feed.get_history(
        instrument_ids,
        ctx.time_context.knowledge_date.isoformat(),
        lookback_days,
    )
    if not history_df.is_empty():
        market_rows.extend(
            history_df.select(
                "instrument_id",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "trade_date",
            ).to_dicts()
        )

    market_data = pl.DataFrame(market_rows)
    if "trade_date" in market_data.columns:
        market_data = market_data.sort("trade_date")

    market_data = _enrich_with_fundamentals(
        market_data,
        data_feed=data_feed,
        instrument_ids=instrument_ids,
        knowledge_date=ctx.time_context.knowledge_date,
        trade_date=ctx.time_context.trade_date,
    )
    market_data = _enrich_with_classification(
        market_data,
        data_feed=data_feed,
        instrument_ids=instrument_ids,
        knowledge_date=ctx.time_context.knowledge_date,
        trade_date=ctx.time_context.trade_date,
    )

    return StrategyInputBundle(
        trade_date=ctx.time_context.trade_date,
        strategy_id=strategy_id,
        run_id=run_id,
        instruments=instruments,
        market_data=market_data,
        signal_values=bridge.compute_signals(market_data, compiled),
        benchmark_close=getattr(slice_, "benchmark_close", None),
    )


def _enrich_with_fundamentals(
    market_data: pl.DataFrame,
    *,
    data_feed: DataFeed,
    instrument_ids: list[InstrumentId],
    knowledge_date: date,
    trade_date: str,
) -> pl.DataFrame:
    """Join the PIT fundamental snapshot to current-day rows."""
    if market_data.is_empty() or not instrument_ids:
        return market_data

    fundamental_df = data_feed.get_fundamental_snapshot(instrument_ids, knowledge_date)
    if fundamental_df.is_empty():
        return market_data

    today_mask = market_data["trade_date"] == trade_date
    today_rows = market_data.filter(today_mask)
    if today_rows.is_empty():
        return market_data

    history_rows = market_data.filter(~today_mask)
    today_rows = today_rows.join(fundamental_df, on="instrument_id", how="left")
    if "eps" in today_rows.columns and "close" in today_rows.columns:
        today_rows = today_rows.with_columns(
            pl.when(pl.col("eps") != 0)
            .then(pl.col("close") / pl.col("eps"))
            .otherwise(None)
            .cast(pl.Float64)
            .alias("pe_ratio"),
        )

    enriched = pl.concat([today_rows, history_rows], how="diagonal_relaxed")
    if "trade_date" in enriched.columns:
        enriched = enriched.sort("trade_date")
    return enriched


def _enrich_with_classification(
    market_data: pl.DataFrame,
    *,
    data_feed: DataFeed,
    instrument_ids: list[InstrumentId],
    knowledge_date: date,
    trade_date: str,
) -> pl.DataFrame:
    """Join the PIT classification snapshot to current-day rows."""
    if market_data.is_empty() or not instrument_ids:
        return market_data

    classification_df = data_feed.get_classification_snapshot(
        instrument_ids,
        knowledge_date,
    )
    if classification_df.is_empty():
        return market_data

    today_mask = market_data["trade_date"] == trade_date
    today_rows = market_data.filter(today_mask)
    if today_rows.is_empty():
        return market_data

    history_rows = market_data.filter(~today_mask)
    today_rows = today_rows.join(classification_df, on="instrument_id", how="left")

    enriched = pl.concat([today_rows, history_rows], how="diagonal_relaxed")
    if "trade_date" in enriched.columns:
        enriched = enriched.sort("trade_date")
    return enriched
