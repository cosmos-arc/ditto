"""个股资金画像：真实存储→facade→HTTP 契约（#658 批次3）.

真实 ParquetStore（moneyflow/top_list/top_inst）＋真实 SQLite 两融→
CapitalStore → CapitalQueryFacade →
CapitalProfileQueryFacade → POST /capital/profile。锁定：四块联看、
latest_available 语义标注、margin 迟发待补（尾部 5 交易日窗）、
无事件合法空、experimental 门。
"""

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import polars as pl
import pytest
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import setup_dishka
from ditto_application.queries.capital import CapitalQueryFacade
from ditto_application.queries.capital_profile import (
    CapitalProfileQueryFacade,
    CapitalProfileRequest,
)
from ditto_application.queries.dataset_coverage import DatasetCoverageQueryFacade
from ditto_application.queries.metadata import MetadataQueryFacade
from ditto_apps.api.routes.capital import router
from ditto_apps.models.capital import MarginBlock
from ditto_data.observability.metrics import register_metrics
from ditto_data.services.capital_store import CapitalStore
from ditto_data.services.deps import CapitalReaders, CapitalWriters
from ditto_data.storage.capital.margin.margin_trading_reader import MarginTradingReader
from ditto_data.storage.capital.margin.margin_trading_writer import MarginTradingWriter
from ditto_data.storage.capital.moneyflow import (
    MoneyflowReader,
    MoneyflowWriter,
)
from ditto_data.storage.capital.specs import MARGIN_TRADING_SPEC
from ditto_data.storage.capital.top_inst import TopInstReader, TopInstWriter
from ditto_data.storage.capital.top_list import TopListReader, TopListWriter
from ditto_platform.foundation import ParquetStore, SQLiteClient, SQLitePool
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

_TRADING_DAYS = ["2026-10-26", "2026-10-27", "2026-10-28"]


class _StubCalendar:
    def list_trading_days(self, start: str, end: str) -> list[str]:
        return [d for d in _TRADING_DAYS if start <= d <= end]


def _make_store(tmp_path: Path, mode: str) -> CapitalStore:
    store = ParquetStore(
        tmp_path,
        key_columns=("instrument_id", "trade_date"),
        date_column="trade_date",
        instrument_column="instrument_id",
    )
    if mode != "empty":
        MoneyflowWriter(store).write(
            pl.DataFrame(
                {
                    "instrument_id": [1],
                    "trade_date": [date(2026, 10, 26)],
                    "knowledge_date": [date(2026, 10, 27)],
                    "net_mf_amount": [123.4],
                    "net_mf_vol": [500.0],
                    "source": ["tushare"],
                },
                schema_overrides={"net_mf_amount": pl.Float64},
            ),
            2026,
        )
        TopListWriter(store).write(
            pl.DataFrame(
                {
                    "instrument_id": [1],
                    "trade_date": [date(2026, 10, 26)],
                    "knowledge_date": [date(2026, 10, 27)],
                    "reason": ["日涨幅偏离值达到7%"],
                    "close": [3.3],
                },
            ),
            2026,
        )
        TopInstWriter(store).write(
            pl.DataFrame(
                {
                    "instrument_id": [1],
                    "trade_date": [date(2026, 10, 26)],
                    "knowledge_date": [date(2026, 10, 27)],
                    "reason": ["日涨幅偏离值达到7%"],
                    "exalter": ["某证券营业部"],
                    "side": ["0"],
                    "buy": [1000.0],
                    "sell": [None],
                    "net_buy": [1000.0],
                },
                schema_overrides={"buy": pl.Float64, "sell": pl.Float64},
            ),
            2026,
        )
    margin_rows = {
        "instrument_id": [1, 1],
        "trade_date": ["2026-10-26", "2026-10-27"],
        "knowledge_date": ["2026-10-27", "2026-11-02"],
        "effective_from": ["2026-10-27", "2026-11-02"],
        "effective_to": [None, None],
        "margin_buy_balance": [None, 1.0],
        "short_sell_balance": [2.0, None],
        "margin_buy_amount": [None, 3.0],
        "short_sell_volume": [None, 4],
    }
    client = SQLiteClient(SQLitePool(str(tmp_path / "margin.sqlite")))
    client.conn.executescript("""
        CREATE TABLE margin_trading (
            instrument_id INTEGER, trade_date TEXT, knowledge_date TEXT,
            effective_from TEXT, effective_to TEXT, margin_buy_balance REAL,
            short_sell_balance REAL, margin_buy_amount REAL, short_sell_volume REAL,
            PRIMARY KEY (instrument_id, trade_date, effective_from));
    """)
    MarginTradingWriter(MARGIN_TRADING_SPEC, client).write(
        pl.DataFrame(margin_rows, schema_overrides={"effective_to": pl.String})
    )
    margin_reader = MarginTradingReader(MARGIN_TRADING_SPEC, client, tmp_path)
    readers = CapitalReaders(
        margin_trading=margin_reader,
        pledge_ratio=MagicMock(),
        valuation_metrics=MagicMock(),
        index_composition=MagicMock(),
        index_valuation=MagicMock(),
        moneyflow=MoneyflowReader(store),
        cyq_perf=MagicMock(),
        hk_hold=MagicMock(),
        hsgt_top10=MagicMock(),
        top_list=TopListReader(store),
        top_inst=TopInstReader(store),
        top10_holders=MagicMock(),
        top10_floatholders=MagicMock(),
    )
    return CapitalStore(read_ports=readers, write_ports=MagicMock(spec=CapitalWriters))


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["stored", "empty"])
async def test_capital_profile_four_blocks(tmp_path: Path, mode: str) -> None:
    register_metrics()
    capital_store = _make_store(tmp_path, mode)
    capital_facade = CapitalQueryFacade(capital_store=capital_store)
    profile_facade = CapitalProfileQueryFacade(
        capital=capital_facade, calendar=_StubCalendar()
    )
    metadata_facade = MagicMock(spec=MetadataQueryFacade)
    metadata_facade.resolve_instrument_identifier.return_value = 1

    class TestProvider(Provider):
        scope = Scope.REQUEST

        @provide
        def profile(self) -> CapitalProfileQueryFacade:
            return profile_facade

        @provide
        def coverage(self) -> DatasetCoverageQueryFacade:
            return DatasetCoverageQueryFacade()

        @provide
        def metadata(self) -> MetadataQueryFacade:
            return metadata_facade

    container = make_async_container(TestProvider())
    app = FastAPI()
    setup_dishka(container, app)
    app.include_router(router, prefix="/api/v1")
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/capital/profile",
                json={
                    "instrument_id": 1,
                    "start_date": "2026-10-26",
                    "end_date": "2026-10-28",
                    "allow_experimental_data": True,
                },
            )
        assert response.status_code == 200, response.text
        payload = response.json()["data"]
        assert payload["instrument_id"] == 1
        assert payload["window"] == {"start": "2026-10-26", "end": "2026-10-28"}
        if mode == "stored":
            assert payload["moneyflow"]["rows"][0]["net_mf_amount"] == 123.4
            assert payload["moneyflow"]["latest_trade_date"] == "2026-10-26"
            assert payload["moneyflow"]["read_semantics"] == "latest_available"
            assert payload["top_list"]["rows"][0]["reason"] == "日涨幅偏离值达到7%"
            inst = payload["top_inst"]["rows"][0]
            assert inst["buy"] == 1000.0
            assert inst["sell"] is None
            margin_rows_out = payload["margin_trading"]["rows"]
            # null 余额月末行原样传播(correctness F1),不再 500 或填 0。
            assert margin_rows_out[1]["margin_buy_balance"] is None
            assert margin_rows_out[0]["margin_buy_balance"] == 1.0
            assert payload["margin_trading"]["read_semantics"] == "latest_available"
            assert payload["moneyflow"]["sources"] == ["tushare"]
        else:
            for block in ("moneyflow", "top_list", "top_inst"):
                assert payload[block]["rows"] == []
                assert payload[block]["latest_trade_date"] is None
        # SQLite 迟发到窗口外仍可读；末端 10-27，窗尾 10-28 待补。
        assert payload["margin_trading"]["pending_trade_dates"] == ["2026-10-28"]
        for block in ("moneyflow", "top_list", "top_inst", "margin_trading"):
            assert payload[block]["data_coverage"]["dataset"] == (
                "margin_trading" if block == "margin_trading" else block
            )
    finally:
        await container.close()


@pytest.mark.asyncio
async def test_capital_profile_requires_experimental_gate(tmp_path: Path) -> None:
    register_metrics()
    capital_store = _make_store(tmp_path, "stored")
    profile_facade = CapitalProfileQueryFacade(
        capital=CapitalQueryFacade(capital_store=capital_store),
        calendar=_StubCalendar(),
    )
    result = profile_facade.get_profile(
        CapitalProfileRequest(
            instrument_id=1,
            start=date(2026, 10, 26),
            end=date(2026, 10, 28),
            allow_experimental_data=True,
        )
    )
    with pytest.raises(Exception, match="experimental") as exc_info:
        profile_facade.get_profile(
            CapitalProfileRequest(
                instrument_id=1,
                start=date(2026, 10, 26),
                end=date(2026, 10, 28),
            )
        )
    assert result.moneyflow.latest_trade_date == "2026-10-26"
    assert "experimental" in str(exc_info.value)


@pytest.mark.asyncio
async def test_capital_profile_window_validation(tmp_path: Path) -> None:
    """F8: 倒挂窗口 422,不冒充全空 200."""
    register_metrics()
    capital_store = _make_store(tmp_path, "stored")
    profile_facade = CapitalProfileQueryFacade(
        capital=CapitalQueryFacade(capital_store=capital_store),
        calendar=_StubCalendar(),
    )
    metadata_facade = MagicMock(spec=MetadataQueryFacade)
    metadata_facade.resolve_instrument_identifier.return_value = 1

    class TestProvider(Provider):
        scope = Scope.REQUEST

        @provide
        def profile(self) -> CapitalProfileQueryFacade:
            return profile_facade

        @provide
        def coverage(self) -> DatasetCoverageQueryFacade:
            return DatasetCoverageQueryFacade()

        @provide
        def metadata(self) -> MetadataQueryFacade:
            return metadata_facade

    container = make_async_container(TestProvider())
    app = FastAPI()
    setup_dishka(container, app)
    app.include_router(router, prefix="/api/v1")
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/capital/profile",
                json={
                    "instrument_id": 1,
                    "start_date": "2026-10-28",
                    "end_date": "2026-10-26",
                    "allow_experimental_data": True,
                },
            )
        assert response.status_code == 422, response.text
    finally:
        await container.close()


def test_margin_pending_excludes_future_sessions() -> None:
    """F3: today 上界把未来交易日排除在待补之外."""
    from datetime import date as date_type

    from ditto_application.queries.capital_profile import (
        CapitalProfileQueryFacade as F,
    )

    rows = pl.DataFrame({"trade_date": ["2026-10-26"]})
    facade = F(capital=MagicMock(), calendar=_StubCalendar())
    pending = facade._margin_pending_dates(
        rows, "2026-10-26", "2026-10-28", today=date_type(2026, 10, 27)
    )
    assert pending == ("2026-10-27",)


def test_margin_block_model_defaults() -> None:
    """margin 块默认承诺文案＋待补空列表（语义声明随响应传播）."""
    block = MarginBlock()
    assert block.freshness_promise.startswith("交易所于下一交易日开市前")
    assert block.pending_trade_dates == []
    assert block.read_semantics == "latest_available"
