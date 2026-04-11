"""摄取协调器 — IngestionCoordinator."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Literal, NamedTuple, cast

import httpx
import polars as pl
from ditto_data.errors import (
    NetworkError,
    SourceFetchError,
)
from ditto_data.models import Dataset, DateScheduleType, OnDuplicate
from ditto_data.models.ingestion import IngestionResult
from ditto_data.models.storage import WriteResult
from ditto_data.services.capital_service import CapitalService
from ditto_data.services.fundamental_service import FundamentalService
from ditto_data.services.macro_service import MacroService
from ditto_data.services.market_service import MarketService
from ditto_data.services.market_write_service import MarketWriteService
from ditto_data.services.metadata_service import MetadataService
from ditto_data.sources.base import DataSource
from ditto_infra.foundation import logger
from ditto_kernel.types import InstrumentIngestParams

from ditto_app.contracts import CheckDataQualityCommand
from ditto_app.process.ingestion.auto_init import resolve_identifier_with_auto_init
from ditto_app.process.ingestion.backfill_handler import BackfillContext
from ditto_app.process.ingestion.backfill_handler import (
    backfill_adj_factor as _backfill_adj_factor,
)
from ditto_app.process.ingestion.commodity_fetcher import (
    fetch_commodity_daily as _fetch_commodity_daily,
)
from ditto_app.process.ingestion.config import IngestionCoordinatorConfig
from ditto_app.process.ingestion.coordinator_constants import (
    SUPPORTED_INSTRUMENT_DATASETS,
    get_all_index_codes,
)
from ditto_app.process.ingestion.data_writer import IngestionDataWriter
from ditto_app.process.ingestion.fetch_handlers import (
    build_daily_fetch_handlers,
    build_instrument_fetch_handlers,
)
from ditto_app.process.ingestion.list_date_inference import ListDateInferenceService
from ditto_app.process.ingestion.metadata_manager import MetadataManager
from ditto_app.process.ingestion.result_handler import IngestionResultHandler

__all__ = [
    "IngestionCoordinator",
    "MarketServices",
]


def _is_source_fetch_error(error: Exception) -> bool:
    """Check whether exception should be treated as source fetch failure."""
    return isinstance(error, SourceFetchError)


def _validate_dataset(dataset: str) -> Dataset:
    """验证数据集名称并返回枚举值。"""
    try:
        return Dataset(dataset)
    except ValueError as e:
        raise ValueError(f"不支持的数据集: {dataset}") from e


def _normalize_source_fetch_error(error: Exception) -> SourceFetchError:
    """Normalize external fetch error into app-level SourceFetchError."""
    source_name = getattr(error, "source", "unknown")
    return SourceFetchError(message=str(error), source=str(source_name))


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


class IngestionCoordinator:
    """统一摄取协调器。"""

    def __init__(
        self,
        metadata_service: MetadataService,
        market_services: MarketServices,
        fundamental_service: FundamentalService,
        capital_service: CapitalService,
        macro_service: MacroService,
        source: DataSource,
        config: IngestionCoordinatorConfig | None = None,
    ) -> None:
        """初始化 IngestionCoordinator。"""
        cfg = config or IngestionCoordinatorConfig()

        self._metadata_service = metadata_service
        self._market_service = market_services.query
        self._market_write_service = market_services.write
        self._fundamental_service = fundamental_service
        self._capital_service = capital_service
        self._macro_service = macro_service
        self._source = source
        self._source_name = cfg.source_name
        self._fred_source = cfg.fred_source
        self._ingestion_log_service = cfg.ingestion_log_service
        self._ingestion_cursor_service = cfg.ingestion_cursor_service
        self._quality_checker = cfg.quality_checker
        self._freeze_service = cfg.freeze_service

        self._metadata_manager = MetadataManager(cfg.ingestion_log_service)
        self._result_handler = IngestionResultHandler(
            cfg.ingestion_log_service, cfg.source_name
        )
        self._data_writer = IngestionDataWriter(
            metadata_service=metadata_service,
            market_write_service=self._market_write_service,
            fundamental_service=fundamental_service,
            capital_service=capital_service,
            macro_service=macro_service,
            source_name=cfg.source_name,
        )

        # list_date 推断服务（用于 basic 数据摄取后的补偿）
        self._list_date_inference = ListDateInferenceService(
            metadata_service=metadata_service,
            source=source,
            source_name=cfg.source_name,
        )

        # 缓存指数代码，避免每次摄取都调用 API
        self._index_codes_cache: list[str] | None = None

    def _fetch_commodity_daily(self, trade_date: str) -> pl.DataFrame:
        """获取商品数据（原油、贵金属、VIX），委托至 ``commodity_fetcher``。"""
        return _fetch_commodity_daily(
            trade_date,
            primary_source=self._source,
            fred_source=self._fred_source,
        )

    # ------------------------------------------------------------------
    # list_date 推断 + 指数代码缓存
    # ------------------------------------------------------------------

    def _run_list_date_inference(self, dataset: str) -> None:
        """
        在 basic 数据摄取后执行 list_date 推断补偿。

        针对 list_date 为 NULL 的证券，从历史行情数据推断上市日期。
        """
        asset_class_map = {
            "stock_basic": "stock",
            "etf_basic": "etf",
            "index_basic": "index",
        }

        asset_class = asset_class_map.get(dataset)
        if asset_class is None:
            return

        try:
            logger.info(
                "Running list_date inference after basic ingestion",
                event="list_date_inference_start",
                dataset=dataset,
                asset_class=asset_class,
            )
            count = self._list_date_inference.infer_for_asset_class(
                cast('Literal["stock", "etf", "index"]', asset_class)
            )
            logger.info(
                "Completed list_date inference",
                event="list_date_inference_complete",
                dataset=dataset,
                asset_class=asset_class,
                inferred_count=count,
            )
        except (
            pl.exceptions.ComputeError,
            pl.exceptions.SchemaError,
            ValueError,
            KeyError,
            TypeError,
            httpx.NetworkError,
            httpx.TimeoutException,
        ) as e:
            # 推断失败不影响主流程，仅记录警告
            logger.warning(
                f"list_date inference failed for {asset_class}",
                event="list_date_inference_error",
                dataset=dataset,
                asset_class=asset_class,
                error=str(e),
            )
        except Exception:
            logger.exception(
                "Unexpected error in list_date inference",
                event="list_date_inference_error",
                dataset=dataset,
                asset_class=asset_class,
            )

    def _get_cached_index_codes(self) -> list[str]:
        """获取缓存的指数代码列表。"""
        if self._index_codes_cache is None:
            logger.debug("Caching index codes from API on first access")
            self._index_codes_cache = get_all_index_codes(
                self._source, include_sw_levels=[1, 2]
            )
            logger.debug(
                "已缓存指数代码",
                count=len(self._index_codes_cache),
            )

        return self._index_codes_cache

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

        # 验证数据集是否支持
        _validate_dataset(dataset)

        # 检查是否应该跳过摄取
        if skip_result := self._check_should_skip(dataset, trade_date, force):
            return skip_result

        # 检查交易日（仅行情类数据集）
        if not self._is_trading_day_for_dataset(dataset, trade_date):
            return self._create_skipped_result(dataset, trade_date, "非交易日, 跳过")

        # 获取数据并执行摄取
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

        return self._process_fetched_data(df_or_result, dataset, trade_date, force)

    def _try_fetch_data(
        self, dataset: str, trade_date: str
    ) -> pl.DataFrame | IngestionResult:
        """尝试获取数据，失败时返回 IngestionResult。"""
        try:
            return self._fetch_data(dataset, trade_date)
        except Exception as e:
            return self._handle_fetch_error(
                e,
                dataset=dataset,
                date_identifier=trade_date,
                context=f"fetching {dataset}",
                log_tag="during_fetch",
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
        """统一的 fetch 错误处理。"""
        if isinstance(error, (httpx.NetworkError, httpx.TimeoutException)):
            logger.exception(
                f"network_error_{log_tag}",
                dataset=dataset,
                error_type=type(error).__name__,
            )
            network_error = NetworkError.from_httpx(
                error=error,
                source=self._source_name,
                context=context,
            )
            fetch_error = SourceFetchError(
                message=str(network_error),
                source=self._source_name,
                cause=network_error,
            )
            return self._result_handler.handle_fetch_error(
                dataset, date_identifier, fetch_error
            )

        if _is_source_fetch_error(error):
            fetch_error = _normalize_source_fetch_error(error)
            return self._result_handler.handle_fetch_error(
                dataset, date_identifier, fetch_error
            )

        logger.exception(
            f"unexpected_error_{log_tag}",
            dataset=dataset,
            error_type=type(error).__name__,
        )
        return self._result_handler.handle_unknown_error(
            dataset, date_identifier, error
        )

    def _process_fetched_data(
        self, df: pl.DataFrame, dataset: str, trade_date: str, force: bool
    ) -> IngestionResult:
        """处理获取的数据：DQ 检查 + 写入。"""
        if df.is_empty():
            return self._result_handler.handle_empty_data(dataset, trade_date)

        # DQ 质量检查
        if self._quality_checker is not None:
            checked_df, should_block = self._quality_checker.handle(
                CheckDataQualityCommand(
                    df=df,
                    dataset=dataset,
                    context={"trade_date": trade_date},
                ),
            )
            if should_block:
                return self._result_handler.handle_dq_blocked(
                    dataset,
                    trade_date,
                    WriteResult(
                        file_path="",
                        checksum="",
                        rows_written=0,
                        rows_total=df.height,
                        blocked=True,
                    ),
                )
            df = checked_df

        # 将 force 映射到 on_duplicate
        on_duplicate = OnDuplicate.KEEP_LAST if force else OnDuplicate.ERROR

        try:
            write_result = self._data_writer.write_data(
                dataset, df, trade_date, on_duplicate
            )
        except (
            pl.exceptions.ComputeError,
            pl.exceptions.SchemaError,
            ValueError,
            KeyError,
            TypeError,
            OSError,
        ) as e:
            logger.warning(
                "write_data_failed",
                event="write_data_error",
                dataset=dataset,
                trade_date=trade_date,
                error_type=type(e).__name__,
                error=str(e),
            )
            return self._result_handler.handle_unknown_error(dataset, trade_date, e)
        except Exception as e:
            logger.exception(
                "write_data_failed_unexpected",
                event="write_data_error",
                dataset=dataset,
                trade_date=trade_date,
                error_type=type(e).__name__,
            )
            return self._result_handler.handle_unknown_error(dataset, trade_date, e)

        # 检查 DQ 阻断
        if write_result.blocked:
            return self._result_handler.handle_dq_blocked(
                dataset, trade_date, write_result
            )

        # basic 数据摄取成功后，执行 list_date 推断补偿
        self._run_list_date_inference(dataset)
        self._run_post_ingest_hooks(dataset, trade_date)

        return self._result_handler.handle_success(
            dataset, trade_date, df, write_result
        )

    def _run_post_ingest_hooks(self, dataset: str, trade_date: str) -> None:
        """执行摄取后的副作用：游标更新、冻结点创建。"""
        # 更新摄入游标
        if self._ingestion_cursor_service is not None:
            try:
                self._ingestion_cursor_service.update_cursor(
                    dataset=dataset,
                    source=self._source_name,
                    last_success=trade_date,
                    last_attempted=trade_date,
                )
            except (ValueError, KeyError, TypeError, OSError) as e:
                logger.warning(
                    "cursor_update_failed",
                    event="cursor_update_error",
                    dataset=dataset,
                    trade_date=trade_date,
                    error_type=type(e).__name__,
                    error=str(e),
                )
            except Exception:
                logger.exception(
                    "cursor_update_failed_unexpected",
                    event="cursor_update_error",
                    dataset=dataset,
                    trade_date=trade_date,
                )

        # 创建冻结点（轻量级版本追踪）
        if self._freeze_service is not None:
            try:
                self._freeze_service.create_freeze(
                    freeze_id=f"{dataset}_{trade_date}",
                    description=f"Auto-freeze: {dataset} @ {trade_date}",
                    datasets=[dataset],
                )
            except (ValueError, KeyError, TypeError, OSError) as e:
                logger.warning(
                    "freeze_create_failed",
                    event="freeze_create_error",
                    dataset=dataset,
                    trade_date=trade_date,
                    error_type=type(e).__name__,
                    error=str(e),
                )
            except Exception:
                logger.exception(
                    "freeze_create_failed_unexpected",
                    event="freeze_create_error",
                    dataset=dataset,
                    trade_date=trade_date,
                )

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

    def ingest_by_instrument(
        self,
        dataset: str,
        params: InstrumentIngestParams,
        force: bool = False,
    ) -> IngestionResult:
        """按标的 + 日期范围摄取数据。"""
        dataset_enum = _validate_dataset(dataset)

        if dataset_enum not in SUPPORTED_INSTRUMENT_DATASETS:
            raise ValueError(f"数据集 {dataset} 不支持按标的摄取")

        asset_class = dataset_enum.asset_class
        if asset_class is None:
            raise ValueError(f"数据集 {dataset} 缺少 asset_class 定义")

        source_ticker = resolve_identifier_with_auto_init(
            params,
            asset_class,
            dataset,
            metadata_service=self._metadata_service,
            source=self._source,
            source_name=self._source_name,
        )

        logger.info(
            "开始按标的摄取数据",
            event="ingestion_by_instrument_start",
            dataset=dataset,
            source_ticker=source_ticker,
            asset_class=asset_class,
            start_date=params.start_date,
            end_date=params.end_date,
            force=force,
        )

        return self._fetch_and_ingest_by_instrument(
            dataset, dataset_enum, source_ticker, params
        )

    def _fetch_and_ingest_by_instrument(
        self,
        dataset: str,
        dataset_enum: Dataset,
        source_ticker: str,
        params: InstrumentIngestParams,
    ) -> IngestionResult:
        """按标的获取数据并执行摄取（统一错误处理）。"""
        df_or_result = self._try_fetch_data_by_instrument(
            dataset, dataset_enum, source_ticker, params
        )

        if isinstance(df_or_result, IngestionResult):
            return df_or_result

        return self._process_fetched_data_by_instrument(
            df_or_result, dataset, source_ticker, params
        )

    def _try_fetch_data_by_instrument(
        self,
        dataset: str,
        dataset_enum: Dataset,
        source_ticker: str,
        params: InstrumentIngestParams,
    ) -> pl.DataFrame | IngestionResult:
        """按标的尝试获取数据，失败时返回 IngestionResult。"""
        try:
            return self._fetch_by_dataset(dataset_enum, source_ticker, params)
        except Exception as e:
            return self._handle_fetch_error(
                e,
                dataset=dataset,
                date_identifier=params.start_date,
                context=f"fetching {dataset} for {source_ticker}",
                log_tag="during_fetch_by_instrument",
            )

    def _process_fetched_data_by_instrument(
        self,
        df: pl.DataFrame,
        dataset: str,
        source_ticker: str,
        params: InstrumentIngestParams,
    ) -> IngestionResult:
        """按标的处理获取的数据：写入。"""
        if df.is_empty():
            return self._result_handler.handle_empty_data(dataset, params.start_date)

        on_duplicate = OnDuplicate.KEEP_LAST

        try:
            write_result = self._data_writer.write_data(
                dataset, df, params.start_date, on_duplicate
            )
        except (
            pl.exceptions.ComputeError,
            pl.exceptions.SchemaError,
            ValueError,
            KeyError,
            TypeError,
            OSError,
        ) as e:
            logger.warning(
                "write_data_failed_by_instrument",
                event="write_data_error_by_instrument",
                dataset=dataset,
                source_ticker=source_ticker,
                error_type=type(e).__name__,
                error=str(e),
            )
            return self._result_handler.handle_unknown_error(
                dataset, params.start_date, e
            )
        except Exception as e:
            logger.exception(
                "write_data_failed_by_instrument_unexpected",
                event="write_data_error_by_instrument",
                dataset=dataset,
                source_ticker=source_ticker,
                error_type=type(e).__name__,
            )
            return self._result_handler.handle_unknown_error(
                dataset, params.start_date, e
            )

        if write_result.blocked:
            return self._result_handler.handle_dq_blocked(
                dataset, params.start_date, write_result
            )
        return self._result_handler.handle_success(
            dataset, params.start_date, df, write_result
        )

    def _fetch_by_dataset(
        self,
        dataset_enum: Dataset,
        source_ticker: str,
        params: InstrumentIngestParams,
    ) -> pl.DataFrame:
        """根据数据集类型调用对应的 fetch 方法（按标的）。"""
        handlers = build_instrument_fetch_handlers(self._source, source_ticker, params)

        if dataset_enum not in handlers:
            raise ValueError(f"不支持按标的摄取的数据集: {dataset_enum.value}")

        return handlers[dataset_enum]()

    def _fetch_data(self, dataset: str, trade_date: str) -> pl.DataFrame:
        """根据数据集类型调用对应的 Source 方法获取数据（日期级）。"""
        dataset_enum = _validate_dataset(dataset)

        handlers = build_daily_fetch_handlers(
            self._source,
            trade_date,
            fetch_commodity_daily=self._fetch_commodity_daily,
            get_cached_index_codes=self._get_cached_index_codes,
        )

        if dataset_enum not in handlers:
            raise ValueError(f"不支持的数据集: {dataset}")

        return handlers[dataset_enum]()

    def backfill_adj_factor(
        self,
        instrument_id: int,
        start: str,
        end: str,
    ) -> dict[str, object]:
        """按标的智能回补复权因子空洞，委托至 backfill_handler。"""
        return _backfill_adj_factor(
            instrument_id=instrument_id,
            start=start,
            end=end,
            ctx=BackfillContext(
                metadata_service=self._metadata_service,
                market_service=self._market_service,
                source=self._source,
                source_name=self._source_name,
                data_writer=self._data_writer,
            ),
        )
