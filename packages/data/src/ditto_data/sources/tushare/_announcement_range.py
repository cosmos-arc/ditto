"""Exact announcement-date range requests for sparse Tushare products."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta
from time import sleep

import polars as pl

from ditto_data.errors import SourceFetchError
from ditto_data.sources.tushare.adapters.fundamental import FundamentalTushareAdapter

_ANNOUNCEMENT_DATE_ATTEMPTS = 3
_ANNOUNCEMENT_RETRY_DELAY_SECONDS = 61.0


def _fetch_exact_announcement_date(
    fetch: Callable[..., pl.DataFrame],
    announcement_date: str,
) -> pl.DataFrame:
    """Retry one exact date after the client's bounded transport retries."""
    for attempt in range(1, _ANNOUNCEMENT_DATE_ATTEMPTS + 1):
        try:
            return fetch(ann_date=announcement_date)
        except SourceFetchError:
            if attempt == _ANNOUNCEMENT_DATE_ATTEMPTS:
                raise
            # Business-level quota errors arrive in successful HTTP responses.
            # Cross the provider minute boundary before retrying the exact date.
            sleep(_ANNOUNCEMENT_RETRY_DELAY_SECONDS)
    raise AssertionError("unreachable announcement-date retry state")


def _fetch_announcement_range(
    fetch: Callable[..., pl.DataFrame],
    *,
    dataset: str,
    start_date: str,
    end_date: str,
) -> pl.DataFrame:
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    if end < start:
        raise ValueError(f"{dataset} range end_date precedes start_date")
    frames: list[pl.DataFrame] = []
    current = start
    while current <= end:
        frames.append(_fetch_exact_announcement_date(fetch, current.strftime("%Y%m%d")))
        current += timedelta(days=1)
    non_empty = [frame for frame in frames if not frame.is_empty()]
    if non_empty:
        return pl.concat(non_empty, how="diagonal_relaxed").unique(maintain_order=True)
    return frames[0]


def fetch_dividend_range(
    adapter: FundamentalTushareAdapter,
    start_date: str,
    end_date: str,
) -> pl.DataFrame:
    """Fetch dividends through documented exact ``ann_date`` calls."""
    return _fetch_announcement_range(
        adapter.fetch_dividend,
        dataset="dividend",
        start_date=start_date,
        end_date=end_date,
    )


def fetch_corporate_actions_range(
    adapter: FundamentalTushareAdapter,
    start_date: str,
    end_date: str,
) -> pl.DataFrame:
    """Fetch corporate actions by exact knowledge date without PIT leakage."""
    return _fetch_announcement_range(
        adapter.fetch_corporate_actions,
        dataset="corporate-action",
        start_date=start_date,
        end_date=end_date,
    )
