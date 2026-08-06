"""摄取协调器 — IngestionCoordinator (facade)."""

from __future__ import annotations

from typing import NamedTuple

import polars as pl
from ditto_data.models import Dataset
from ditto_data.models.ingestion import IngestionQualityEvidence, IngestionResult
from ditto_data.services.capital_store import CapitalStore
from ditto_data.services.fundamental_store import FundamentalStore
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
from ditto_application.processes.ingestion.commodity_fetcher import (
    fetch_commodity_range as _fetch_commodity_range,
)
from ditto_application.processes.ingestion.config import IngestionCoordinatorConfig
from ditto_application.processes.ingestion.coordinator_constants import (
    get_all_index_codes,
)
from ditto_application.processes.ingestion.data_writer import IngestionDataWriter
from ditto_application.processes.ingestion.dataset_registry import (
    default_dataset_registry,
)
from ditto_application.processes.ingestion.date_range import list_ingestion_dates
from ditto_application.processes.ingestion.fetch_handlers import (
    build_daily_fetch_handlers,
)
from ditto_application.processes.ingestion.instrument_ingestion import (
    InstrumentBackfillContext,
    InstrumentIngestContext,
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
    DataWriteContext,
    PostIngestContext,
    is_sparse_pit_dataset,
    resolve_sparse_asof_snapshot,
)
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
from ditto_application.processes.ingestion.source_capability import (
    ensure_source_supported,
)
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


class MarketServices(NamedTuple):
    """Market 域读写服务聚合."""

    query: MarketService
    write: MarketWriteService


class IngestionServices(NamedTuple):
    """域级写入服务聚合."""

    metadata: MetadataService
    market: MarketServices
    fundamental: FundamentalStore
    capital: CapitalStore
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
        self._fundamental_store = services.fundamental
        self._capital_store = services.capital
        self._macro_service = services.macro
        self._fetchers = fetchers
        self._source_name = cfg.source_name
        self._fred_source = fred_source
        self._ingestion_log_store = cfg.ingestion_log_store
        self._ingestion_cursor_store = cfg.ingestion_cursor_store
        self._quality_checker = cfg.quality_checker
        self._freeze_store = cfg.freeze_store
        self._lineage_recorder = cfg.lineage_recorder
        self._catalog_reader = cfg.catalog_reader
        self._catalog_writer = cfg.catalog_writer
        self._evidence_committer = cfg.evidence_committer
        self._license_record_id = cfg.license_record_id

        self._metadata_manager = MetadataManager(
            cfg.ingestion_log_store,
            data_catalog_reader=cfg.catalog_reader,
        )
        self._result_handler = IngestionResultHandler(
            cfg.ingestion_log_store, cfg.source_name
        )
        self._data_writer = IngestionDataWriter(
            metadata_service=services.metadata,
            market_write_service=services.market.write,
            fundamental_store=services.fundamental,
            capital_store=services.capital,
            macro_service=services.macro,
            source_name=cfg.source_name,
        )

        self._list_date_inference = ListDateInferenceService(
            metadata_service=services.metadata,
            source=fetchers.market,
            source_name=cfg.source_name,
        )

        self._index_codes_cache: list[str] | None = None
        self._registry = default_dataset_registry()

    def _fetch_commodity_daily(self, trade_date: str) -> pl.DataFrame:
        """获取商品数据（原油、贵金属、VIX），委托至 ``commodity_fetcher``。"""
        return _fetch_commodity_daily(
            trade_date,
            primary_source=self._fetchers.macro,
            fred_source=self._fred_source,
        )

    def _fetch_source_defined_range(
        self,
        dataset: str,
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        """Use provider-native range APIs for source-defined products."""
        if dataset == "commodity_daily":
            return _fetch_commodity_range(
                start_date,
                end_date,
                primary_source=self._fetchers.macro,
                fred_source=self._fred_source,
            )
        if dataset == "macro_indicators":
            range_fetch = getattr(
                self._fetchers.macro,
                "fetch_macro_indicators_range",
                None,
            )
            if not callable(range_fetch):
                raise AppProcessError(
                    "macro source does not support bounded range ingestion"
                )
            value = range_fetch(start_date, end_date)
            if not isinstance(value, pl.DataFrame):
                raise AppProcessError("macro range fetch returned invalid payload")
            return value
        raise AppProcessError(f"unsupported source-defined range dataset: {dataset}")

    def _fetch_sparse_range(
        self,
        dataset: str,
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        """Fetch sparse PIT events with one product-specific bounded request."""
        range_fetch = getattr(
            self._fetchers.fundamental,
            f"fetch_{dataset}_range",
            None,
        )
        if not callable(range_fetch):
            raise AppProcessError(
                f"sparse source does not support bounded range ingestion: {dataset}"
            )
        value = range_fetch(start_date, end_date)
        if not isinstance(value, pl.DataFrame):
            raise AppProcessError("sparse range fetch returned invalid payload")
        return value

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

        dataset_enum = _validate_dataset(dataset)
        ensure_source_supported(dataset_enum, self._source_name)

        if skip_result := self._check_should_skip(dataset, trade_date, force):
            return skip_result

        if not self._is_trading_day_for_dataset(dataset, trade_date):
            return self._create_skipped_result(dataset, trade_date, "非交易日, 跳过")

        return self._fetch_and_ingest(dataset, trade_date, force)

    def _check_should_skip(
        self, dataset: str, trade_date: str, force: bool
    ) -> IngestionResult | None:
        """检查是否应该跳过摄取。"""
        decision = self._metadata_manager.get_skip_decision(
            dataset=dataset,
            trade_date=trade_date,
            source=self._source_name,
            force=force,
        )
        if decision.should_skip:
            quality_evidence = (
                IngestionQualityEvidence(
                    kind="persisted_ingestion_l1_l2",
                    status="passed",
                    source=self._source_name,
                    trade_date=trade_date,
                    levels=("l1", "l2"),
                    row_count=decision.row_count,
                    checksum=decision.checksum,
                )
                if isinstance(decision.checksum, str)
                and decision.checksum
                and isinstance(decision.row_count, int)
                and not isinstance(decision.row_count, bool)
                and decision.row_count >= 0
                else None
            )
            if is_sparse_pit_dataset(dataset):
                snapshot_evidence = resolve_sparse_asof_snapshot(
                    dataset=dataset,
                    trade_date=trade_date,
                    source_name=self._source_name,
                    catalog_reader=self._catalog_reader,
                )
                if snapshot_evidence is None or quality_evidence is None:
                    return None
                return IngestionResult(
                    dataset=dataset,
                    trade_date=trade_date,
                    status="skipped",
                    row_count=decision.row_count,
                    checksum=None,
                    message=decision.reason or "数据已存在且摄取成功",
                    snapshot_evidence=snapshot_evidence,
                    quality_evidence=quality_evidence,
                )
            return IngestionResult(
                dataset=dataset,
                trade_date=trade_date,
                status="skipped",
                row_count=decision.row_count,
                checksum=decision.checksum,
                message=decision.reason or "数据已存在且摄取成功",
                quality_evidence=quality_evidence,
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
            Dataset.INDEX_WEIGHT,
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
            ctx=PostIngestContext(
                result_handler=self._result_handler,
                data_writer=self._data_writer,
                quality_checker=self._quality_checker,
                list_date_inference=self._list_date_inference,
                catalog_reader=self._catalog_reader,
                cursor_store=self._ingestion_cursor_store,
                freeze_store=self._freeze_store,
                lineage_recorder=self._lineage_recorder,
                catalog_writer=self._catalog_writer,
                source_name=self._source_name,
                evidence_committer=self._evidence_committer,
                license_record_id=self._license_record_id,
            ),
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
            DataWriteContext(
                dataset=dataset,
                df=df,
                trade_date=trade_date,
                on_duplicate=on_duplicate,
                source_ticker=source_ticker,
                event_suffix=event_suffix,
            ),
            result_handler=self._result_handler,
            data_writer=self._data_writer,
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
        dates = list_ingestion_dates(
            dataset,
            start_date,
            end_date,
            metadata_service=self._metadata_service,
            registry=self._registry,
        )

        if not dates:
            return []

        results: list[IngestionResult] = []
        for dt in dates:
            result = self.ingest_date(dataset, dt, force)
            results.append(result)
        return results

    def ingest_chunk(
        self,
        dataset: str,
        *,
        chunk_id: str,
        request_start: str,
        request_end: str,
        partition_dates: tuple[str, ...],
        force: bool = False,
    ) -> IngestionResult:
        """Fetch a planned same-year chunk and persist it as one durable payload."""
        dataset_enum = _validate_dataset(dataset)
        ensure_source_supported(dataset_enum, self._source_name)
        if not partition_dates:
            raise AppProcessError("ingestion chunk has no partitions")
        normalized_dates = tuple(sorted(set(partition_dates)))
        if normalized_dates != partition_dates:
            raise AppProcessError(
                "ingestion chunk partitions must be unique and sorted"
            )
        if normalized_dates[0] < request_start or normalized_dates[-1] > request_end:
            raise AppProcessError("ingestion chunk partition outside request interval")
        if len({value[:4] for value in normalized_dates}) != 1:
            raise AppProcessError("ingestion chunk cannot cross a storage year")

        combined = self._fetch_planned_chunk(
            dataset,
            normalized_dates,
            request_start=request_start,
            request_end=request_end,
        )
        if isinstance(combined, IngestionResult):
            return combined
        return _process_fetched_data(
            combined,
            dataset,
            request_start,
            force,
            ctx=PostIngestContext(
                result_handler=self._result_handler,
                data_writer=self._data_writer,
                quality_checker=self._quality_checker,
                list_date_inference=self._list_date_inference,
                catalog_reader=self._catalog_reader,
                cursor_store=self._ingestion_cursor_store,
                freeze_store=self._freeze_store,
                lineage_recorder=self._lineage_recorder,
                catalog_writer=self._catalog_writer,
                source_name=self._source_name,
                evidence_committer=self._evidence_committer,
                license_record_id=self._license_record_id,
            ),
            request_end=request_end,
            chunk_id=chunk_id,
        )

    def _fetch_planned_chunk(
        self,
        dataset: str,
        partition_dates: tuple[str, ...],
        *,
        request_start: str,
        request_end: str,
    ) -> pl.DataFrame | IngestionResult:
        """Fetch one planned range while preserving typed fetch failures."""
        if dataset in {"macro_indicators", "commodity_daily"}:
            return self._fetch_range_chunk(
                dataset,
                request_start=request_start,
                request_end=request_end,
                sparse=False,
            )
        if dataset in {
            "balance_sheet",
            "income_statement",
            "cash_flow",
            "dividend",
            "corporate_actions",
        }:
            return self._fetch_range_chunk(
                dataset,
                request_start=request_start,
                request_end=request_end,
                sparse=True,
            )
        frames: list[pl.DataFrame] = []
        for partition_date in partition_dates:
            fetched = self._try_fetch_data(dataset, partition_date)
            if isinstance(fetched, IngestionResult):
                return fetched
            if not fetched.is_empty():
                frames.append(fetched)
        return pl.concat(frames, how="diagonal_relaxed") if frames else pl.DataFrame()

    def _fetch_range_chunk(
        self,
        dataset: str,
        *,
        request_start: str,
        request_end: str,
        sparse: bool,
    ) -> pl.DataFrame | IngestionResult:
        kind = "sparse" if sparse else "source-defined"
        try:
            fetched = (
                self._fetch_sparse_range(dataset, request_start, request_end)
                if sparse
                else self._fetch_source_defined_range(
                    dataset,
                    request_start,
                    request_end,
                )
            )
        except Exception as error:
            return _handle_fetch_error(
                error,
                dataset=dataset,
                date_identifier=request_start,
                context=f"fetching {kind} range {dataset}",
                log_tag=f"during_{kind.replace('-', '_')}_range",
                source_name=self._source_name,
                result_handler=self._result_handler,
            )
        return fetched

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
            ctx=InstrumentIngestContext(
                fetchers=self._fetchers,
                metadata_service=self._metadata_service,
                source_name=self._source_name,
                result_handler=self._result_handler,
                data_writer=self._data_writer,
                lineage_recorder=self._lineage_recorder,
                catalog_writer=self._catalog_writer,
                quality_checker=self._quality_checker,
                evidence_committer=self._evidence_committer,
                license_record_id=self._license_record_id,
            ),
        )

    def ingest_planned_instrument_chunk(
        self,
        dataset: str,
        *,
        chunk_id: str,
        params: InstrumentIngestParams,
        force: bool = False,
    ) -> IngestionResult:
        """Ingest one instrument range and commit the planner checkpoint identity."""
        return _ingest_by_instrument_impl(
            dataset,
            params,
            force,
            ctx=InstrumentIngestContext(
                fetchers=self._fetchers,
                metadata_service=self._metadata_service,
                source_name=self._source_name,
                result_handler=self._result_handler,
                data_writer=self._data_writer,
                lineage_recorder=self._lineage_recorder,
                catalog_writer=self._catalog_writer,
                quality_checker=self._quality_checker,
                evidence_committer=self._evidence_committer,
                license_record_id=self._license_record_id,
            ),
            chunk_id=chunk_id,
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
            ctx=InstrumentBackfillContext(
                metadata_service=self._metadata_service,
                market_service=self._market_service,
                fetchers=self._fetchers,
                source_name=self._source_name,
                data_writer=self._data_writer,
                lineage_recorder=self._lineage_recorder,
            ),
        )
