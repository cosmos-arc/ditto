"""Unit tests for market route handlers."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import cast
from unittest.mock import MagicMock, patch

import polars as pl
from ditto_application.queries.market import MarketQueryFacade
from ditto_apps.api.routes.market import post_bars
from ditto_apps.models.common import APIResponse
from ditto_apps.models.market import Bar, BarsQuery


async def _inline_to_thread(function: Callable[..., pl.DataFrame], /, *args, **kwargs):
    return function(*args, **kwargs)


class TestPostBarsHandler:
    """POST /market/bars handler behavior without TestClient/Dishka wiring."""

    def test_passes_maturity_opt_in_to_application_facade(self) -> None:
        """Market bars API forwards maturity opt-in, leaving policy to application."""
        facade = MagicMock(spec=MarketQueryFacade)
        facade.find_bars.return_value = pl.DataFrame()
        query = BarsQuery(
            instrument_ids=[1],
            asset_class="stock",
            allow_experimental_data=True,
        )
        handler = cast(
            Callable[..., Awaitable[APIResponse[list[Bar]]]],
            post_bars.__dict__["__dishka_orig_func__"],
        )

        with patch(
            "ditto_apps.api.routes.market.asyncio.to_thread",
            side_effect=_inline_to_thread,
        ):
            response = asyncio.run(handler(query=query, facade=facade))

        assert response.data == []
        call_kwargs = facade.find_bars.call_args.kwargs
        assert call_kwargs["asset_class"] == "stock"
        assert call_kwargs["allow_experimental_data"] is True
