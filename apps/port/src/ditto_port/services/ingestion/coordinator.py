"""
统一摄取协调器。

负责协调数据摄取的完整流程，包括：
- 调用 Source 获取数据
- 调用 Metadata 管理增量逻辑
- 调用 DataHub 写入数据
- 记录摄取日志
"""

from collections.abc import Callable
from typing import Literal

import polars as pl
from ditto_datahub.hub import DataHub
from ditto_datahub.models import Dataset, OnDuplicate, WriteResult
from ditto_datahub.models.ingestion import IngestionLog, IngestionStatus
from ditto_datahub.sources.base import DataSource, SourceFetchError
from ditto_foundation import logger
from ditto_foundation.util.checksum import ChecksumCompute

from ditto_port.models import IngestionResult
from ditto_port.services.ingestion.metadata import MetadataManager


class IngestionCoordinator:
    """统一摄取协调器。"""

    def __init__(
        self,
        hub: DataHub,
        source: DataSource,
        source_name: str = "tushare",
    ) -> None:
        """初始化 IngestionCoordinator。"""
        self._hub = hub
        self._source = source
        self._source_name = source_name
        self._metadata_manager = MetadataManager(hub)

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

        对于行情类数据集（stock_daily, etf_daily），非交易日返回 False。
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

        if dataset_enum in (Dataset.STOCK_DAILY, Dataset.ETF_DAILY):
            return self._hub.calendar_store.is_trading_day(trade_date)
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
        try:
            df = self._fetch_data(dataset, trade_date)
        except SourceFetchError as e:
            return self._handle_fetch_error(dataset, trade_date, e)
        except Exception as e:
            return self._handle_unknown_error(dataset, trade_date, e)

        if df.is_empty():
            return self._handle_empty_data(dataset, trade_date)

        # 将 force 映射到 on_duplicate
        on_duplicate = OnDuplicate.KEEP_LAST if force else OnDuplicate.ERROR

        try:
            write_result = self._write_data(dataset, df, trade_date, on_duplicate)
        except Exception as e:
            return self._handle_write_error(dataset, trade_date, e)

        # 检查 DQ 阻断
        if write_result.blocked:
            return self._handle_dq_blocked(dataset, trade_date, write_result)

        # 成功写入
        return self._handle_success(dataset, trade_date, df, write_result)

    def _handle_fetch_error(
        self, dataset: str, trade_date: str, error: SourceFetchError
    ) -> IngestionResult:
        """处理数据获取错误。"""
        self._hub.ingestion_log.save_log(
            IngestionLog(
                dataset=dataset,
                source=self._source_name,
                trade_date=trade_date,
                status=IngestionStatus.FAIL,
                error_code="FETCH_ERROR",
                error_message=str(error),
            )
        )
        return IngestionResult(
            dataset=dataset,
            trade_date=trade_date,
            status="failed",
            error="FETCH_ERROR",
            message=f"获取数据失败: {error}",
        )

    def _handle_unknown_error(
        self, dataset: str, trade_date: str, error: Exception
    ) -> IngestionResult:
        """处理未知错误。"""
        self._hub.ingestion_log.save_log(
            IngestionLog(
                dataset=dataset,
                source=self._source_name,
                trade_date=trade_date,
                status=IngestionStatus.FAIL,
                error_code="UNKNOWN_ERROR",
                error_message=f"{type(error).__name__}: {error}",
            )
        )
        return IngestionResult(
            dataset=dataset,
            trade_date=trade_date,
            status="failed",
            error="UNKNOWN_ERROR",
            message=f"未知错误: {error}",
        )

    def _handle_empty_data(self, dataset: str, trade_date: str) -> IngestionResult:
        """处理空数据。"""
        self._hub.ingestion_log.save_log(
            IngestionLog(
                dataset=dataset,
                source=self._source_name,
                trade_date=trade_date,
                status=IngestionStatus.FAIL,
                error_code="EMPTY_DATA",
                error_message="获取的数据为空",
            )
        )
        return IngestionResult(
            dataset=dataset,
            trade_date=trade_date,
            status="failed",
            error="EMPTY_DATA",
            message="获取的数据为空",
        )

    def _handle_write_error(
        self, dataset: str, trade_date: str, error: Exception
    ) -> IngestionResult:
        """处理写入错误。"""
        self._hub.ingestion_log.save_log(
            IngestionLog(
                dataset=dataset,
                source=self._source_name,
                trade_date=trade_date,
                status=IngestionStatus.FAIL,
                error_code="WRITE_ERROR",
                error_message=str(error),
            )
        )
        return IngestionResult(
            dataset=dataset,
            trade_date=trade_date,
            status="failed",
            error="WRITE_ERROR",
            message=f"写入数据失败: {error}",
        )

    def _handle_dq_blocked(
        self, dataset: str, trade_date: str, write_result: WriteResult
    ) -> IngestionResult:
        """处理 DQ 阻断。"""
        error_count = (
            write_result.dq_result.error_count if write_result.dq_result else 0
        )
        self._hub.ingestion_log.save_log(
            IngestionLog(
                dataset=dataset,
                source=self._source_name,
                trade_date=trade_date,
                status=IngestionStatus.FAIL,
                error_code="DQ_BLOCKED",
                error_message=f"DQ L1 check failed: {error_count} errors",
            )
        )

        return IngestionResult(
            dataset=dataset,
            trade_date=trade_date,
            status="failed",
            error="DQ_BLOCKED",
            message=(
                "DQ L1 check failed, data rejected (will retry via reprocess task)"
            ),
        )

    def _handle_success(
        self,
        dataset: str,
        trade_date: str,
        df: pl.DataFrame,
        write_result: WriteResult,
    ) -> IngestionResult:
        """处理成功写入。"""
        self._hub.ingestion_log.save_log(
            IngestionLog(
                dataset=dataset,
                source=self._source_name,
                trade_date=trade_date,
                status=IngestionStatus.SUCCESS,
                # 修复：统一使用 write_result.checksum（落盘后包含所有字段的 checksum）
                checksum=write_result.checksum,
                rows=len(df),
            )
        )

        return IngestionResult(
            dataset=dataset,
            trade_date=trade_date,
            status="success",
            row_count=len(df),
            # 修复：统一使用 write_result.checksum（落盘后包含所有字段的 checksum）
            checksum=write_result.checksum,
            message="数据摄取成功",
        )

    def ingest_range(
        self,
        dataset: str,
        start_date: str,
        end_date: str,
        force: bool = False,
    ) -> list[IngestionResult]:
        """摄取日期范围数据。"""
        trade_dates = self._hub.calendar_store.get_range(start_date, end_date)

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
            Dataset.ADJ_FACTOR: lambda: self._source.fetch_adj_factor(trade_date),
            Dataset.FUND_ADJ: lambda: self._source.fetch_fund_adj(trade_date),
        }

        if dataset_enum not in handlers:
            raise ValueError(f"不支持的数据集: {dataset}")

        return handlers[dataset_enum]()

    def _write_data(
        self,
        dataset: str,
        df: pl.DataFrame,
        trade_date: str,
        on_duplicate: OnDuplicate = OnDuplicate.ERROR,
    ) -> WriteResult:
        """根据数据集类型写入对应的 Store。"""
        year = int(trade_date[:4])

        # 转换为枚举进行比较
        try:
            dataset_enum = Dataset(dataset)
        except ValueError as e:
            raise ValueError(f"不支持写入数据集: {dataset}") from e

        if dataset_enum in (Dataset.ETF_DAILY, Dataset.STOCK_DAILY):
            # 补齐 sid/source 字段（使用 SecuritiesAccessor API）
            asset_class: Literal["stock", "etf"] = (
                "etf" if dataset_enum == Dataset.ETF_DAILY else "stock"
            )
            df = self._hub.securities.enrich_dataframe_with_sid(
                df,
                source=self._source_name,
                asset_class=asset_class,
                src_code_col="src_code",
            )
            # 使用 Accessor 层以获得文件锁和 DQ 检查保护
            return self._hub.bars.write(
                df=df,
                year=year,
                dataset=dataset,
                source=self._source_name,
                run_dq_check=True,
                on_duplicate=on_duplicate,
            )
        elif dataset_enum in (Dataset.ADJ_FACTOR, Dataset.FUND_ADJ):
            # 补齐 sid/source 字段（使用 SecuritiesAccessor API）
            adj_asset_class: Literal["stock", "etf"] = (
                "etf" if dataset_enum == Dataset.FUND_ADJ else "stock"
            )

            # 检查是否已有 sid 列（上游可能已处理）
            if "sid" not in df.columns:
                df = self._hub.securities.enrich_dataframe_with_sid(
                    df,
                    source=self._source_name,
                    asset_class=adj_asset_class,
                    src_code_col="src_code",
                )

            # 使用 AdjFactorAccessor 写入（带文件锁保护）
            return self._hub.adj_factor.write(
                dataset=dataset,
                df=df,
                year=year,
                on_duplicate=on_duplicate,
            )
        elif dataset_enum == Dataset.CALENDAR:
            records = df.to_dicts()
            self._hub.calendar_store.upsert(records)
            file_path = f"calendar_store:{trade_date}"
            # 修复：使用统一的 ChecksumCompute（MD5 算法，确定性排序）
            checksum = ChecksumCompute.from_dataframe(df, "calendar")
            return WriteResult(
                file_path=file_path,
                checksum=checksum,
                rows_written=len(df),
                rows_total=len(df),
                blocked=False,
                dq_result=None,
            )
        elif dataset_enum == Dataset.STOCK_BASIC:
            file_path, checksum = self._write_stock_basic(df, trade_date)
            return WriteResult(
                file_path=file_path,
                checksum=checksum,
                rows_written=len(df),
                rows_total=len(df),
                blocked=False,
                dq_result=None,
            )
        elif dataset_enum == Dataset.ETF_BASIC:
            file_path, checksum = self._write_etf_basic(df, trade_date)
            return WriteResult(
                file_path=file_path,
                checksum=checksum,
                rows_written=len(df),
                rows_total=len(df),
                blocked=False,
                dq_result=None,
            )
        else:
            raise ValueError(f"不支持写入数据集: {dataset}")

    def _write_stock_basic(self, df: pl.DataFrame, trade_date: str) -> tuple[str, str]:
        """写入 stock_basic 数据到 security_store。"""
        # 使用 SecuritiesAccessor 批量注册（线程安全）
        file_path, checksum = self._hub.securities.register_batch(
            df=df,
            source=self._source_name,
            asset_class="stock",
            src_code_col="src_code",
        )

        return file_path, checksum

    def _write_etf_basic(self, df: pl.DataFrame, trade_date: str) -> tuple[str, str]:
        """写入 etf_basic 数据到 security_store。"""
        # 使用 SecuritiesAccessor 批量注册（线程安全）
        file_path, checksum = self._hub.securities.register_batch(
            df=df,
            source=self._source_name,
            asset_class="etf",
            src_code_col="src_code",
        )

        return file_path, checksum
