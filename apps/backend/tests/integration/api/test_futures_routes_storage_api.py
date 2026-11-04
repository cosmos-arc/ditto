"""#658 批次4c 消费接线：期货双库与指数估值真实存储→facade→HTTP 契约.

真实 ParquetStore（market/futures/daily、market/futures/basic、
capital/index_valuation）→ MarketService/CapitalStore → facade → 路由。
锁定：行透传（ISO 日期/null 保真）、read_semantics、experimental 门、
合约代码过滤、交易所/品种过滤。
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
from ditto_application.queries.futures import FuturesQueryFacade
from ditto_application.queries.metadata import MetadataQueryFacade
from ditto_apps.api.routes import capital as capital_routes
from ditto_apps.api.routes import futures as futures_routes
from ditto_apps.middleware import configure_exception_handlers
from ditto_data.observability.metrics import register_metrics
from ditto_data.services.capital_store import CapitalStore
from ditto_data.services.deps import CapitalReaders, CapitalWriters, MarketReaders
from ditto_data.services.market_service import MarketService
from ditto_data.storage.capital.index_valuation import (
    IndexValuationReader,
    IndexValuationWriter,
)
from ditto_data.storage.market.futures.basic import (
    FuturesBasicReader,
    FuturesBasicWriter,
)
from ditto_data.storage.market.futures.daily import (
    FuturesDailyReader,
    FuturesDailyWriter,
)
from ditto_platform.foundation import ParquetStore
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


def _make_market_service(tmp_path: Path) -> MarketService:
    daily_store = ParquetStore(
        tmp_path,
        key_columns=("source_ticker", "trade_date", "knowledge_date"),
        date_column="trade_date",
        instrument_column="source_ticker",
    )
    # RB2410.SHF 10-30 双版本（11-02 重摄取纠正 settle）→ 收敛回归载体。
    FuturesDailyWriter(daily_store).write(
        pl.DataFrame(
            {
                "source_ticker": [
                    "RB2410.SHF",
                    "RB2410.SHF",
                    "RB2410.SHF",
                    "CU2412.SHF",
                ],
                "trade_date": [
                    date(2026, 10, 30),
                    date(2026, 10, 30),
                    date(2026, 10, 31),
                    date(2026, 10, 31),
                ],
                "open": [3450.0, 3450.0, 3460.0, 76000.0],
                "high": [3480.0, 3480.0, 3475.0, 76500.0],
                "low": [3440.0, 3440.0, 3455.0, 75800.0],
                "close": [3470.0, 3470.0, 3465.0, 76200.0],
                "settle": [3472.0, 3471.0, 3468.0, 76250.0],
                "pre_settle": [None, None, 3472.0, 76100.0],
                "volume": [120000.0, 120000.0, 98000.0, 45000.0],
                "amount": [4.15e7, 4.15e7, 3.4e7, 3.43e7],
                "open_interest": [230000.0, 230000.0, 225000.0, 88000.0],
                "knowledge_date": [
                    date(2026, 10, 30),
                    date(2026, 11, 2),
                    date(2026, 10, 31),
                    date(2026, 10, 31),
                ],
            }
        ),
        2026,
    )
    basic_store = ParquetStore(
        tmp_path,
        # 与生产 DI（di/market.py _futures_basic_parquet_store）逐字段一致。
        key_columns=("source", "source_ticker", "knowledge_date"),
        date_column="knowledge_date",
        instrument_column="source_ticker",
    )
    FuturesBasicWriter(basic_store).write(
        pl.DataFrame(
            {
                "source": ["tushare"] * 3,
                "source_ticker": ["RB2410.SHF", "CU2412.SHF", "RB2501.SHF"],
                "symbol": ["RB2410", "CU2412", "RB2501"],
                "exchange": ["SHFE", "SHFE", "SHFE"],
                "fut_code": ["RB", "CU", "RB"],
                "multiplier": [10.0, 5.0, 10.0],
                "list_date": [date(2024, 4, 22), date(2024, 6, 17), date(2024, 5, 6)],
                "delist_date": [
                    date(2026, 10, 31),
                    date(2024, 12, 16),
                    date(2027, 1, 18),
                ],
                "knowledge_date": [date(2026, 10, 31)] * 3,
            }
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
        futures_daily=FuturesDailyReader(daily_store),
        futures_basic=FuturesBasicReader(basic_store),
    )
    return MarketService(read_ports=readers)


def _make_capital_store(tmp_path: Path) -> CapitalStore:
    store = ParquetStore(
        tmp_path,
        key_columns=("instrument_id", "trade_date", "knowledge_date"),
        date_column="trade_date",
        instrument_column="instrument_id",
    )
    IndexValuationWriter(store).write(
        pl.DataFrame(
            {
                # 双版本（11-02 重摄取修订 pe）→ 收敛回归载体。
                "instrument_id": [7, 7],
                "trade_date": [date(2026, 10, 30), date(2026, 10, 30)],
                "knowledge_date": [date(2026, 10, 30), date(2026, 11, 2)],
                "total_mv": [4.9e10, 4.9e10],
                "float_mv": [4.1e10, 4.1e10],
                "pe": [14.2, 14.5],
                "pe_ttm": [13.8, 13.8],
                "pb": [1.36, 1.36],
                "turnover_rate": [0.98, 0.98],
                "source_ticker": ["000300.SH", "000300.SH"],
                "source": ["tushare", "tushare"],
            }
        ),
        2026,
    )
    readers = CapitalReaders(
        margin_trading=MagicMock(),
        pledge_ratio=MagicMock(),
        valuation_metrics=MagicMock(),
        index_composition=MagicMock(),
        index_valuation=IndexValuationReader(store),
        moneyflow=MagicMock(),
        cyq_perf=MagicMock(),
        hk_hold=MagicMock(),
        hsgt_top10=MagicMock(),
        top_list=MagicMock(),
        top_inst=MagicMock(),
        top10_holders=MagicMock(),
        top10_floatholders=MagicMock(),
    )
    return CapitalStore(read_ports=readers, write_ports=MagicMock(spec=CapitalWriters))


def _build_app(
    market: MarketService, capital: CapitalStore
) -> tuple[FastAPI, AsyncContainer]:
    futures_facade = FuturesQueryFacade(futures_data=market)
    capital_facade = CapitalQueryFacade(capital_store=capital)
    metadata_facade = MagicMock(spec=MetadataQueryFacade)
    metadata_facade.resolve_instrument_identifier.return_value = 7

    class TestProvider(Provider):
        scope = Scope.REQUEST

        @provide
        def futures(self) -> FuturesQueryFacade:
            return futures_facade

        @provide
        def capital(self) -> CapitalQueryFacade:
            return capital_facade

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
    app.include_router(futures_routes.router, prefix="/api/v1")
    app.include_router(capital_routes.router, prefix="/api/v1")
    return app, container


@pytest.mark.asyncio
async def test_futures_routes_read_real_storage(tmp_path: Path) -> None:
    register_metrics()
    market = _make_market_service(tmp_path)
    capital = _make_capital_store(tmp_path)
    app, container = _build_app(market, capital)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            bars = await client.post(
                "/api/v1/futures/bars",
                json={
                    "source_tickers": ["RB2410.SHF"],
                    "start_date": "2026-10-01",
                    "end_date": "2026-10-31",
                    "allow_experimental_data": True,
                },
            )
            assert bars.status_code == 200, bars.text
            payload = bars.json()["data"]
            # 修订收敛：RB2410 双版本(10-30 两天条)收敛为每交易日一行
            assert payload["read_semantics"] == "latest_available"
            assert len(payload["bars"]) == 2
            assert payload["data_coverage"]["dataset"] == "futures_daily"
            first = payload["bars"][0]
            assert first["source_ticker"] == "RB2410.SHF"
            assert first["trade_date"] == "2026-10-30"
            assert first["close"] == 3470.0
            # 收敛到最新 knowledge_date(11-02) 的纠正值
            assert first["settle"] == 3471.0
            # 上市首日 pre_settle null 保真
            assert first["pre_settle"] is None
            assert payload["bars"][1]["pre_settle"] == 3472.0

            contracts = await client.get(
                "/api/v1/futures/contracts",
                params={"fut_code": "RB", "allow_experimental_data": True},
            )
            assert contracts.status_code == 200, contracts.text
            contract_payload = contracts.json()["data"]
            rows = contract_payload["contracts"]
            assert [r["source_ticker"] for r in rows] == [
                "RB2410.SHF",
                "RB2501.SHF",
            ]
            assert rows[0]["delist_date"] == "2026-10-31"
            # 来源与快照摄取日随行传播
            assert rows[0]["source"] == "tushare"
            assert rows[0]["knowledge_date"] == "2026-10-31"
            assert contract_payload["data_coverage"]["dataset"] == "futures_basic"

            index_valuation = await client.get(
                "/api/v1/capital/index-valuation",
                params={
                    "instrument_id": 7,
                    "start_date": "2026-10-01",
                    "end_date": "2026-10-31",
                    "allow_experimental_data": True,
                },
            )
            assert index_valuation.status_code == 200, index_valuation.text
            iv = index_valuation.json()["data"]
            assert iv["read_semantics"] == "latest_available"
            # 修订收敛：双版本收敛为单行,取最新 knowledge_date 的修订值
            assert len(iv["rows"]) == 1
            row = iv["rows"][0]
            assert row["trade_date"] == "2026-10-30"
            assert row["pe"] == 14.5
            assert iv["data_coverage"]["dataset"] == "index_valuation"
    finally:
        await container.close()


@pytest.mark.asyncio
async def test_futures_routes_require_experimental(tmp_path: Path) -> None:
    register_metrics()
    market = _make_market_service(tmp_path)
    capital = _make_capital_store(tmp_path)
    app, container = _build_app(market, capital)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            bars = await client.post(
                "/api/v1/futures/bars",
                json={"start_date": "2026-10-01", "end_date": "2026-10-31"},
            )
            assert bars.status_code == 400, bars.text
            assert "experimental" in bars.text
            contracts = await client.get("/api/v1/futures/contracts")
            assert contracts.status_code == 400, contracts.text
            assert "experimental" in contracts.text
            iv = await client.get(
                "/api/v1/capital/index-valuation",
                params={
                    "instrument_id": 7,
                    "start_date": "2026-10-01",
                    "end_date": "2026-10-31",
                },
            )
            assert iv.status_code == 400, iv.text
            assert "experimental" in iv.text
    finally:
        await container.close()


@pytest.mark.asyncio
async def test_futures_window_rejected_and_ticker_filter(tmp_path: Path) -> None:
    register_metrics()
    market = _make_market_service(tmp_path)
    capital = _make_capital_store(tmp_path)
    app, container = _build_app(market, capital)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            inverted = await client.post(
                "/api/v1/futures/bars",
                json={
                    "start_date": "2026-10-31",
                    "end_date": "2026-10-01",
                    "allow_experimental_data": True,
                },
            )
            assert inverted.status_code == 422, inverted.text

            # 空合约列表拒绝：非缺省选择不得静默全量(fail-closed)
            empty_list = await client.post(
                "/api/v1/futures/bars",
                json={
                    "source_tickers": [],
                    "start_date": "2026-10-01",
                    "end_date": "2026-10-31",
                    "allow_experimental_data": True,
                },
            )
            assert empty_list.status_code == 422, empty_list.text

            unknown_ticker = await client.post(
                "/api/v1/futures/bars",
                json={
                    "source_tickers": ["XX9999.XXX"],
                    "start_date": "2026-10-01",
                    "end_date": "2026-10-31",
                    "allow_experimental_data": True,
                },
            )
            assert unknown_ticker.status_code == 200, unknown_ticker.text
            assert unknown_ticker.json()["data"]["bars"] == []

            # limit=最新 N 行：窗口 3 行(收敛后)取最新 2 行
            latest_n = await client.post(
                "/api/v1/futures/bars",
                json={
                    "start_date": "2026-10-01",
                    "end_date": "2026-10-31",
                    "limit": 2,
                    "allow_experimental_data": True,
                },
            )
            assert latest_n.status_code == 200, latest_n.text
            kept = latest_n.json()["data"]["bars"]
            assert [b["trade_date"] for b in kept] == [
                "2026-10-31",
                "2026-10-31",
            ]
    finally:
        await container.close()
