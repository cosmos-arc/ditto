"""Instrument ingestion context unit tests."""

from typing import cast

import polars as pl
from ditto_application.processes.ingestion.data_writer import IngestionDataWriter
from ditto_application.processes.ingestion.instrument_ingestion import (
    InstrumentBackfillContext,
    InstrumentIngestContext,
    InstrumentPostIngestContext,
    _process_fetched_data_by_instrument,
    backfill_adj_factor,
    ingest_by_instrument,
)
from ditto_application.processes.ingestion.result_handler import IngestionResultHandler
from ditto_application.processes.ingestion.types import SourceFetchers
from ditto_data.catalog import DataAssetRef, InMemoryDataCatalog
from ditto_data.services.market_service import MarketService
from ditto_data.services.metadata_service import MetadataService
from ditto_data.sources.protocols import (
    CapitalFetcher,
    FundamentalFetcher,
    MacroFetcher,
    MarketFetcher,
    MetadataFetcher,
)
from ditto_kernel.instrument import InstrumentIngestParams
from ditto_platform.foundation import OnDuplicate, WriteResult


class _WriteDataRecorder:
    def __init__(self, result: WriteResult) -> None:
        self._result = result
        self.calls: list[tuple[str, str, OnDuplicate]] = []

    def write_data(
        self,
        dataset: str,
        df: pl.DataFrame,
        trade_date: str,
        on_duplicate: OnDuplicate,
    ) -> WriteResult:
        self.calls.append((dataset, trade_date, on_duplicate))
        assert df.columns == ["source_ticker", "trade_date", "close"]
        return self._result


class _MetadataService:
    def __init__(self) -> None:
        self.calls: list[tuple[str | None, str]] = []

    def resolve_source_ticker(
        self,
        *,
        ticker: str | None = None,
        standard_ticker: str | None = None,
        instrument_id: int | None = None,
        asset_class: str,
        source: str,
    ) -> str:
        _ = standard_ticker, instrument_id, asset_class
        self.calls.append((ticker, source))
        return "000001.SZ"

    def list_trading_days(self, start: str, end: str) -> list[str]:
        _ = end
        return [start]


class _MarketSource:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str | None]] = []

    def fetch_stock_daily(
        self,
        *,
        source_ticker: str,
        start_date: str,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        self.calls.append((source_ticker, start_date, end_date))
        return pl.DataFrame(
            {
                "source_ticker": [source_ticker],
                "trade_date": [start_date],
                "close": [10.2],
            }
        )

    def fetch_adj_factor_by_ticker(
        self,
        *,
        ts_code: str,
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        self.calls.append((ts_code, start_date, end_date))
        return pl.DataFrame(
            {
                "source_ticker": [ts_code],
                "trade_date": [start_date],
                "adj_factor": [1.0],
            }
        )

    # #434 新增 instrument 路由方法：handler 构建期被 getattr，本测试
    # 只执行 stock_daily 路由，存根返回空帧即可。

    def fetch_earnings_forecast(
        self,
        *,
        source_ticker: str,
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        _ = source_ticker, start_date, end_date
        return pl.DataFrame()

    def fetch_earnings_express(
        self,
        *,
        source_ticker: str,
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        _ = source_ticker, start_date, end_date
        return pl.DataFrame()

    def fetch_futures_daily(
        self,
        *,
        source_ticker: str,
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        _ = source_ticker, start_date, end_date
        return pl.DataFrame()

    def fetch_index_valuation(
        self,
        *,
        source_ticker: str,
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        _ = source_ticker, start_date, end_date
        return pl.DataFrame()


class _MarketQueryService:
    def get_adj_factors(self, start: str, end: str) -> pl.DataFrame:
        _ = start, end
        return pl.DataFrame()


class _AdjFactorWriteRecorder:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, OnDuplicate]] = []

    def write_data(
        self,
        dataset: str,
        df: pl.DataFrame,
        trade_date: str,
        on_duplicate: OnDuplicate,
    ) -> WriteResult:
        self.calls.append((dataset, trade_date, on_duplicate))
        return WriteResult(
            file_path=f"{dataset}/{trade_date}",
            checksum="checksum123",
            rows_written=len(df),
            rows_total=len(df),
            blocked=False,
        )


def _single_source_fetchers(source: object) -> SourceFetchers:
    """替身单点注入：假源只实现被测 stock_daily 路由消费的方法面，
    五个协议槽位统一经此放宽为该替身（不再逐处 cast(object)）."""
    return SourceFetchers(
        metadata=cast(MetadataFetcher, source),
        market=cast(MarketFetcher, source),
        fundamental=cast(FundamentalFetcher, source),
        capital=cast(CapitalFetcher, source),
        macro=cast(MacroFetcher, source),
    )


def test_process_fetched_data_by_instrument_accepts_context() -> None:
    write_result = WriteResult(
        file_path="stock_daily/000001/2024",
        checksum="checksum123",
        rows_written=1,
        rows_total=1,
        blocked=False,
    )
    writer = _WriteDataRecorder(write_result)
    catalog = InMemoryDataCatalog()
    ctx = InstrumentPostIngestContext(
        result_handler=IngestionResultHandler(None, "tushare"),
        data_writer=cast(IngestionDataWriter, writer),
        source_name="tushare",
        catalog_writer=catalog,
    )

    result = _process_fetched_data_by_instrument(
        pl.DataFrame(
            {
                "source_ticker": ["000001.SZ"],
                "trade_date": ["2024-01-02"],
                "close": [10.2],
            }
        ),
        "stock_daily",
        "000001.SZ",
        InstrumentIngestParams(
            ticker="000001",
            start_date="2024-01-01",
            end_date="2024-01-31",
        ),
        ctx=ctx,
    )

    assert result.status == "success"
    assert writer.calls == [("stock_daily", "2024-01-01", OnDuplicate.VERIFY_IDENTICAL)]
    # #394:标的维度写入也收敛为数据集级 catalog 行。
    asset = DataAssetRef(dataset_id="stock_daily", namespace="market")
    assert catalog.get_asset(asset) is not None


def test_ingest_by_instrument_accepts_runtime_context() -> None:
    write_result = WriteResult(
        file_path="stock_daily/000001/2024",
        checksum="checksum123",
        rows_written=1,
        rows_total=1,
        blocked=False,
    )
    writer = _WriteDataRecorder(write_result)
    metadata = _MetadataService()
    market_source = _MarketSource()
    fetchers = _single_source_fetchers(market_source)
    ctx = InstrumentIngestContext(
        fetchers=fetchers,
        # 最小替身只实现 resolve_source_ticker 消费面，声明类型为具体类，需单点放宽.
        metadata_service=cast(MetadataService, metadata),
        source_name="tushare",
        result_handler=IngestionResultHandler(None, "tushare"),
        data_writer=cast(IngestionDataWriter, writer),
    )

    result = ingest_by_instrument(
        "stock_daily",
        InstrumentIngestParams(
            ticker="000001",
            start_date="2024-01-01",
            end_date="2024-01-31",
        ),
        False,
        ctx=ctx,
    )

    assert result.status == "success"
    assert metadata.calls == [("000001", "tushare")]
    assert market_source.calls == [("000001.SZ", "2024-01-01", "2024-01-31")]
    assert writer.calls == [("stock_daily", "2024-01-01", OnDuplicate.VERIFY_IDENTICAL)]


def test_backfill_adj_factor_accepts_runtime_context() -> None:
    metadata = _MetadataService()
    market_source = _MarketSource()
    writer = _AdjFactorWriteRecorder()
    fetchers = _single_source_fetchers(market_source)
    ctx = InstrumentBackfillContext(
        # 最小替身只实现 resolve_source_ticker 消费面，声明类型为具体类，需单点放宽.
        metadata_service=cast(MetadataService, metadata),
        # 最小替身只实现 get_adj_factors 消费面，声明类型为具体类，需单点放宽.
        market_service=cast(MarketService, _MarketQueryService()),
        fetchers=fetchers,
        source_name="tushare",
        data_writer=cast(IngestionDataWriter, writer),
    )

    result = backfill_adj_factor(
        instrument_id=1,
        start="2024-01-02",
        end="2024-01-02",
        ctx=ctx,
    )

    assert result == {"status": "ok", "gap_count": 1, "filled_dates": 1}
    assert market_source.calls == [("000001.SZ", "20240102", "20240102")]
    assert writer.calls == [("adj_factor", "2024-01-02", OnDuplicate.KEEP_LAST)]


def _patch_market_source_for_registry() -> None:
    """#518-#523 增补后 instrument 注册表急切 getattr 新方法；给测试假源补齐."""
    for name in (
        "fetch_moneyflow",
        "fetch_hk_hold",
        "fetch_fina_indicator",
        "fetch_fund_portfolio",
        "fetch_fund_share",
        "fetch_etf_daily",
        "fetch_fund_nav",
        "fetch_fund_adj",
        "fetch_valuation_metrics",
        "fetch_margin_trading",
        "fetch_pledge_ratio",
        "fetch_index_valuation",
        "fetch_balance_sheet",
        "fetch_income_statement",
        "fetch_cash_flow",
        "fetch_dividend",
        "fetch_earnings_forecast",
        "fetch_earnings_express",
        "fetch_futures_daily",
    ):
        if not hasattr(_MarketSource, name):

            def _stub(
                *args: object, _name: str = name, **kwargs: object
            ) -> pl.DataFrame:
                return pl.DataFrame()

            _stub.__name__ = name
            setattr(_MarketSource, name, staticmethod(_stub))


_patch_market_source_for_registry()
