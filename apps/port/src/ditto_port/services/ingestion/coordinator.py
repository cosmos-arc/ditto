"""
统一摄取协调器。

负责协调数据摄取的完整流程，包括：
- 调用 Source 获取数据
- 调用 Metadata 管理增量逻辑
- 调用 DataHub 写入数据
- 记录摄取日志
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar, Literal, cast

import polars as pl
from ditto_datahub.repositories.bars import WriteResult
from ditto_datahub.sources.base import DataSource, SourceFetchError
from ditto_datahub.sources.metadata import IngestionStatus
from ditto_datahub.types import OnDuplicate
from ditto_foundation import logger

from ditto_port.services.ingestion.metadata import MetadataManager
from ditto_port.services.ingestion.security_mapper import SecurityMapper

if TYPE_CHECKING:
    from ditto_datahub.hub import DataHub


@dataclass(frozen=True)
class IngestionResult:
    """数据摄取结果。"""

    dataset: str
    trade_date: str
    status: Literal["success", "skipped", "failed"]
    row_count: int | None = None
    checksum: str | None = None
    message: str = ""
    error: str | None = None


class IngestionCoordinator:
    """统一摄取协调器。"""

    _DATASET_METHODS: ClassVar[dict[str, str]] = {
        "calendar": "fetch_calendar",
        "etf_basic": "fetch_etf_basic",
        "etf_daily": "fetch_etf_daily",
        "stock_basic": "fetch_stock_basic",
        "stock_daily": "fetch_stock_daily",
        "adj_factor": "fetch_adj_factor",
        "fund_adj": "fetch_fund_adj",
    }

    def __init__(
        self,
        hub: "DataHub",
        source: DataSource,
        source_name: str = "tushare",
        security_mapper: SecurityMapper | None = None,
    ) -> None:
        """初始化 IngestionCoordinator。"""
        self._hub = hub
        self._source = source
        self._source_name = source_name
        self._metadata_manager = MetadataManager(log_store=hub.ingestion_log)
        self._security_mapper = security_mapper or SecurityMapper(
            security_store=hub.security_store, sid_allocator=hub.sid_allocator
        )

    def ingest_date(  # noqa: PLR0911
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
        if dataset not in self._DATASET_METHODS:
            raise ValueError(f"不支持的数据集: {dataset}")

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

        # 对于行情类数据集，检查是否为交易日（P0-2）
        # P0-2: 行情类数据集在非交易日静默跳过
        if dataset in (
            "stock_daily",
            "etf_daily",
        ) and not self._hub.calendar_store.is_trading_day(trade_date):
            return IngestionResult(
                dataset=dataset,
                trade_date=trade_date,
                status="skipped",
                message="非交易日, 跳过",
            )

        try:
            df = self._fetch_data(dataset, trade_date)
        except SourceFetchError as e:
            self._hub.ingestion_log.save_log(
                dataset=dataset,
                source=self._source_name,
                trade_date=trade_date,
                status=IngestionStatus.FAIL,
                error_code="FETCH_ERROR",
                error_message=str(e),
            )
            return IngestionResult(
                dataset=dataset,
                trade_date=trade_date,
                status="failed",
                error="FETCH_ERROR",
                message=f"获取数据失败: {e}",
            )
        except Exception as e:
            self._hub.ingestion_log.save_log(
                dataset=dataset,
                source=self._source_name,
                trade_date=trade_date,
                status=IngestionStatus.FAIL,
                error_code="UNKNOWN_ERROR",
                error_message=f"{type(e).__name__}: {e}",
            )
            return IngestionResult(
                dataset=dataset,
                trade_date=trade_date,
                status="failed",
                error="UNKNOWN_ERROR",
                message=f"未知错误: {e}",
            )

        if df.is_empty():
            self._hub.ingestion_log.save_log(
                dataset=dataset,
                source=self._source_name,
                trade_date=trade_date,
                status=IngestionStatus.FAIL,
                error_code="EMPTY_DATA",
                error_message="获取的数据为空",
            )
            return IngestionResult(
                dataset=dataset,
                trade_date=trade_date,
                status="failed",
                error="EMPTY_DATA",
                message="获取的数据为空",
            )

        checksum = self._metadata_manager.compute_checksum(df)

        # 将 force 映射到 on_duplicate
        on_duplicate = OnDuplicate.KEEP_LAST if force else OnDuplicate.ERROR

        try:
            write_result = self._write_data(dataset, df, trade_date, on_duplicate)
        except Exception as e:
            self._hub.ingestion_log.save_log(
                dataset=dataset,
                source=self._source_name,
                trade_date=trade_date,
                status=IngestionStatus.FAIL,
                error_code="WRITE_ERROR",
                error_message=str(e),
            )
            return IngestionResult(
                dataset=dataset,
                trade_date=trade_date,
                status="failed",
                error="WRITE_ERROR",
                message=f"写入数据失败: {e}",
            )

        # 检查 DQ 阻断
        if write_result.blocked:
            error_count = (
                write_result.dq_result.error_count if write_result.dq_result else 0
            )
            self._hub.ingestion_log.save_log(
                dataset=dataset,
                source=self._source_name,
                trade_date=trade_date,
                status=IngestionStatus.FAIL,
                error_code="DQ_BLOCKED",
                error_message=f"DQ L1 check failed: {error_count} errors",
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

        self._hub.ingestion_log.save_log(
            dataset=dataset,
            source=self._source_name,
            trade_date=trade_date,
            status=IngestionStatus.SUCCESS,
            checksum=write_result.checksum or checksum,
            rows=len(df),
        )

        return IngestionResult(
            dataset=dataset,
            trade_date=trade_date,
            status="success",
            row_count=len(df),
            checksum=write_result.checksum or checksum,
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

    def _fetch_data(self, dataset: str, trade_date: str) -> pl.DataFrame:  # noqa: PLR0911
        """根据数据集类型调用对应的 Source 方法获取数据。"""
        from ditto_datahub.sources.base import DataSourceMethods  # noqa: PLC0415

        method_name = self._DATASET_METHODS.get(dataset)
        if method_name is None:
            raise ValueError(f"不支持的数据集: {dataset}")

        source: DataSourceMethods = cast(DataSourceMethods, self._source)

        if dataset == "calendar":
            return source.fetch_calendar(trade_date, trade_date)
        if dataset == "etf_basic":
            return source.fetch_etf_basic()
        if dataset == "stock_basic":
            return source.fetch_stock_basic()
        if dataset == "etf_daily":
            return source.fetch_etf_daily(trade_date)
        if dataset == "stock_daily":
            return source.fetch_stock_daily(trade_date)
        if dataset == "adj_factor":
            return source.fetch_adj_factor(trade_date)
        if dataset == "fund_adj":
            return source.fetch_fund_adj(trade_date)

        # 不应该到达这里（前面已经验证过 dataset）
        raise ValueError(f"不支持的数据集: {dataset}")

    def _write_data(
        self,
        dataset: str,
        df: pl.DataFrame,
        trade_date: str,
        on_duplicate: OnDuplicate = OnDuplicate.ERROR,
    ) -> WriteResult:
        """根据数据集类型写入对应的 Store。"""
        year = int(trade_date[:4])

        if dataset in ("etf_daily", "stock_daily"):
            # 补齐 sid/source 字段
            asset_class: Literal["stock", "etf"] = (
                "etf" if dataset == "etf_daily" else "stock"
            )
            df = self._security_mapper.enrich_dataframe(
                df,
                src_code_col="src_code",
                asset_class=asset_class,
                source=self._source_name,
            )
            # 使用 Repository 层以获得文件锁和 DQ 检查保护
            return self._hub.bars.write(
                df=df,
                year=year,
                dataset=dataset,
                source=self._source_name,
                run_dq_check=True,
                on_duplicate=on_duplicate,
            )
        elif dataset in ("adj_factor", "fund_adj"):
            # 补齐 sid/source 字段
            adj_asset_class: Literal["stock", "etf"] = (
                "etf" if dataset == "fund_adj" else "stock"
            )

            # 检查是否已有 sid 列（上游可能已处理）
            if "sid" not in df.columns:
                df = self._security_mapper.enrich_dataframe(
                    df,
                    src_code_col="src_code",
                    asset_class=adj_asset_class,
                    source=self._source_name,
                )

            # 使用 AdjFactorRepository 写入（带文件锁保护）
            return self._hub.adj_factor.write(
                dataset=dataset,
                df=df,
                year=year,
                on_duplicate=on_duplicate,
            )
        elif dataset == "calendar":
            records = df.to_dicts()
            self._hub.calendar_store.upsert(records)
            file_path = f"calendar_store:{trade_date}"
            checksum = self._metadata_manager.compute_checksum(df)
            return WriteResult(
                file_path=file_path,
                checksum=checksum,
                rows_written=len(df),
                rows_total=len(df),
                blocked=False,
                dq_result=None,
            )
        elif dataset == "stock_basic":
            file_path, checksum = self._write_stock_basic(df, trade_date)
            return WriteResult(
                file_path=file_path,
                checksum=checksum,
                rows_written=len(df),
                rows_total=len(df),
                blocked=False,
                dq_result=None,
            )
        elif dataset == "etf_basic":
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
        # 使用 SecurityRepository 批量注册（线程安全）
        file_path, checksum = self._hub.securities.register_batch(
            df=df,
            source=self._source_name,
            asset_class="stock",
            src_code_col="src_code",
        )

        return file_path, checksum

    def _write_etf_basic(self, df: pl.DataFrame, trade_date: str) -> tuple[str, str]:
        """写入 etf_basic 数据到 security_store。"""
        # 使用 SecurityRepository 批量注册（线程安全）
        file_path, checksum = self._hub.securities.register_batch(
            df=df,
            source=self._source_name,
            asset_class="etf",
            src_code_col="src_code",
        )

        return file_path, checksum
