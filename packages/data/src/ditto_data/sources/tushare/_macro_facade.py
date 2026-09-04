"""Macro, FX, metal, and commodity facade for ``TushareSource``."""

from __future__ import annotations

from datetime import date

import polars as pl

from ditto_data.sources.tushare.adapters.fx import FxTushareAdapter
from ditto_data.sources.tushare.adapters.macro import MacroTushareAdapter
from ditto_data.sources.tushare.adapters.metal import MetalTushareAdapter
from ditto_data.sources.tushare.macro_source import (
    fetch_commodities,
    fetch_fx_daily,
    fetch_macro_indicators,
    fetch_macro_indicators_by_codes,
    fetch_macro_indicators_range,
    fetch_metal_daily,
)

__all__ = ["MacroFacade"]


class MacroFacade:
    """Group macro, FX, metal, and commodity operations by data domain."""

    def __init__(
        self,
        macro: MacroTushareAdapter,
        fx: FxTushareAdapter,
        metal: MetalTushareAdapter,
    ) -> None:
        self._macro = macro
        self._fx = fx
        self._metal = metal

    def fetch_macro_indicators(self, trade_date: str) -> pl.DataFrame:
        """Fetch macro indicator data."""
        return fetch_macro_indicators(self._macro, trade_date)

    def fetch_macro_indicators_range(
        self,
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        """Fetch macro indicator data over a bounded interval."""
        return fetch_macro_indicators_range(self._macro, start_date, end_date)

    def fetch_macro_indicators_by_codes(
        self,
        codes: list[str],
        start_date: str,
        end_date: str,
        *,
        observed_on: date | None = None,
    ) -> pl.DataFrame:
        """Fetch a provider observation snapshot for selected macro codes."""
        return fetch_macro_indicators_by_codes(
            self._macro,
            codes,
            start_date,
            end_date,
            observed_on=observed_on,
        )

    def fetch_fx_daily(
        self,
        ts_codes: list[str],
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        """Fetch FX daily data."""
        return fetch_fx_daily(
            self._fx,
            ts_codes=ts_codes,
            start_date=start_date,
            end_date=end_date,
        )

    def fetch_metal_daily(
        self,
        codes: list[str],
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        """Fetch precious-metal daily data."""
        return fetch_metal_daily(
            self._metal,
            codes=codes,
            start_date=start_date,
            end_date=end_date,
        )

    def fetch_commodities(
        self,
        codes: list[str],
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        """Return the Tushare unsupported-commodity result."""
        return fetch_commodities(codes, start_date, end_date)
