"""Real canonical NAV storage reaches the existing HTTP display contract."""

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import polars as pl
import pytest
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import setup_dishka
from ditto_application.queries.market import MarketQueryFacade
from ditto_apps.api.routes.market import router
from ditto_data.observability.metrics import register_metrics
from ditto_data.services.deps import MarketReaders
from ditto_data.services.market_service import MarketService
from ditto_data.storage.market.etf.nav.nav_reader import EtfNavReader
from ditto_data.storage.market.etf.nav.nav_writer import EtfNavWriter
from ditto_platform.foundation import ParquetStore
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["stored", "empty", "missing_reader", "missing_value"])
async def test_nav_api_reads_canonical_unit_nav(tmp_path: Path, mode: str) -> None:
    register_metrics()
    store = ParquetStore(
        tmp_path, key_columns=("instrument_id", "trade_date"), date_column="trade_date"
    )
    if mode in {"stored", "missing_value"}:
        EtfNavWriter(store).write(
            pl.DataFrame(
                {
                    "instrument_id": [1, 1],
                    "trade_date": [date(2026, 9, 29), date(2026, 9, 30)],
                    "knowledge_date": [None, date(2026, 10, 2)],
                    "unit_nav": [4.4, 4.5] if mode == "stored" else [None, None],
                    "acc_nav": [99.0, 99.0],
                },
                schema_overrides={"unit_nav": pl.Float64},
            ),
            2026,
        )
    readers = MarketReaders(
        stock_bars=MagicMock(),
        stock_status=MagicMock(),
        stock_adj=MagicMock(),
        etf_bars=MagicMock(),
        etf_status=MagicMock(),
        instrument=MagicMock(),
        etf_nav=None if mode == "missing_reader" else EtfNavReader(store),
    )
    facade = MarketQueryFacade(MarketService(readers))

    class TestProvider(Provider):
        scope = Scope.REQUEST

        @provide
        def market_facade(self) -> MarketQueryFacade:
            return facade

    container = make_async_container(TestProvider())
    app = FastAPI()
    setup_dishka(container, app)
    app.include_router(router, prefix="/api/v1")
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/market/etf-nav",
                json={
                    "instrument_id": 1,
                    "start_date": "2026-09-29",
                    "end_date": "2026-09-30",
                },
            )
        assert response.status_code == 200, response.text
        assert response.json()["data"]["points"] == (
            [
                {"nav_date": "2026-09-29", "nav": 4.4},
                {"nav_date": "2026-09-30", "nav": 4.5},
            ]
            if mode == "stored"
            else []
        )
    finally:
        await container.close()
