"""Forward return computation service."""

from __future__ import annotations

from datetime import date, timedelta

import polars as pl

from ditto_data.services.market_service import MarketService

__all__ = ["ForwardReturnService"]


class ForwardReturnService:
    """
    Compute forward returns from market data.

    Wraps :class:`MarketService` to produce forward return series for
    factor evaluation.  For a given *holding_period* ``T``, the forward
    return at time ``t`` is ``close[t+T] / close[t] - 1``.

    The service delegates to :meth:`MarketService.get_stock_bars` or
    :meth:`MarketService.get_etf_bars` depending on *asset_class*,
    computes the shifted ratio, and drops the trailing ``T`` dates per
    instrument (where the forward return is undefined).
    """

    def __init__(self, market_service: MarketService) -> None:
        self._market_service = market_service

    def compute(
        self,
        asset_class: str,
        start: str,
        end: str,
        holding_period: int = 5,
        adj: str = "none",
    ) -> pl.DataFrame:
        """
        Compute forward return series.

        Args:
            asset_class: ``"stock"`` or ``"etf"``.
            start: Start date (``YYYY-MM-DD``).
            end: End date (``YYYY-MM-DD``).
            holding_period: Number of trading days to look ahead.
            adj: Adjustment type (``"none"``, ``"qfq"``, ``"hfq"``).

        Returns:
            ``pl.DataFrame[instrument_id, trade_date, forward_return]``
            with the last *holding_period* dates per instrument dropped.

        """
        # Fetch a wider range so that close[t+T] is available for the
        # requested end date.  We add a generous calendar buffer.
        extended_end = _extend_end_date(end, holding_period)

        if asset_class == "etf":
            bars = self._market_service.get_etf_bars(start, extended_end, adj=adj)
        else:
            bars = self._market_service.get_stock_bars(start, extended_end)

        if bars.is_empty() or "close" not in bars.columns:
            return pl.DataFrame(
                schema={
                    "instrument_id": pl.Int64,
                    "trade_date": pl.Utf8,
                    "forward_return": pl.Float64,
                },
            )

        result = (
            bars.sort(["instrument_id", "trade_date"])
            .with_columns(
                forward_return=(
                    pl.col("close").shift(-holding_period).over("instrument_id")
                    / pl.col("close")
                    - 1
                ),
            )
            .filter(pl.col("forward_return").is_not_null())
            .select("instrument_id", "trade_date", "forward_return")
        )

        # Trim to the original requested range (keep rows where trade_date
        # falls within [start, end]).
        return result.filter(
            (pl.col("trade_date") >= start) & (pl.col("trade_date") <= end),
        )


def _extend_end_date(end: str, holding_period: int) -> str:
    """
    Extend *end* by a generous calendar buffer.

    Trading calendars have roughly 5 out of 7 days, so we multiply the
    holding period by a calendar factor of 2 and add a small safety
    margin to ensure we capture enough future close prices.
    """
    try:
        end_date = date.fromisoformat(end[:10])
    except (ValueError, TypeError):
        return end
    extended = end_date + timedelta(days=holding_period * 2 + 10)
    return extended.isoformat()
