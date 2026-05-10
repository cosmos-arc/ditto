"""摄取协调器 — IngestionCoordinator (facade)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import NamedTuple

import polars as pl
from ditto_data.models import Dataset, DateScheduleType
from ditto_data.models.ingestion import IngestionResult
from ditto_data.services.capital_service import CapitalService
from ditto_data.services.fundamental_service import FundamentalService
from ditto_data.services.macro_service import MacroService
from ditto_data.services.market_service import MarketService
from ditto_data.services.market_write_service import MarketWriteService
from ditto_data.services.metadata_service import MetadataService
from ditto_kernel.instrument import InstrumentIngestParams
from ditto_platform.foundation import OnDuplicate, WriteResult, logger

from ditto_application.exceptions import AppProcessError
from ditto_application.processes.ingestion.commodity_fetcher import (
    CommoditySource,
)
from ditto_application.processes.ingestion.commodity_fetcher import (
    fetch_commodity_daily as _fetch_commodity_daily,
)
from ditto_application.processes.ingestion.config import IngestionCoordinatorConfig
from ditto_application.processes.ingestion.coordinator_constants import (
    get_all_index_codes,
)
from ditto_application.processes.ingestion.data_writer import IngestionDataWriter
from ditto_application.processes.ingestion.fetch_handlers import (
    build_daily_fetch_handlers,
)
from ditto_application.processes.ingestion.instrument_ingestion import (
    backfill_adj_factor as _backfill_adj_factor_impl,
)
from ditto_application.processes.ingestion.instrument_ingestion import (
    ingest_by_instrument as _ingest_by_instrument_impl,
)
from ditto_application.processes.ingestion.list_date_inference import (
    ListDateInferenceService,
)
from ditto_application.processes.ingestion.metadata_manager import MetadataManager
from ditto_application.processes.ingestion.post_ingest import (
    handle_fetch_error as _handle_fetch_error,
)
from ditto_application.processes.ingestion.post_ingest import (
    process_fetched_data as _process_fetched_data,
)
from ditto_application.processes.ingestion.post_ingest import (
    write_data_safe as _write_data_safe,
)
from ditto_application.processes.ingestion.result_handler import IngestionResultHandler
from ditto_application.processes.ingestion.types import SourceFetchers

__all__ = [
    "IngestionCoordinator",
    "IngestionServices",
    "MarketServices",
    "SourceFetchers",
]


def _validate_dataset(dataset: str) -> Dataset:
    """验证数据集名称并返回枚举值。"""
    try:
        return Dataset(dataset)
    except ValueError as e:
        raise AppProcessError(
            f"不支持的数据集: {dataset}",
            field="dataset",
            value=dataset,
        ) from e


def _list_natural_days(start_date: str, end_date: str) -> list[str]:
    """生成自然日列表 [start_date, end_date]。"""
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    days: list[str] = []
    current = start
    while current <= end:
        days.append(current.isoformat())
        current += timedelta(days=1)
    return days


class MarketServices(NamedTuple):
    """Market 域读写服务聚合."""

    query: MarketService
    write: MarketWriteService


class IngestionServices(NamedTuple):
    """域级写入服务聚合."""

    metadata: MetadataService
    market: MarketServices
    fundamental: FundamentalService
    capital: CapitalService
    macro: MacroService


class IngestionCoordinator:
    """统一摄取协调器。"""

    def __init__(
        self,
        services: IngestionServices,
        *,
        fetchers: SourceFetchers,
        fred_source: CommoditySource | None = None,
        config: IngestionCoordinatorConfig | None = None,
    ) -> None:
        """初始化 IngestionCoordinator。"""
        cfg = config or IngestionCoordinatorConfig()

        self._metadata_service = services.metadata
        self._market_service = services.market.query
        self._market_write_service = services.market.write
        self._fundamental_service = services.fundamental
        self._capital_service = services.capital
        self._macro_service = services.macro
        self._fetchers = fetchers
        self._source_name = cfg.source_name
        self._fred_source = fred_source
        self._ingestion_log_service = cfg.ingestion_log_service
        self._ingestion_cursor_service = cfg.ingestion_cursor_service
        self._quality_checker = cfg.quality_checker
        self._freeze_service = cfg.freeze_service

        self._metadata_manager = MetadataManager(cfg.ingestion_log_service)
        self._result_handler = IngestionResultHandler(
            cfg.ingestion_log_service, cfg.source_name
        )
        self._data_writer = IngestionDataWriter(
            metadata_service=services.metadata,
            market_write_service=services.market.write,
            fundamental_service=services.fundamental,
            capital_service=services.capital,
            macro_service=services.macro,
            source_name=cfg.source_name,
        )

        self._list_date_inference = ListDateInferenceService(
            metadata_service=services.metadata,
            source=fetchers.market,
            source_name=cfg.source_name,
        )

        self._index_codes_cache: list[str] | None = None

    def _fetch_commodity_daily(self, trade_date: str) -> pl.DataFrame:
        """获取商品数据（原油、贵金属、VIX），委托至 ``commodity_fetcher``。"""
        return _fetch_commodity_daily(
            trade_date,
            primary_source=self._fetchers.macro,
            fred_source=self._fred_source,
        )

    # ------------------------------------------------------------------
    # list_date 推断 + 指数代码缓存
    # ------------------------------------------------------------------

    def _get_cached_index_codes(self) -> list[str]:
        """获取缓存的指数代码列表。"""
        if self._index_codes_cache is None:
            logger.debug("Caching index codes from API on first access")
            self._index_codes_cache = get_all_index_codes(
                self._fetchers.metadata, include_sw_levels=[1, 2]
            )
            logger.debug(
                "已缓存指数代码",
                count=len(self._index_codes_cache),
            )

        return self._index_codes_cache

    # ------------------------------------------------------------------
    # 日期级摄取
    # ------------------------------------------------------------------

    def ingest_date(
        self,
        dataset: str,
        trade_date: str,
        force: bool = False,
    ) -> IngestionResult:
        """摄取单个交易日数据。"""
        logger.info(
            "开始摄取数据",
            event="ingestion_start",
            dataset=dataset,
            trade_date=trade_date,
            force=force,
        )

        _validate_dataset(dataset)

        if skip_result := self._check_should_skip(dataset, trade_date, force):
            return skip_result

        if not self._is_trading_day_for_dataset(dataset, trade_date):
            return self._create_skipped_result(dataset, trade_date, "非交易日, 跳过")

        return self._fetch_and_ingest(dataset, trade_date, force)

    def _check_should_skip(
        self, dataset: str, trade_date: str, force: bool
    ) -> IngestionResult | None:
        """检查是否应该跳过摄取。"""
        should_skip, skip_reason = self._metadata_manager.should_skip(
            dataset=dataset,
            trade_date=trade_date,
            source=self._source_name,
            force=force,
        )
        if should_skip:
            return IngestionResult(
                dataset=dataset,
                trade_date=trade_date,
                status="skipped",
                message=skip_reason or "数据已存在且摄取成功",
            )
        return None

    def _is_trading_day_for_dataset(self, dataset: str, trade_date: str) -> bool:
        """检查数据集是否需要交易日验证。"""
        try:
            dataset_enum = Dataset(dataset)
        except ValueError:
            return True

        if dataset_enum in (
            Dataset.STOCK_DAILY,
            Dataset.ETF_DAILY,
            Dataset.INDEX_DAILY,
            Dataset.STOCK_STATUS,
            Dataset.ADJ_FACTOR,
            Dataset.FUND_ADJ,
            Dataset.VALUATION_METRICS,
            Dataset.MARGIN_TRADING,
        ):
            return self._metadata_service.is_trading_day(trade_date)
        return True

    def _create_skipped_result(
        self, dataset: str, trade_date: str, message: str
    ) -> IngestionResult:
        """创建跳过结果。"""
        return IngestionResult(
            dataset=dataset,
            trade_date=trade_date,
            status="skipped",
            message=message,
        )

    def _fetch_and_ingest(
        self, dataset: str, trade_date: str, force: bool
    ) -> IngestionResult:
        """获取数据并执行摄取（统一错误处理）。"""
        df_or_result = self._try_fetch_data(dataset, trade_date)

        if isinstance(df_or_result, IngestionResult):
            return df_or_result

        return _process_fetched_data(
            df_or_result,
            dataset,
            trade_date,
            force,
            result_handler=self._result_handler,
            data_writer=self._data_writer,
            quality_checker=self._quality_checker,
            list_date_inference=self._list_date_inference,
            cursor_service=self._ingestion_cursor_service,
            freeze_service=self._freeze_service,
            source_name=self._source_name,
        )

    def _try_fetch_data(
        self, dataset: str, trade_date: str
    ) -> pl.DataFrame | IngestionResult:
        """尝试获取数据，失败时返回 IngestionResult。"""
        try:
            return self._fetch_data(dataset, trade_date)
        except Exception as e:
            return _handle_fetch_error(
                e,
                dataset=dataset,
                date_identifier=trade_date,
                context=f"fetching {dataset}",
                log_tag="during_fetch",
                source_name=self._source_name,
                result_handler=self._result_handler,
            )

    def _write_data_safe(
        self,
        dataset: str,
        df: pl.DataFrame,
        trade_date: str,
        on_duplicate: OnDuplicate,
        *,
        source_ticker: str | None = None,
        event_suffix: str = "",
    ) -> WriteResult | IngestionResult:
        """安全写入数据，统一异常处理。委托至 post_ingest.write_data_safe。"""
        return _write_data_safe(
            dataset,
            df,
            trade_date,
            on_duplicate,
            result_handler=self._result_handler,
            data_writer=self._data_writer,
            source_ticker=source_ticker,
            event_suffix=event_suffix,
        )

    def _handle_fetch_error(
        self,
        error: Exception,
        *,
        dataset: str,
        date_identifier: str,
        context: str,
        log_tag: str,
    ) -> IngestionResult:
        """统一的 fetch 错误处理。委托至 post_ingest.handle_fetch_error。"""
        return _handle_fetch_error(
            error,
            dataset=dataset,
            date_identifier=date_identifier,
            context=context,
            log_tag=log_tag,
            source_name=self._source_name,
            result_handler=self._result_handler,
        )

    # ------------------------------------------------------------------
    # 日期范围摄取
    # ------------------------------------------------------------------

    def ingest_range(
        self,
        dataset: str,
        start_date: str,
        end_date: str,
        force: bool = False,
    ) -> list[IngestionResult]:
        """摄取日期范围数据，根据 date_schedule 类型选择日期序列。"""
        try:
            dataset_enum = Dataset(dataset)
        except ValueError:
            dataset_enum = None

        default_schedule = DateScheduleType.TRADING_DAYS
        schedule_type = dataset_enum.date_schedule if dataset_enum else default_schedule

        match schedule_type:
            case DateScheduleType.TRADING_DAYS:
                dates = self._metadata_service.list_trading_days(start_date, end_date)
            case DateScheduleType.NATURAL_DAYS | DateScheduleType.SOURCE_DEFINED:
                dates = _list_natural_days(start_date, end_date)

        if not dates:
            return []

        results: list[IngestionResult] = []
        for dt in dates:
            result = self.ingest_date(dataset, dt, force)
            results.append(result)
        return results

    # ------------------------------------------------------------------
    # 按标的摄取（委托至 instrument_ingestion）
    # ------------------------------------------------------------------

    def ingest_by_instrument(
        self,
        dataset: str,
        params: InstrumentIngestParams,
        force: bool = False,
    ) -> IngestionResult:
        """按标的 + 日期范围摄取数据。委托至 instrument_ingestion 模块。"""
        return _ingest_by_instrument_impl(
            dataset,
            params,
            force,
            fetchers=self._fetchers,
            metadata_service=self._metadata_service,
            source_name=self._source_name,
            result_handler=self._result_handler,
            data_writer=self._data_writer,
        )

    def _fetch_data(self, dataset: str, trade_date: str) -> pl.DataFrame:
        """根据数据集类型调用对应的 Source 方法获取数据（日期级）。"""
        dataset_enum = _validate_dataset(dataset)

        handlers = build_daily_fetch_handlers(
            self._fetchers,
            trade_date,
            fetch_commodity_daily=self._fetch_commodity_daily,
            get_cached_index_codes=self._get_cached_index_codes,
        )

        if dataset_enum not in handlers:
            raise AppProcessError(
                f"不支持的数据集: {dataset}",
                field="dataset",
                value=dataset,
            )

        return handlers[dataset_enum]()

    def backfill_adj_factor(
        self,
        instrument_id: int,
        start: str,
        end: str,
    ) -> dict[str, object]:
        """按标的智能回补复权因子空洞。委托至 instrument_ingestion 模块。"""
        return _backfill_adj_factor_impl(
            instrument_id=instrument_id,
            start=start,
            end=end,
            metadata_service=self._metadata_service,
            market_service=self._market_service,
            fetchers=self._fetchers,
            source_name=self._source_name,
            data_writer=self._data_writer,
        )
