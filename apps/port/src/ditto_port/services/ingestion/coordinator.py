"""
统一摄取协调器。

负责协调数据摄取的完整流程，包括：
- 调用 Source 获取数据
- 调用 Metadata 管理增量逻辑
- 调用 DataHub 写入数据
- 记录摄取日志
"""

from collections.abc import Callable
from datetime import date, timedelta
from typing import Literal, cast

import httpx
import polars as pl
from ditto_datahub.errors import AmbiguousTickerError, IdentifierNotFoundError
from ditto_datahub.models import (
    FX_CODE_TO_INSTRUMENT_ID,
    METAL_CODE_ALIASES,
    VIX_CODE_TO_INSTRUMENT_ID,
    Dataset,
    DateScheduleType,
    OnDuplicate,
)
from ditto_datahub.models.storage import WriteResult
from ditto_datahub.runtime.freeze_manager import FreezeManager
from ditto_datahub.services import IngestionCursorService, IngestionLogService
from ditto_datahub.services.capital_service import CapitalService
from ditto_datahub.services.fundamental_service import FundamentalService
from ditto_datahub.services.macro_service import MacroService
from ditto_datahub.services.market_service import MarketService
from ditto_datahub.services.metadata_service import MetadataService
from ditto_datahub.sources.base import DataSource
from ditto_infra.foundation import logger

from ditto_port.errors import NetworkError, SourceFetchError
from ditto_port.models import IngestionResult, InstrumentIngestParams
from ditto_port.services.ingestion.data_writer import IngestionDataWriter
from ditto_port.services.ingestion.index_config import get_all_index_codes
from ditto_port.services.ingestion.list_date_inference import (
    ListDateInferenceService,
)
from ditto_port.services.ingestion.metadata import MetadataManager
from ditto_port.services.ingestion.quality.service import QualityService
from ditto_port.services.ingestion.result_handler import IngestionResultHandler

# 支持按标的摄取的数据集
SUPPORTED_INSTRUMENT_DATASETS: set[Dataset] = {
    Dataset.STOCK_DAILY,
    Dataset.ETF_DAILY,
    Dataset.INDEX_DAILY,
    Dataset.ADJ_FACTOR,
    Dataset.FUND_ADJ,
    Dataset.STOCK_STATUS,
    Dataset.VALUATION_METRICS,
    Dataset.BALANCE_SHEET,
    Dataset.INCOME_STATEMENT,
    Dataset.CASH_FLOW,
    Dataset.DIVIDEND,
    Dataset.MARGIN_TRADING,
    Dataset.PLEDGE_RATIO,
}

# A股交易所代码前缀映射
# 用于从裸代码（如 "600519"）推断交易所后缀
EXCHANGE_PREFIX_MAP: dict[str, str] = {
    "60": "SH",  # 上交所主板
    "68": "SH",  # 上交所科创板
    "00": "SZ",  # 深交所主板
    "30": "SZ",  # 深交所创业板
    "8": "BJ",  # 北交所
    "4": "BJ",  # 北交所
}


def _infer_exchange_suffix(ticker: str) -> str | None:
    """
    从股票代码推断交易所后缀.

    Args:
        ticker: 裸股票代码（如 "600519"）

    Returns:
        交易所后缀（"SH", "SZ", "BJ"）或 None

    """
    for prefix, exchange in EXCHANGE_PREFIX_MAP.items():
        if ticker.startswith(prefix):
            return exchange
    return None


class IngestionCoordinator:
    """统一摄取协调器。"""

    def __init__(  # noqa: PLR0913
        self,
        metadata_service: MetadataService,
        market_service: MarketService,
        fundamental_service: FundamentalService,
        capital_service: CapitalService,
        macro_service: MacroService,
        source: DataSource,
        source_name: str = "tushare",
        ingestion_log_service: IngestionLogService | None = None,
        ingestion_cursor_service: IngestionCursorService | None = None,
        quality_service: QualityService | None = None,
        freeze_manager: FreezeManager | None = None,
        fred_source: DataSource | None = None,
    ) -> None:
        """初始化 IngestionCoordinator。"""
        self._metadata_service = metadata_service
        self._market_service = market_service
        self._fundamental_service = fundamental_service
        self._capital_service = capital_service
        self._macro_service = macro_service
        self._source = source
        self._source_name = source_name
        self._fred_source = fred_source
        self._ingestion_log_service = ingestion_log_service
        self._ingestion_cursor_service = ingestion_cursor_service
        self._quality_service = quality_service
        self._freeze_manager = freeze_manager
        self._metadata_manager = MetadataManager(ingestion_log_service)
        self._result_handler = IngestionResultHandler(
            ingestion_log_service, source_name
        )
        self._data_writer = IngestionDataWriter(
            metadata_service=metadata_service,
            market_service=market_service,
            fundamental_service=fundamental_service,
            capital_service=capital_service,
            macro_service=macro_service,
            source_name=source_name,
        )
        # list_date 推断服务（用于 basic 数据摄取后的补偿）
        self._list_date_inference = ListDateInferenceService(
            metadata_service=metadata_service,
            source=source,
            source_name=source_name,
        )
        # 缓存指数代码，避免每次摄取都调用 API
        self._index_codes_cache: list[str] | None = None

    def _fetch_commodity_daily(self, trade_date: str) -> pl.DataFrame:
        """
        获取商品数据（原油、贵金属、VIX）.

        数据源分配：
        - FRED: WTI 原油、布伦特原油、VIX
        - Tushare: 黄金、白银（FRED 数据已停止更新）

        Args:
            trade_date: 交易日期 (YYYY-MM-DD)

        Returns:
            合并后的商品数据 DataFrame

        """
        results: list[pl.DataFrame] = []

        # FRED 数据：原油和 VIX（排除已停止更新的贵金属）
        fred_codes = [
            "COMMOD_WTI",
            "COMMOD_BRENT",
            *list(VIX_CODE_TO_INSTRUMENT_ID.keys()),
        ]
        if self._fred_source:
            try:
                fred_df = self._fred_source.fetch_commodities(
                    codes=fred_codes,
                    start_date=trade_date,
                    end_date=trade_date,
                )
                if not fred_df.is_empty():
                    results.append(fred_df)
            except Exception as e:
                logger.warning(
                    "FRED commodity fetch failed, continuing with Tushare metals",
                    event="fred_commodity_fetch_failed",
                    error=str(e),
                )
        else:
            logger.warning(
                "FRED source not configured, skipping oil/VIX data",
                event="fred_not_configured",
            )

        # Tushare 数据：贵金属（黄金、白银）
        metal_codes = list(METAL_CODE_ALIASES.keys())
        try:
            metal_df = self._source.fetch_metal_daily(
                codes=metal_codes,
                start_date=trade_date,
                end_date=trade_date,
            )
            if not metal_df.is_empty():
                results.append(metal_df)
        except Exception as e:
            logger.warning(
                "Tushare metal fetch failed",
                event="tushare_metal_fetch_failed",
                error=str(e),
            )

        if not results:
            return pl.DataFrame()
        return pl.concat(results)

    @staticmethod
    def _is_source_fetch_error(error: Exception) -> bool:
        """Check whether exception should be treated as source fetch failure."""
        return isinstance(error, SourceFetchError) or (
            error.__class__.__name__ == "SourceFetchError"
        )

    @staticmethod
    def _normalize_source_fetch_error(error: Exception) -> SourceFetchError:
        """Normalize external fetch error into port-level SourceFetchError."""
        source_name = getattr(error, "source", type(error).__name__)
        return SourceFetchError(message=str(error), source=str(source_name))

    def _run_list_date_inference(self, dataset: str) -> None:
        """
        在 basic 数据摄取后执行 list_date 推断补偿。

        针对 list_date 为 NULL 的证券，从历史行情数据推断上市日期。

        Args:
            dataset: 数据集名称

        """
        # 仅对 basic 数据集执行推断
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
        except Exception as e:
            # 推断失败不影响主流程，仅记录警告
            logger.warning(
                f"list_date inference failed for {asset_class}",
                event="list_date_inference_error",
                dataset=dataset,
                asset_class=asset_class,
                error=str(e),
            )

    def _get_cached_index_codes(self) -> list[str]:
        """
        获取缓存的指数代码列表.

        首次调用时从 API 获取并缓存，后续调用直接返回缓存值。
        SW 行业指数代码不常变化，缓存可以避免每次摄取都调用 API。

        Returns:
            指数代码列表（包含市场指数、风格指数和 SW 行业指数）

        """
        if self._index_codes_cache is None:
            logger.debug("Caching index codes from API on first access")
            self._index_codes_cache = get_all_index_codes(
                self._source, include_sw_levels=[1, 2]
            )
            logger.debug(f"已缓存 {len(self._index_codes_cache)} 个指数代码")
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
        try:
            Dataset(dataset)  # 验证是否为有效的数据集
        except ValueError as e:
            raise ValueError(f"不支持的数据集: {dataset}") from e

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
        """
        检查是否应该跳过摄取。

        Returns:
            IngestionResult: 如果应该跳过，返回跳过结果
            None: 如果不应该跳过

        """
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
        """
        检查数据集是否需要交易日验证。

        对于交易日驱动数据集（market + 部分 capital），非交易日返回 False。
        其他数据集不需要交易日验证，返回 True。

        Args:
            dataset: 数据集名称
            trade_date: 交易日期

        Returns:
            bool: True 表示可以继续，False 表示应该跳过

        """
        # P0-2: 行情类数据集在非交易日静默跳过
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

    def _fetch_and_ingest(  # noqa: C901, PLR0911
        self, dataset: str, trade_date: str, force: bool
    ) -> IngestionResult:
        """获取数据并执行摄取（统一错误处理）。"""
        try:
            df = self._fetch_data(dataset, trade_date)
        except (httpx.NetworkError, httpx.TimeoutException) as e:
            # 网络相关异常，转换为 NetworkError
            logger.exception(
                "network_error_during_fetch",
                dataset=dataset,
                trade_date=trade_date,
                error_type=type(e).__name__,
            )
            network_error = NetworkError.from_httpx(
                error=e,
                source=self._source_name,
                context=f"fetching {dataset}",
            )
            # 转换为 SourceFetchError 以保持与现有处理流程的兼容性
            fetch_error = SourceFetchError(
                message=str(network_error),
                source=self._source_name,
                cause=network_error,
            )
            return self._result_handler.handle_fetch_error(
                dataset, trade_date, fetch_error
            )
        except Exception as e:
            if self._is_source_fetch_error(e):
                fetch_error = self._normalize_source_fetch_error(e)
                return self._result_handler.handle_fetch_error(
                    dataset, trade_date, fetch_error
                )
            # 未知异常，记录完整堆栈
            logger.exception(
                "unexpected_error_during_fetch",
                dataset=dataset,
                trade_date=trade_date,
                error_type=type(e).__name__,
            )
            return self._result_handler.handle_unknown_error(dataset, trade_date, e)

        if df.is_empty():
            return self._result_handler.handle_empty_data(dataset, trade_date)

        # DQ 质量检查
        if self._quality_service is not None:
            checked_df, should_block = self._quality_service.check_and_quarantine(
                df=df,
                dataset=dataset,
                context={"trade_date": trade_date},
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
        except Exception as e:
            logger.exception(
                "write_data_failed",
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

        # 更新摄入游标
        if self._ingestion_cursor_service is not None:
            try:
                self._ingestion_cursor_service.update_cursor(
                    dataset=dataset,
                    source=self._source_name,
                    last_success=trade_date,
                    last_attempted=trade_date,
                )
            except Exception as e:
                logger.warning(
                    "cursor_update_failed",
                    dataset=dataset,
                    trade_date=trade_date,
                    error=str(e),
                )

        # 创建冻结点（轻量级版本追踪）
        if self._freeze_manager is not None:
            try:
                self._freeze_manager.create(
                    freeze_id=f"{dataset}_{trade_date}",
                    description=f"Auto-freeze: {dataset} @ {trade_date}",
                    datasets=[dataset],
                )
            except Exception as e:
                logger.warning(
                    "freeze_create_failed",
                    dataset=dataset,
                    trade_date=trade_date,
                    error=str(e),
                )

        # 成功写入
        return self._result_handler.handle_success(
            dataset, trade_date, df, write_result
        )

    def ingest_range(
        self,
        dataset: str,
        start_date: str,
        end_date: str,
        force: bool = False,
    ) -> list[IngestionResult]:
        """
        摄取日期范围数据.

        根据数据集的日期调度类型选择日期序列：
        - TRADING_DAYS: 使用 A 股交易日历
        - NATURAL_DAYS: 使用自然日
        - SOURCE_DEFINED: 使用自然日（由数据源决定哪些日期有数据）

        Args:
            dataset: 数据集名称
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            force: 是否强制覆盖已有数据

        Returns:
            摄取结果列表

        """
        # 获取数据集的日期调度类型
        try:
            dataset_enum = Dataset(dataset)
        except ValueError:
            # 未知数据集，默认使用交易日
            dataset_enum = None

        default_schedule = DateScheduleType.TRADING_DAYS
        schedule_type = dataset_enum.date_schedule if dataset_enum else default_schedule

        # 根据调度类型获取日期列表
        match schedule_type:
            case DateScheduleType.TRADING_DAYS:
                dates = self._metadata_service.list_trading_days(start_date, end_date)
            case DateScheduleType.NATURAL_DAYS | DateScheduleType.SOURCE_DEFINED:
                dates = self._list_natural_days(start_date, end_date)

        if not dates:
            return []

        results: list[IngestionResult] = []
        for dt in dates:
            result = self.ingest_date(dataset, dt, force)
            results.append(result)

        return results

    @staticmethod
    def _list_natural_days(start_date: str, end_date: str) -> list[str]:
        """
        生成自然日列表.

        Args:
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)

        Returns:
            日期字符串列表 (YYYY-MM-DD)

        """
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)

        days: list[str] = []
        current = start
        while current <= end:
            days.append(current.isoformat())
            current += timedelta(days=1)

        return days

    def ingest_by_instrument(
        self,
        dataset: str,
        params: InstrumentIngestParams,
        force: bool = False,
    ) -> IngestionResult:
        """
        按标的 + 日期范围摄取数据.

        Args:
            dataset: 数据集名称（如 stock_daily, etf_daily）
            params: 摄取参数（含 instrument_id/standard_ticker/ticker,
                start_date, end_date）
            force: 是否强制覆盖已有数据

        Returns:
            IngestionResult: 摄取结果

        Raises:
            ValueError: 不支持的数据集

        """
        # 验证数据集是否支持按标的摄取
        try:
            dataset_enum = Dataset(dataset)
        except ValueError as e:
            raise ValueError(f"不支持的数据集: {dataset}") from e

        # 检查数据集是否在支持列表中（基于实际支持的 handler）
        if dataset_enum not in SUPPORTED_INSTRUMENT_DATASETS:
            raise ValueError(f"数据集 {dataset} 不支持按标的摄取")

        # 从数据集推断资产类型
        asset_class = dataset_enum.asset_class
        if asset_class is None:
            raise ValueError(f"数据集 {dataset} 缺少 asset_class 定义")

        # 解析标识符为 source_ticker
        source_ticker = self._resolve_identifier_with_auto_init(
            params, asset_class, dataset
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
            dataset, dataset_enum, source_ticker, params, force
        )

    def _resolve_identifier_with_auto_init(
        self,
        params: InstrumentIngestParams,
        asset_class: str,
        dataset: str,
    ) -> str:
        """
        解析标识符，如果失败则尝试自动初始化证券信息.

        对于股票类型，如果标识符未找到，会尝试从数据源获取
        该股票的基本信息并注册，然后重试解析。

        Args:
            params: 摄取参数
            asset_class: 资产类别
            dataset: 数据集名称（用于日志）

        Returns:
            解析后的 source_ticker

        Raises:
            AmbiguousTickerError: 标识符模糊
            IdentifierNotFoundError: 标识符未找到且无法自动初始化

        """
        try:
            return self._metadata_service.resolve_source_ticker(
                ticker=params.ticker,
                standard_ticker=params.standard_ticker,
                instrument_id=params.instrument_id,
                asset_class=asset_class,
                source=self._source_name,
            )
        except AmbiguousTickerError:
            # 模糊标识符无法自动修复
            raise
        except IdentifierNotFoundError as e:
            # 仅对股票类型尝试自动初始化
            if asset_class != "stock":
                logger.error(
                    "标识符解析失败",
                    event="identifier_resolution_failed",
                    dataset=dataset,
                    error=str(e),
                )
                raise

            # 尝试自动初始化
            return self._auto_init_stock_instrument(params, dataset, e)

    def _auto_init_stock_instrument(
        self,
        params: InstrumentIngestParams,
        dataset: str,
        original_error: IdentifierNotFoundError,
    ) -> str:
        """
        自动初始化股票证券信息.

        从 Tushare 获取股票基本信息并注册，然后返回 source_ticker。

        Args:
            params: 摄取参数
            dataset: 数据集名称
            original_error: 原始的标识符未找到错误

        Returns:
            source_ticker

        Raises:
            IdentifierNotFoundError: 如果无法获取股票信息

        """
        # 构建可能的 source_ticker 格式
        # 用户可能传入裸代码（如 "600519"）或标准格式（如 "600519.SH"）
        ticker = params.ticker or (
            params.standard_ticker.split(".")[0] if params.standard_ticker else None
        )

        if not ticker:
            logger.error(
                "无法确定股票代码",
                event="auto_init_missing_ticker",
                dataset=dataset,
            )
            raise original_error

        # 尝试构建 source_ticker（需要判断交易所）
        exchange_suffix = _infer_exchange_suffix(ticker)
        if exchange_suffix:
            source_ticker = f"{ticker}.{exchange_suffix}"
        else:
            logger.error(
                "无法确定交易所",
                event="auto_init_unknown_exchange",
                ticker=ticker,
            )
            raise original_error

        logger.info(
            "尝试自动初始化股票信息",
            event="auto_init_stock_start",
            source_ticker=source_ticker,
            dataset=dataset,
        )

        # 从 Tushare 获取股票基本信息
        try:
            basic_df = self._source.fetch_stock_basic(source_ticker)
        except Exception as fetch_error:
            logger.error(
                "获取股票基本信息失败",
                event="auto_init_fetch_failed",
                source_ticker=source_ticker,
                error=str(fetch_error),
            )
            raise original_error from fetch_error

        if basic_df.is_empty():
            logger.warning(
                "股票在数据源中不存在",
                event="auto_init_stock_not_found",
                source_ticker=source_ticker,
            )
            raise original_error  # 无底层异常：股票不存在是业务条件，非错误

        # 注册证券
        try:
            self._metadata_service.register_instruments_batch(
                df=basic_df,
                source=self._source_name,
                asset_class="stock",
                source_ticker_col="source_ticker",
            )
        except Exception as register_error:
            logger.error(
                "注册证券失败",
                event="auto_init_register_failed",
                source_ticker=source_ticker,
                error=str(register_error),
            )
            raise original_error from register_error

        logger.info(
            "自动初始化股票信息成功",
            event="auto_init_stock_success",
            source_ticker=source_ticker,
        )

        return source_ticker

    def _fetch_and_ingest_by_instrument(  # noqa: PLR0911
        self,
        dataset: str,
        dataset_enum: Dataset,
        source_ticker: str,
        params: InstrumentIngestParams,
        force: bool,
    ) -> IngestionResult:
        """按标的获取数据并执行摄取（统一错误处理）。"""
        try:
            df = self._fetch_by_dataset(dataset_enum, source_ticker, params)
        except (httpx.NetworkError, httpx.TimeoutException) as e:
            # 网络相关异常，转换为 NetworkError
            logger.exception(
                "network_error_during_fetch_by_instrument",
                dataset=dataset,
                source_ticker=source_ticker,
                error_type=type(e).__name__,
            )
            network_error = NetworkError.from_httpx(
                error=e,
                source=self._source_name,
                context=f"fetching {dataset} for {source_ticker}",
            )
            # 转换为 SourceFetchError 以保持与现有处理流程的兼容性
            fetch_error = SourceFetchError(
                message=str(network_error),
                source=self._source_name,
                cause=network_error,
            )
            return self._result_handler.handle_fetch_error(
                dataset, params.start_date, fetch_error
            )
        except Exception as e:
            if self._is_source_fetch_error(e):
                fetch_error = self._normalize_source_fetch_error(e)
                return self._result_handler.handle_fetch_error(
                    dataset, params.start_date, fetch_error
                )
            logger.exception(
                "unexpected_error_during_fetch_by_instrument",
                dataset=dataset,
                source_ticker=source_ticker,
                error_type=type(e).__name__,
            )
            return self._result_handler.handle_unknown_error(
                dataset, params.start_date, e
            )

        if df.is_empty():
            return self._result_handler.handle_empty_data(dataset, params.start_date)

        # 按标的摄取默认使用 KEEP_LAST，确保重复摄取幂等
        # （按标的摄取没有摄取日志检查机制，因此需要依赖存储层覆盖）
        on_duplicate = OnDuplicate.KEEP_LAST

        try:
            write_result = self._data_writer.write_data(
                dataset, df, params.start_date, on_duplicate
            )
        except Exception as e:
            logger.exception(
                "write_data_failed_by_instrument",
                dataset=dataset,
                source_ticker=source_ticker,
                error_type=type(e).__name__,
            )
            return self._result_handler.handle_unknown_error(
                dataset, params.start_date, e
            )

        # 检查 DQ 阻断
        if write_result.blocked:
            return self._result_handler.handle_dq_blocked(
                dataset, params.start_date, write_result
            )

        # 成功写入
        return self._result_handler.handle_success(
            dataset, params.start_date, df, write_result
        )

    def _fetch_by_dataset(
        self,
        dataset_enum: Dataset,
        source_ticker: str,
        params: InstrumentIngestParams,
    ) -> pl.DataFrame:
        """
        根据数据集类型调用对应的 fetch 方法.

        Args:
            dataset_enum: 数据集枚举
            source_ticker: 数据源代码
            params: 摄取参数

        Returns:
            数据 DataFrame

        """
        handlers: dict[Dataset, Callable[[], pl.DataFrame]] = {
            # Market 域
            Dataset.STOCK_DAILY: lambda: self._source.fetch_stock_daily(
                source_ticker=source_ticker,
                start_date=params.start_date,
                end_date=params.end_date,
            ),
            Dataset.ETF_DAILY: lambda: self._source.fetch_etf_daily(
                source_ticker=source_ticker,
                start_date=params.start_date,
                end_date=params.end_date,
            ),
            Dataset.INDEX_DAILY: lambda: self._source.fetch_index_daily(
                source_ticker=source_ticker,
                start_date=params.start_date,
                end_date=params.end_date,
            ),
            Dataset.ADJ_FACTOR: lambda: self._source.fetch_adj_factor_by_ticker(
                ts_code=source_ticker,
                start_date=params.start_date.replace("-", ""),
                end_date=params.end_date.replace("-", ""),
            ),
            Dataset.FUND_ADJ: lambda: self._source.fetch_fund_adj(
                source_ticker=source_ticker,
                start_date=params.start_date,
                end_date=params.end_date,
            ),
            # Fundamental 域
            Dataset.BALANCE_SHEET: lambda: self._source.fetch_balance_sheet(
                source_ticker=source_ticker,
                start_date=params.start_date,
                end_date=params.end_date,
            ),
            Dataset.INCOME_STATEMENT: lambda: self._source.fetch_income_statement(
                source_ticker=source_ticker,
                start_date=params.start_date,
                end_date=params.end_date,
            ),
            Dataset.CASH_FLOW: lambda: self._source.fetch_cash_flow(
                source_ticker=source_ticker,
                start_date=params.start_date,
                end_date=params.end_date,
            ),
            Dataset.DIVIDEND: lambda: self._source.fetch_dividend(
                source_ticker=source_ticker,
                start_date=params.start_date,
                end_date=params.end_date,
            ),
            # Capital 域
            Dataset.VALUATION_METRICS: lambda: self._source.fetch_valuation_metrics(
                source_ticker=source_ticker,
                start_date=params.start_date,
                end_date=params.end_date,
            ),
            Dataset.MARGIN_TRADING: lambda: self._source.fetch_margin_trading(
                source_ticker=source_ticker,
                start_date=params.start_date,
                end_date=params.end_date,
            ),
            Dataset.PLEDGE_RATIO: lambda: self._source.fetch_pledge_ratio(
                source_ticker=source_ticker,
                start_date=params.start_date,
                end_date=params.end_date,
            ),
        }

        if dataset_enum not in handlers:
            raise ValueError(f"不支持按标的摄取的数据集: {dataset_enum.value}")

        return handlers[dataset_enum]()

    def _fetch_data(self, dataset: str, trade_date: str) -> pl.DataFrame:
        """
        根据数据集类型调用对应的 Source 方法获取数据。

        使用字典映射替代动态 getattr 调用，易于扩展新数据集。
        """
        # 转换为枚举
        try:
            dataset_enum = Dataset(dataset)
        except ValueError as e:
            raise ValueError(f"不支持的数据集: {dataset}") from e

        # 定义数据集获取函数映射（使用枚举作为键）
        # 交易日历特殊处理：使用整年日期范围
        _calendar_year = trade_date[:4]  # 从 trade_date 提取年份
        handlers: dict[Dataset, Callable[[], pl.DataFrame]] = {
            Dataset.CALENDAR: lambda y=_calendar_year: self._source.fetch_calendar(
                f"{y}-01-01", f"{y}-12-31"
            ),
            Dataset.STOCK_BASIC: self._source.fetch_stock_basic,
            Dataset.ETF_BASIC: self._source.fetch_etf_basic,
            Dataset.STOCK_DAILY: lambda: self._source.fetch_stock_daily(trade_date),
            Dataset.ETF_DAILY: lambda: self._source.fetch_etf_daily(trade_date),
            Dataset.STOCK_STATUS: lambda: self._source.fetch_stock_status(trade_date),
            Dataset.ADJ_FACTOR: lambda: self._source.fetch_adj_factor(trade_date),
            Dataset.FUND_ADJ: lambda: self._source.fetch_fund_adj(trade_date),
            Dataset.BALANCE_SHEET: lambda: self._source.fetch_balance_sheet(trade_date),
            Dataset.INCOME_STATEMENT: lambda: self._source.fetch_income_statement(
                trade_date
            ),
            Dataset.CASH_FLOW: lambda: self._source.fetch_cash_flow(trade_date),
            Dataset.DIVIDEND: lambda: self._source.fetch_dividend(trade_date),
            Dataset.VALUATION_METRICS: lambda: self._source.fetch_valuation_metrics(
                trade_date
            ),
            Dataset.MARGIN_TRADING: lambda: self._source.fetch_margin_trading(
                trade_date
            ),
            Dataset.PLEDGE_RATIO: lambda: self._source.fetch_pledge_ratio(trade_date),
            Dataset.MACRO_INDICATORS: lambda: self._source.fetch_macro_indicators(
                trade_date
            ),
            Dataset.CORPORATE_ACTIONS: lambda: self._source.fetch_corporate_actions(
                trade_date
            ),
            Dataset.INDEX_BASIC: self._source.fetch_index_basic,
            Dataset.INDEX_DAILY: lambda: self._source.fetch_index_daily(
                trade_date,
                ts_codes=self._get_cached_index_codes(),
            ),
            # Market 域扩展（汇率/商品）
            Dataset.FX_DAILY: lambda: self._source.fetch_fx_daily(
                ts_codes=list(FX_CODE_TO_INSTRUMENT_ID.keys()),
                start_date=trade_date,
                end_date=trade_date,
            ),
            Dataset.COMMODITY_DAILY: lambda: self._fetch_commodity_daily(trade_date),
        }

        if dataset_enum not in handlers:
            raise ValueError(f"不支持的数据集: {dataset}")

        return handlers[dataset_enum]()

    # ------------------------------------------------------------------
    # 智能回填
    # ------------------------------------------------------------------

    def backfill_adj_factor(
        self,
        instrument_id: int,
        start: str,
        end: str,
    ) -> dict[str, object]:
        """
        按标的智能回补复权因子空洞.

        检测指定证券在 [start, end] 日期范围内的复权因子空洞，
        仅对缺失的连续日期区间发起数据源请求，避免全量覆盖。

        流程:
        1. 解析 instrument_id → source_ticker
        2. 获取 [start, end] 内全部交易日
        3. 查询已有的复权因子日期
        4. 计算差集得到空洞日期
        5. 将空洞按连续区间分组，逐段 fetch + 写入

        Args:
            instrument_id: 证券内部 ID.
            start: 开始日期 (YYYY-MM-DD).
            end: 结束日期 (YYYY-MM-DD).

        Returns:
            回补结果摘要，包含 status / gap_count / filled_dates.

        """
        logger.info(
            "开始智能回补复权因子",
            event="backfill_adj_factor_start",
            instrument_id=instrument_id,
            start=start,
            end=end,
        )

        # 1. 解析 source_ticker
        source_ticker = self._metadata_service.resolve_source_ticker(
            instrument_id=instrument_id,
            asset_class="stock",
            source=self._source_name,
        )

        # 2. 获取交易日列表
        trading_days = self._metadata_service.list_trading_days(start, end)
        if not trading_days:
            logger.info(
                "范围内无交易日",
                event="backfill_adj_factor_no_trading_days",
                instrument_id=instrument_id,
            )
            return {"status": "ok", "gap_count": 0, "filled_dates": 0}

        trading_day_set: set[str] = set(trading_days)

        # 3. 查询已有复权因子日期
        existing_df = self._market_service.get_adj_factors(start, end)
        existing_dates: set[str] = set()
        if not existing_df.is_empty():
            existing_dates = set(
                existing_df.filter(pl.col("instrument_id") == instrument_id)
                .select("trade_date")
                .to_series()
                .cast(pl.String)
                .to_list()
            )

        # 4. 计算空洞
        gap_dates = sorted(trading_day_set - existing_dates)
        if not gap_dates:
            logger.info(
                "复权因子数据完整 无需回补",
                event="backfill_adj_factor_no_gaps",
                instrument_id=instrument_id,
            )
            return {"status": "ok", "gap_count": 0, "filled_dates": 0}

        # 5. 将空洞按连续区间分组
        gap_ranges = self._group_contiguous_dates(gap_dates)

        # 6. 逐段 fetch + 写入
        total_filled = 0
        for range_start, range_end in gap_ranges:
            try:
                gap_df = self._source.fetch_adj_factor_by_ticker(
                    ts_code=source_ticker,
                    start_date=range_start.replace("-", ""),
                    end_date=range_end.replace("-", ""),
                )
            except Exception as e:
                logger.warning(
                    "回补 fetch 失败",
                    event="backfill_adj_factor_fetch_failed",
                    instrument_id=instrument_id,
                    range_start=range_start,
                    range_end=range_end,
                    error=str(e),
                )
                continue

            if gap_df.is_empty():
                continue

            # 写入 — 使用 OnDuplicate.KEEP_LAST 保证幂等
            try:
                self._data_writer.write_data(
                    "adj_factor", gap_df, range_start, OnDuplicate.KEEP_LAST
                )
            except Exception as e:
                logger.warning(
                    "回补写入失败",
                    event="backfill_adj_factor_write_failed",
                    instrument_id=instrument_id,
                    range_start=range_start,
                    range_end=range_end,
                    error=str(e),
                )
                continue

            total_filled += len(gap_df)

        logger.info(
            "智能回补复权因子完成",
            event="backfill_adj_factor_complete",
            instrument_id=instrument_id,
            gap_count=len(gap_ranges),
            filled_dates=total_filled,
        )

        return {
            "status": "ok",
            "gap_count": len(gap_ranges),
            "filled_dates": total_filled,
        }

    @staticmethod
    def _group_contiguous_dates(dates: list[str]) -> list[tuple[str, str]]:
        """
        将日期列表按连续区间分组.

        对于 [2024-01-02, 2024-01-03, 2024-01-05, 2024-01-06]，
        返回 [("2024-01-02", "2024-01-03"), ("2024-01-05", "2024-01-06")]。

        Args:
            dates: 已排序的日期字符串列表 (YYYY-MM-DD).

        Returns:
            连续区间列表 [(start, end), ...].

        """
        if not dates:
            return []

        ranges: list[tuple[str, str]] = []
        range_start = dates[0]
        prev = date.fromisoformat(dates[0])

        for d_str in dates[1:]:
            d = date.fromisoformat(d_str)
            if (d - prev).days <= 1:
                prev = d
            else:
                ranges.append((range_start, prev.isoformat()))
                range_start = d_str
                prev = d

        ranges.append((range_start, prev.isoformat()))
        return ranges
