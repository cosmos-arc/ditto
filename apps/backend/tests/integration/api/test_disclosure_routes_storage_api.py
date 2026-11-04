"""#658 批次4b 消费接线：真实存储→facade→HTTP 契约.

真实 ParquetStore（hk_hold/hsgt_top10/top10_holders/fina_indicator/
earnings_express）→ Store → facade → GET 路由。锁定：行透传（ISO 日期/null
保真）、read_semantics、experimental 门、market_type 过滤、制度语义在
docstring/coverage。
"""

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import polars as pl
import pytest
from dishka import AsyncContainer, Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import setup_dishka
from ditto_application.queries.capital import CapitalQueryFacade
from ditto_application.queries.dataset_coverage import DatasetCoverageQueryFacade
from ditto_application.queries.fundamental import FundamentalQueryFacade
from ditto_application.queries.metadata import MetadataQueryFacade
from ditto_apps.api.routes import capital as capital_routes
from ditto_apps.api.routes import fundamental as fundamental_routes
from ditto_apps.middleware import configure_exception_handlers
from ditto_data.observability.metrics import register_metrics
from ditto_data.services.capital_store import CapitalStore
from ditto_data.services.deps import CapitalReaders, CapitalWriters
from ditto_data.services.fundamental_store import FundamentalStore
from ditto_data.storage.capital.hk_hold import HkHoldReader, HkHoldWriter
from ditto_data.storage.capital.hsgt_top10 import HsgtTop10Reader, HsgtTop10Writer
from ditto_data.storage.capital.top10_holders import (
    Top10HoldersReader,
    Top10HoldersWriter,
)
from ditto_data.storage.fundamental.earnings.express.reader import (
    EarningsExpressReader,
)
from ditto_data.storage.fundamental.earnings.express.writer import (
    EarningsExpressWriter,
)
from ditto_data.storage.fundamental.fina_indicator import (
    FinaIndicatorReader,
    FinaIndicatorWriter,
)
from ditto_platform.foundation import ParquetStore
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


def _make_capital_store(tmp_path: Path) -> CapitalStore:
    store = ParquetStore(
        tmp_path,
        key_columns=("instrument_id", "trade_date", "knowledge_date"),
        date_column="trade_date",
        instrument_column="instrument_id",
    )
    HkHoldWriter(store).write(
        pl.DataFrame(
            {
                "instrument_id": [1],
                "trade_date": [date(2026, 10, 26)],
                "knowledge_date": [date(2026, 10, 27)],
                "vol": [1000.0],
                "ratio": [1.5],
                "exchange": ["SZ"],
                "source_ticker": ["000001.SZ"],
                "source": ["tushare"],
            }
        ),
        2026,
    )
    HsgtTop10Writer(store).write(
        pl.DataFrame(
            {
                "instrument_id": [1, 2],
                "trade_date": [date(2026, 10, 26)] * 2,
                "knowledge_date": [date(2026, 10, 27)] * 2,
                "market_type": ["1", "3"],
                "rank": [1, 1],
                "close": [10.0, 20.0],
                "buy": [None, None],
                "sell": [None, None],
                "net_amount": [None, None],
                "source_ticker": ["600000.SH", "000001.SZ"],
                "source": ["tushare"] * 2,
            }
        ),
        2026,
    )
    holders_store = ParquetStore(
        tmp_path,
        key_columns=("instrument_id", "report_date", "knowledge_date", "holder_name"),
        date_column="report_date",
        instrument_column="instrument_id",
    )
    Top10HoldersWriter(holders_store).write(
        pl.DataFrame(
            {
                "instrument_id": [1],
                "report_date": [date(2026, 9, 30)],
                "knowledge_date": [date(2026, 10, 20)],
                "holder_name": ["某基金"],
                "hold_amount": [1.0e8],
                "hold_ratio": [5.0],
                "source_ticker": ["000001.SZ"],
                "source": ["tushare"],
            },
            schema_overrides={"hold_amount": pl.Float64, "hold_ratio": pl.Float64},
        ),
        2026,
    )
    readers = CapitalReaders(
        margin_trading=MagicMock(),
        pledge_ratio=MagicMock(),
        valuation_metrics=MagicMock(),
        index_composition=MagicMock(),
        index_valuation=MagicMock(),
        moneyflow=MagicMock(),
        cyq_perf=MagicMock(),
        hk_hold=HkHoldReader(store),
        hsgt_top10=HsgtTop10Reader(store),
        top_list=MagicMock(),
        top_inst=MagicMock(),
        top10_holders=Top10HoldersReader(holders_store),
        top10_floatholders=MagicMock(),
    )
    return CapitalStore(read_ports=readers, write_ports=MagicMock(spec=CapitalWriters))


def _make_fundamental_store(tmp_path: Path) -> FundamentalStore:
    express_store = ParquetStore(
        tmp_path,
        key_columns=("source_ticker", "ann_date", "report_date", "knowledge_date"),
        date_column="ann_date",
        instrument_column="source_ticker",
    )
    EarningsExpressWriter(express_store).write(
        pl.DataFrame(
            {
                "source_ticker": ["000001.SZ"],
                "ann_date": [date(2026, 3, 15)],
                "report_date": [date(2025, 12, 31)],
                "revenue": [1.0e10],
                "operate_profit": [2.0e9],
                "total_profit": [2.1e9],
                "n_income": [1.5e9],
                "total_assets": [5.0e10],
                "audit_status": [None],
                "knowledge_date": [date(2026, 11, 2)],
            }
        ),
        2026,
    )
    fina_store = ParquetStore(
        tmp_path,
        key_columns=("instrument_id", "report_date", "knowledge_date"),
        date_column="report_date",
        instrument_column="instrument_id",
    )
    FinaIndicatorWriter(fina_store).write(
        pl.DataFrame(
            {
                "instrument_id": [1],
                "report_date": [date(2025, 12, 31)],
                "knowledge_date": [date(2026, 3, 15)],
                "eps": [1.2],
                "source_ticker": ["000001.SZ"],
                "source": ["tushare"],
            }
        ),
        2025,
    )
    return FundamentalStore(
        read_ports=MagicMock(
            fina_indicator=FinaIndicatorReader(fina_store),
            earnings_express=EarningsExpressReader(express_store),
        ),
        write_ports=MagicMock(),
    )


def _build_app(
    capital: CapitalStore, fundamental: FundamentalStore
) -> tuple[FastAPI, AsyncContainer]:
    capital_facade = CapitalQueryFacade(capital_store=capital)
    fundamental_facade = FundamentalQueryFacade(fundamental_store=fundamental)
    metadata_facade = MagicMock(spec=MetadataQueryFacade)
    metadata_facade.resolve_instrument_identifier.return_value = 1

    class TestProvider(Provider):
        scope = Scope.REQUEST

        @provide
        def capital(self) -> CapitalQueryFacade:
            return capital_facade

        @provide
        def fundamental(self) -> FundamentalQueryFacade:
            return fundamental_facade

        @provide
        def metadata(self) -> MetadataQueryFacade:
            return metadata_facade

        @provide
        def coverage(self) -> DatasetCoverageQueryFacade:
            return DatasetCoverageQueryFacade()

    container = make_async_container(TestProvider())
    app = FastAPI()
    configure_exception_handlers(app)
    setup_dishka(container, app)
    app.include_router(capital_routes.router, prefix="/api/v1")
    app.include_router(fundamental_routes.router, prefix="/api/v1")
    return app, container


@pytest.mark.asyncio
async def test_disclosure_routes_read_real_storage(tmp_path: Path) -> None:
    register_metrics()
    capital = _make_capital_store(tmp_path)
    fundamental = _make_fundamental_store(tmp_path)
    app, container = _build_app(capital, fundamental)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            hk = await client.get(
                "/api/v1/capital/hk-hold",
                params={
                    "instrument_id": 1,
                    "start_date": "2026-10-01",
                    "end_date": "2026-10-31",
                    "allow_experimental_data": True,
                },
            )
            assert hk.status_code == 200, hk.text
            payload = hk.json()["data"]
            assert payload["read_semantics"] == "latest_available"
            row = payload["rows"][0]
            assert row["vol"] == 1000.0
            assert row["trade_date"] == "2026-10-26"
            assert payload["data_coverage"]["dataset"] == "hk_hold"

            hsgt = await client.get(
                "/api/v1/capital/hsgt-top10",
                params={
                    "start_date": "2026-10-01",
                    "end_date": "2026-10-31",
                    "market_type": "3",
                    "allow_experimental_data": True,
                },
            )
            assert hsgt.status_code == 200, hsgt.text
            rows = hsgt.json()["data"]["rows"]
            assert len(rows) == 1
            assert rows[0]["market_type"] == "3"
            # 改制后 null 保真
            assert rows[0]["buy"] is None

            holders = await client.get(
                "/api/v1/capital/top10-holders",
                params={
                    "instrument_id": 1,
                    "start_date": "2026-01-01",
                    "end_date": "2026-12-31",
                    "allow_experimental_data": True,
                },
            )
            assert holders.status_code == 200, holders.text
            assert holders.json()["data"]["rows"][0]["holder_name"] == "某基金"

            express = await client.get(
                "/api/v1/fundamental/earnings-express",
                params={
                    "ticker": "000001.SZ",
                    "start_date": "2026-01-01",
                    "end_date": "2026-12-31",
                    "allow_experimental_data": True,
                },
            )
            assert express.status_code == 200, express.text
            assert express.json()["data"]["rows"][0]["n_income"] == 1.5e9

            indicators = await client.get(
                "/api/v1/fundamental/indicators",
                params={
                    "instrument_id": 1,
                    "start_date": "2025-01-01",
                    "end_date": "2025-12-31",
                    "allow_experimental_data": True,
                },
            )
            assert indicators.status_code == 200, indicators.text
            assert indicators.json()["data"]["rows"][0]["eps"] == 1.2
    finally:
        await container.close()


@pytest.mark.asyncio
async def test_disclosure_routes_require_experimental(tmp_path: Path) -> None:
    register_metrics()
    capital = _make_capital_store(tmp_path)
    fundamental = _make_fundamental_store(tmp_path)
    app, container = _build_app(capital, fundamental)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            hk = await client.get(
                "/api/v1/capital/hk-hold",
                params={
                    "instrument_id": 1,
                    "start_date": "2026-10-01",
                    "end_date": "2026-10-31",
                },
            )
            assert hk.status_code in (400, 403, 422), hk.text
            body = hk.text
            assert "experimental" in body
    finally:
        await container.close()
