"""Application process for market instrument completeness checks."""

from __future__ import annotations

from typing import cast

import polars as pl

from ditto_application.exceptions import AppProcessError
from ditto_application.processes.quality.types import (
    QualityCompletenessRequest,
    QualityCompletenessResult,
)
from ditto_application.queries.market import MarketQueryFacade

__all__ = ["QualityCompletenessService"]

_MARKET_BAR_ASSET_CLASS_BY_DATASET = {
    "stock_daily": "stock",
    "etf_daily": "etf",
    "index_daily": "index",
    "fx_daily": "fx",
    "commodity_daily": "commodity",
}


class QualityCompletenessService:
    """Compare expected instruments with one persisted market partition."""

    def __init__(self, *, market: MarketQueryFacade) -> None:
        self._market = market

    def run(self, request: QualityCompletenessRequest) -> QualityCompletenessResult:
        """Read one date and return deterministic missing/extra instrument sets."""
        frame = self._read_dataset(request)
        actual: set[int] = (
            set(cast(list[int], frame["instrument_id"].unique().to_list()))
            if not frame.is_empty()
            else set()
        )
        expected = set(request.expected_sids or ())
        return QualityCompletenessResult(
            trade_date=request.trade_date,
            dataset=request.dataset,
            expected_count=(
                len(request.expected_sids) if request.expected_sids else None
            ),
            actual_count=len(actual),
            missing_sids=tuple(sorted(expected - actual)),
            extra_sids=tuple(sorted(actual - expected)) if expected else (),
        )

    def _read_dataset(self, request: QualityCompletenessRequest) -> pl.DataFrame:
        if request.dataset == "adj_factor":
            return self._market.get_adj_factors(
                start=request.trade_date,
                end=request.trade_date,
                allow_experimental_data=True,
            )
        asset_class = _MARKET_BAR_ASSET_CLASS_BY_DATASET.get(request.dataset)
        if asset_class is None:
            raise AppProcessError(
                f"Completeness reader unsupported for dataset: {request.dataset}",
                field="dataset",
                value=request.dataset,
            )
        return self._market.find_bars(
            start=request.trade_date,
            end=request.trade_date,
            market_wide=request.market_wide,
            asset_class=asset_class,
            allow_experimental_data=True,
        )
