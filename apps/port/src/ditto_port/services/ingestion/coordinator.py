"""
统一摄取协调器。

负责协调数据摄取的完整流程，包括：
- 调用 Source 获取数据
- 调用 Metadata 管理增量逻辑
- 调用 DataHub 写入数据
- 记录摄取日志
"""

from collections.abc import Callable

import httpx
import polars as pl
from ditto_datahub.hub import DataHub
from ditto_datahub.models import Dataset, OnDuplicate
from ditto_foundation import logger

from ditto_port.models import IngestionResult
from ditto_port.services.ingestion.data_writer import IngestionDataWriter
from ditto_port.services.ingestion.errors import SourceFetchError
from ditto_port.services.ingestion.metadata import MetadataManager
from ditto_port.services.ingestion.protocols import IngestionDataSource
from ditto_port.services.ingestion.result_handler import IngestionResultHandler


class IngestionCoordinator:
    """统一摄取协调器。"""

    def __init__(
        self,
        hub: DataHub,
        source: IngestionDataSource,
        source_name: str = "tushare",
    ) -> None:
        """初始化 IngestionCoordinator。"""
        self._hub = hub
        self._source = source
        self._source_name = source_name
        self._metadata_manager = MetadataManager(hub)
        self._result_handler = IngestionResultHandler(hub, source_name)
        self._data_writer = IngestionDataWriter(hub, source_name)

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
            Dataset.STOCK_STATUS,
            Dataset.ADJ_FACTOR,
            Dataset.FUND_ADJ,
            Dataset.VALUATION_METRICS,
            Dataset.MARGIN_TRADING,
        ):
            return self._hub.calendar.is_trading_day(trade_date)
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

    def _fetch_and_ingest(  # noqa: PLR0911
        self, dataset: str, trade_date: str, force: bool
    ) -> IngestionResult:
        """获取数据并执行摄取（统一错误处理）。"""
        try:
            df = self._fetch_data(dataset, trade_date)
        except (httpx.NetworkError, httpx.TimeoutException) as e:
            # 网络相关异常，记录后转换为业务异常
            logger.exception(
                "network_error_during_fetch",
                dataset=dataset,
                trade_date=trade_date,
                error_type=type(e).__name__,
            )
            fetch_error = SourceFetchError(
                message=f"Network error fetching {dataset}: {e}",
                source=type(e).__name__,
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
        """摄取日期范围数据。"""
        trade_dates = self._hub.calendar.list_trading_days(start_date, end_date)

        if not trade_dates:
            return []

        results: list[IngestionResult] = []
        for trade_date in trade_dates:
            result = self.ingest_date(dataset, trade_date, force)
            results.append(result)

        return results

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
        handlers: dict[Dataset, Callable[[], pl.DataFrame]] = {
            Dataset.CALENDAR: lambda: self._source.fetch_calendar(
                trade_date, trade_date
            ),
            Dataset.STOCK_BASIC: lambda: self._source.fetch_stock_basic(),
            Dataset.ETF_BASIC: lambda: self._source.fetch_etf_basic(),
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
        }

        if dataset_enum not in handlers:
            raise ValueError(f"不支持的数据集: {dataset}")

        return handlers[dataset_enum]()
