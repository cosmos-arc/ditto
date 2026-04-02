"""数据摄取服务 — 编排协调（应用层）."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable, Iterator
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path
from typing import Literal, Protocol, cast

import httpx
import polars as pl
from ditto_data.errors import (
    AmbiguousTickerError,
    IdentifierNotFoundError,
    NetworkError,
    SourceFetchError,
)
from ditto_data.models import (
    FX_CODE_TO_INSTRUMENT_ID,
    METAL_CODE_ALIASES,
    VIX_CODE_TO_INSTRUMENT_ID,
    Dataset,
    DateScheduleType,
    OnDuplicate,
    Source,
)
from ditto_data.models.ingestion import (
    BackfillResult,
    IngestionLog,
    IngestionResult,
    IngestionStatus,
    InstrumentIngestParams,
    ResultCounts,
    RetryResult,
)
from ditto_data.models.storage import WriteResult
from ditto_data.services import (
    FreezeService,
    IngestionCursorService,
    IngestionLogService,
)
from ditto_data.services.capital_service import CapitalService
from ditto_data.services.fundamental_service import FundamentalService
from ditto_data.services.macro_service import MacroService
from ditto_data.services.market_service import MarketService
from ditto_data.services.metadata_service import MetadataService
from ditto_data.services.source_service import SourceService
from ditto_data.sources.base import DataSource
from ditto_infra.foundation import logger, traced
from ditto_infra.foundation.util.checksum import ChecksumCompute
from pydantic import BaseModel, ConfigDict, Field

from ditto_app.process.quality import QualityService

# ---------------------------------------------------------------------------
# Section: IngestionConfig (config/config.py)
# ---------------------------------------------------------------------------


class IngestionConfig(BaseModel):
    """Data ingestion configuration (pure model)."""

    model_config = ConfigDict(extra="ignore")

    data_root: Path = Field(
        default=Path("data"),
        description="Root directory for DataHub storage.",
    )
    default_source: str = "tushare"
    auto_register_securities: bool = True


# ---------------------------------------------------------------------------
# Section: MetadataManager (metadata.py)
# ---------------------------------------------------------------------------


class MetadataManager:
    """
    元数据管理器。

    负责处理数据摄取的元数据逻辑, 包括：
    - 计算 checksum
    - 比较数据是否变化
    - 判断是否需要跳过

    Attributes:
        _ingestion_log_service: IngestionLogService 实例, 用于访问数据摄取日志等数据。

    """

    def __init__(self, ingestion_log_service: IngestionLogService | None) -> None:
        """
        初始化 MetadataManager。

        Args:
            ingestion_log_service: IngestionLogService 实例。

        """
        self._ingestion_log_service = ingestion_log_service

    def should_skip(
        self,
        dataset: str,
        trade_date: str,
        source: str = "tushare",
        force: bool = False,
    ) -> tuple[bool, str | None]:
        """
        判断是否应该跳过此次摄取。

        Args:
            dataset: 数据集名称(如 "stock_daily")。
            trade_date: 交易日期(YYYY-MM-DD)。
            source: 数据源名称(如 "tushare", "akshare")。
            force: 是否强制重新摄取。

        Returns:
            (should_skip, reason) 元组：
            - should_skip: 是否应该跳过
            - reason: 跳过原因(如果不跳过则为 None)

        """
        # 如果 force=True, 不跳过
        if force:
            logger.debug(
                "Force mode enabled, not skipping",
                event="should_skip_false",
                dataset=dataset,
                trade_date=trade_date,
                reason="force=True",
            )
            return False, None

        # 检查是否有历史记录
        if self._ingestion_log_service is None:
            # 如果没有提供 ingestion_log_service，不跳过
            logger.debug(
                "No ingestion_log_service provided, not skipping",
                event="should_skip_false",
                dataset=dataset,
                trade_date=trade_date,
                reason="no_log_service",
            )
            return False, None

        existing = self._ingestion_log_service.get_log(
            dataset=dataset,
            source=source,
            trade_date=trade_date,
        )

        # 无历史记录, 不跳过
        if existing is None:
            logger.debug(
                "No history found, not skipping",
                event="should_skip_false",
                dataset=dataset,
                trade_date=trade_date,
                reason="no_history",
            )
            return False, None

        # 历史成功, 跳过
        if existing.status.value == "SUCCESS":
            reason = (
                f"数据已存在且摄取成功({trade_date}, "
                f"checksum={existing.checksum[:8] if existing.checksum else 'N/A'}..., "
                f"rows={existing.rows})"
            )
            logger.debug(
                "Previous success found, skipping",
                event="should_skip_true",
                dataset=dataset,
                trade_date=trade_date,
                checksum=existing.checksum,
                rows=existing.rows,
            )
            return True, reason

        # 历史失败, 不跳过
        logger.debug(
            "Previous failure found, not skipping",
            event="should_skip_false",
            dataset=dataset,
            trade_date=trade_date,
            reason="previous_failure",
        )
        return False, None

    def compare_data(
        self,
        new_df: pl.DataFrame,
        existing_log: IngestionLog,
    ) -> bool:
        """
        比较新数据与已有数据是否相同。

        Args:
            new_df: 新的 Polars DataFrame。
            existing_log: 已有的摄取日志记录。

        Returns:
            如果数据相同返回 True, 否则返回 False。

        """
        # 如果现有记录没有 checksum, 认为不同
        if existing_log.checksum is None:
            logger.debug(
                "Existing log has no checksum, treating as different",
                event="compare_data_different",
                reason="no_checksum",
            )
            return False

        # 计算新数据的 checksum（使用统一的 ChecksumCompute）
        new_checksum = ChecksumCompute.from_dataframe(new_df, existing_log.dataset)

        # 比较 checksum
        if new_checksum != existing_log.checksum:
            logger.debug(
                "Checksum mismatch, data changed",
                event="compare_data_different",
                reason="checksum_mismatch",
                new_checksum=new_checksum,
                existing_checksum=existing_log.checksum,
            )
            return False

        # 比较行数
        if existing_log.rows is not None and len(new_df) != existing_log.rows:
            logger.debug(
                "Row count mismatch, data changed",
                event="compare_data_different",
                reason="row_count_mismatch",
                new_rows=len(new_df),
                existing_rows=existing_log.rows,
            )
            return False

        # 数据相同
        logger.debug(
            "Data comparison successful, data unchanged",
            event="compare_data_same",
            checksum=new_checksum,
            rows=len(new_df),
        )
        return True


# ---------------------------------------------------------------------------
# Section: IngestionDataWriter (data_writer.py)
# ---------------------------------------------------------------------------


def _enrich_with_instrument_id(
    df: pl.DataFrame,
    instrument_id_mapping: dict[str, int],
    source_ticker_col: str,
    source: str,
) -> pl.DataFrame:
    """
    为 DataFrame 添加 instrument_id/source_ticker/source 列。

    Args:
        df: 输入 DataFrame，必须包含 source_ticker_col 指定的列
        instrument_id_mapping: {source_ticker: instrument_id} 映射字典
        source_ticker_col: 源代码列名
        source: 数据源标识符

    Returns:
        添加了 instrument_id、source_ticker 和 source 列的 DataFrame

    """
    standardized_df = (
        df.rename({source_ticker_col: "source_ticker"})
        if source_ticker_col != "source_ticker"
        else df
    )

    # 处理空 DataFrame
    if len(standardized_df) == 0:
        return standardized_df.with_columns(
            pl.lit(None, dtype=pl.Int64).alias("instrument_id"),
            pl.lit(source).alias("source"),
        )

    # 将 instrument_id 映射转换为 DataFrame 并 join
    mapping_df = pl.DataFrame(
        {
            "source_ticker": list(instrument_id_mapping.keys()),
            "instrument_id": list(instrument_id_mapping.values()),
        }
    )

    return standardized_df.join(
        mapping_df, on="source_ticker", how="left"
    ).with_columns(pl.lit(source).alias("source"))


def _to_write_result(
    dataset: str,
    year: int,
    df: pl.DataFrame,
    rows_written: int,
) -> WriteResult:
    """
    将写入结果转换为 WriteResult。

    Args:
        dataset: 数据集名称
        year: 年份
        df: 写入的 DataFrame（用于计算 checksum）
        rows_written: 写入行数

    Returns:
        WriteResult 对象

    """
    checksum = ChecksumCompute.from_dataframe(df, dataset)
    return WriteResult(
        file_path=f"{dataset}/{year}",
        checksum=checksum,
        rows_written=rows_written,
        rows_total=rows_written,
        blocked=rows_written == 0,  # 如果没有行写入，则认为被阻塞
    )


class IngestionDataWriter:
    """统一数据写入器。"""

    def __init__(
        self,
        metadata_service: MetadataService,
        market_service: MarketService,
        fundamental_service: FundamentalService,
        capital_service: CapitalService,
        macro_service: MacroService,
        source_name: str,
    ) -> None:
        """
        初始化 IngestionDataWriter。

        Args:
            metadata_service: MetadataService 实例
            market_service: MarketService 实例
            fundamental_service: FundamentalService 实例
            capital_service: CapitalService 实例
            macro_service: MacroService 实例
            source_name: 数据源名称

        """
        self._metadata_service = metadata_service
        self._market_service = market_service
        self._fundamental_service = fundamental_service
        self._capital_service = capital_service
        self._macro_service = macro_service
        self._source_name = source_name

    def write_data(
        self,
        dataset: str,
        df: pl.DataFrame,
        trade_date: str,
        on_duplicate: OnDuplicate = OnDuplicate.ERROR,
    ) -> WriteResult:
        """
        根据数据集类型写入对应的 Store。

        Args:
            dataset: 数据集名称
            df: 要写入的数据
            trade_date: 交易日期
            on_duplicate: 重复数据处理策略

        Returns:
            WriteResult: 写入结果

        Raises:
            ValueError: 不支持的数据集

        """
        try:
            dataset_enum = Dataset(dataset)  # 转换为枚举进行比较
        except ValueError as e:
            raise ValueError(f"不支持写入数据集: {dataset}") from e

        # 元数据类型数据集不需要年份分区
        metadata_datasets = {
            Dataset.CALENDAR,
            Dataset.STOCK_BASIC,
            Dataset.ETF_BASIC,
            Dataset.INDEX_BASIC,
        }

        # 只有非元数据类型才需要提取年份
        year = int(trade_date[:4]) if dataset_enum not in metadata_datasets else 0

        source_ticker_col = "source_ticker"
        handlers: dict[Dataset, Callable[[], WriteResult]] = {
            Dataset.ETF_DAILY: lambda: self._write_market_bars(
                dataset,
                dataset_enum,
                df,
                year,
                on_duplicate,
                source_ticker_col,
            ),
            Dataset.STOCK_DAILY: lambda: self._write_market_bars(
                dataset,
                dataset_enum,
                df,
                year,
                on_duplicate,
                source_ticker_col,
            ),
            Dataset.STOCK_STATUS: lambda: self._write_stock_status(
                dataset,
                df,
                year,
                on_duplicate,
                source_ticker_col,
            ),
            Dataset.ADJ_FACTOR: lambda: self._write_adj_factor(
                dataset,
                df,
                year,
                on_duplicate,
                source_ticker_col,
            ),
            Dataset.FUND_ADJ: lambda: self._write_adj_factor(
                dataset,
                df,
                year,
                on_duplicate,
                source_ticker_col,
            ),
            Dataset.BALANCE_SHEET: lambda: self._write_fundamental(
                dataset,
                dataset_enum,
                df,
                year,
            ),
            Dataset.INCOME_STATEMENT: lambda: self._write_fundamental(
                dataset,
                dataset_enum,
                df,
                year,
            ),
            Dataset.CASH_FLOW: lambda: self._write_fundamental(
                dataset,
                dataset_enum,
                df,
                year,
            ),
            Dataset.DIVIDEND: lambda: self._write_fundamental(
                dataset,
                dataset_enum,
                df,
                year,
            ),
            Dataset.VALUATION_METRICS: lambda: self._write_capital(
                dataset,
                dataset_enum,
                df,
                year,
            ),
            Dataset.MARGIN_TRADING: lambda: self._write_capital(
                dataset,
                dataset_enum,
                df,
                year,
            ),
            Dataset.PLEDGE_RATIO: lambda: self._write_capital(
                dataset,
                dataset_enum,
                df,
                year,
            ),
            Dataset.MACRO_INDICATORS: lambda: self._write_macro(
                dataset,
                df,
                year,
            ),
            Dataset.CORPORATE_ACTIONS: lambda: self._write_fundamental(
                dataset,
                dataset_enum,
                df,
                year,
            ),
            Dataset.CALENDAR: lambda: self._write_calendar(df, trade_date),
            Dataset.STOCK_BASIC: lambda: self._write_basic(df, trade_date, "stock"),
            Dataset.ETF_BASIC: lambda: self._write_basic(df, trade_date, "etf"),
            Dataset.INDEX_BASIC: lambda: self._write_basic(df, trade_date, "index"),
            Dataset.INDEX_DAILY: lambda: self._write_index_bars(
                dataset, df, year, on_duplicate, source_ticker_col
            ),
            Dataset.FX_DAILY: lambda: self._write_fx_bars(
                dataset,
                df,
                year,
                on_duplicate,
            ),
            Dataset.COMMODITY_DAILY: lambda: self._write_commodity_bars(
                dataset,
                df,
                year,
                on_duplicate,
            ),
        }

        if dataset_enum not in handlers:
            raise ValueError(f"不支持写入数据集: {dataset}")

        return handlers[dataset_enum]()

    def _write_market_bars(
        self,
        dataset: str,
        dataset_enum: Dataset,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate,
        source_ticker_col: str,
    ) -> WriteResult:
        # 日行情数据不包含创建证券所需的元数据字段，
        # 使用 resolve_instrument_ids_batch 仅解析已存在的证券
        source_tickers = df[source_ticker_col].unique().to_list()
        instrument_id_mapping = self._metadata_service.resolve_instrument_ids_batch(
            identifiers=source_tickers,
            source=self._source_name,
            asof=None,
        )
        enriched_df = _enrich_with_instrument_id(
            df,
            instrument_id_mapping,
            source_ticker_col,
            self._source_name,
        )
        bars_dataset = cast(Literal["stock_daily", "etf_daily"], dataset_enum.value)
        rows_written = self._market_service.save_bars(
            dataset=bars_dataset,
            df=enriched_df,
            year=year,
            on_duplicate=on_duplicate,
        )

        return _to_write_result(
            dataset,
            year,
            enriched_df,
            rows_written,
        )

    def _write_index_bars(
        self,
        dataset: str,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate,
        source_ticker_col: str,
    ) -> WriteResult:
        """
        写入指数 K 线数据.

        Args:
            dataset: 数据集名称
            df: K 线数据
            year: 年份
            on_duplicate: 重复数据处理策略
            source_ticker_col: 源代码列名

        Returns:
            WriteResult: 写入结果

        """
        # 指数行情数据不包含创建证券所需的元数据字段，
        # 使用 resolve_instrument_ids_batch 仅解析已存在的证券
        source_tickers = df[source_ticker_col].unique().to_list()
        instrument_id_mapping = self._metadata_service.resolve_instrument_ids_batch(
            identifiers=source_tickers,
            source=self._source_name,
            asof=None,
        )

        # 添加 instrument_id 列
        enriched_df = _enrich_with_instrument_id(
            df, instrument_id_mapping, source_ticker_col, self._source_name
        )

        # 写入到 MarketService
        rows_written = self._market_service.save_bars(
            dataset="index_daily",
            df=enriched_df,
            year=year,
            on_duplicate=on_duplicate,
        )

        return _to_write_result(dataset, year, enriched_df, rows_written)

    def _write_fx_bars(
        self,
        dataset: str,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate,
    ) -> WriteResult:
        """Write FX daily bars data."""
        rows_written = self._market_service.save_bars(
            dataset="fx_daily",
            df=df,
            year=year,
            on_duplicate=on_duplicate,
        )
        return _to_write_result(dataset, year, df, rows_written)

    def _write_commodity_bars(
        self,
        dataset: str,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate,
    ) -> WriteResult:
        """Write Commodity daily bars data."""
        rows_written = self._market_service.save_bars(
            dataset="commodity_daily",
            df=df,
            year=year,
            on_duplicate=on_duplicate,
        )
        return _to_write_result(dataset, year, df, rows_written)

    def _write_stock_status(
        self,
        dataset: str,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate,
        source_ticker_col: str,
    ) -> WriteResult:
        # 股票状态数据不包含创建证券所需的元数据字段，
        # 使用 resolve_instrument_ids_batch 仅解析已存在的证券
        source_tickers = df[source_ticker_col].unique().to_list()
        instrument_id_mapping = self._metadata_service.resolve_instrument_ids_batch(
            identifiers=source_tickers,
            source=self._source_name,
            asof=None,
        )
        enriched_df = _enrich_with_instrument_id(
            df,
            instrument_id_mapping,
            source_ticker_col,
            self._source_name,
        )
        rows_written = self._market_service.save_stock_status(
            df=enriched_df,
            year=year,
        )
        return _to_write_result(
            dataset,
            year,
            enriched_df,
            rows_written,
        )

    def _write_adj_factor(
        self,
        dataset: str,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate,
        source_ticker_col: str,
    ) -> WriteResult:
        enriched_df = df
        if "instrument_id" not in df.columns:
            # 复权因子数据不包含创建证券所需的元数据字段，
            # 使用 resolve_instrument_ids_batch 仅解析已存在的证券
            source_tickers = df[source_ticker_col].unique().to_list()
            instrument_id_mapping = self._metadata_service.resolve_instrument_ids_batch(
                identifiers=source_tickers,
                source=self._source_name,
                asof=None,
            )
            enriched_df = _enrich_with_instrument_id(
                df,
                instrument_id_mapping,
                source_ticker_col,
                self._source_name,
            )

        rows_written = self._market_service.save_adj_factor(
            df=enriched_df,
            year=year,
            on_duplicate=on_duplicate,
        )
        return _to_write_result(
            dataset,
            year,
            enriched_df,
            rows_written,
        )

    def _write_fundamental(
        self,
        dataset: str,
        dataset_enum: Dataset,
        df: pl.DataFrame,
        year: int,
    ) -> WriteResult:
        # 解析 instrument_id（基本面数据需要有效的 instrument_id 作为外键）
        source_ticker_col = "source_ticker"
        if "instrument_id" not in df.columns:
            source_tickers = df[source_ticker_col].unique().to_list()
            instrument_id_mapping = self._metadata_service.resolve_instrument_ids_batch(
                identifiers=source_tickers,
                source=self._source_name,
                asof=None,
            )
            enriched_df = _enrich_with_instrument_id(
                df,
                instrument_id_mapping,
                source_ticker_col,
                self._source_name,
            )
        else:
            enriched_df = df

        # 过滤掉 instrument_id 为 null 的记录（无法写入有外键约束的表）
        total_count = len(enriched_df)
        enriched_df = enriched_df.filter(pl.col("instrument_id").is_not_null())
        filtered_count = total_count - len(enriched_df)
        if filtered_count > 0:
            logger.warning(
                f"Filtered {filtered_count} records with null instrument_id",
                dataset=dataset,
            )

        if len(enriched_df) == 0:
            return _to_write_result(dataset, year, enriched_df, 0)

        # Map dataset enum to the appropriate save method
        save_methods = {
            Dataset.BALANCE_SHEET: self._fundamental_service.save_balance_sheet,
            Dataset.INCOME_STATEMENT: self._fundamental_service.save_income_statement,
            Dataset.CASH_FLOW: self._fundamental_service.save_cash_flow,
            Dataset.DIVIDEND: self._fundamental_service.save_dividend,
            Dataset.CORPORATE_ACTIONS: self._fundamental_service.save_corporate_actions,
        }
        save_method = save_methods[dataset_enum]
        records_written = save_method(enriched_df)
        return _to_write_result(
            dataset,
            year,
            enriched_df,
            records_written,
        )

    def _write_capital(
        self,
        dataset: str,
        dataset_enum: Dataset,
        df: pl.DataFrame,
        year: int,
    ) -> WriteResult:
        # 解析 instrument_id（资本面数据需要有效的 instrument_id 作为外键）
        source_ticker_col = "source_ticker"
        if "instrument_id" not in df.columns:
            source_tickers = df[source_ticker_col].unique().to_list()
            instrument_id_mapping = self._metadata_service.resolve_instrument_ids_batch(
                identifiers=source_tickers,
                source=self._source_name,
                asof=None,
            )
            enriched_df = _enrich_with_instrument_id(
                df,
                instrument_id_mapping,
                source_ticker_col,
                self._source_name,
            )
        else:
            enriched_df = df

        # 过滤掉 instrument_id 为 null 的记录（无法写入有外键约束的表）
        total_count = len(enriched_df)
        enriched_df = enriched_df.filter(pl.col("instrument_id").is_not_null())
        filtered_count = total_count - len(enriched_df)
        if filtered_count > 0:
            logger.warning(
                f"Filtered {filtered_count} records with null instrument_id",
                dataset=dataset,
            )

        if len(enriched_df) == 0:
            return _to_write_result(dataset, year, enriched_df, 0)

        capital_dataset = cast(
            Literal[
                "valuation_metrics",
                "margin_trading",
                "pledge_ratio",
            ],
            dataset_enum.value,
        )
        # 使用特定的 save_* 方法替代已删除的 write() 方法
        if capital_dataset == "valuation_metrics":
            records_written = self._capital_service.save_valuation_metrics(enriched_df)
        elif capital_dataset == "margin_trading":
            records_written = self._capital_service.save_margin_trading(enriched_df)
        elif capital_dataset == "pledge_ratio":
            records_written = self._capital_service.save_pledge_ratio(enriched_df)
        else:
            valid = "valuation_metrics, margin_trading, pledge_ratio"
            raise ValueError(
                f"Unknown capital_dataset: {capital_dataset}. Expected: {valid}"
            )
        return _to_write_result(
            dataset,
            year,
            enriched_df,
            records_written,
        )

    def _write_macro(
        self,
        dataset: str,
        df: pl.DataFrame,
        year: int,
    ) -> WriteResult:
        write_result = self._macro_service.save_indicators(df)
        return _to_write_result(
            dataset,
            year,
            df,
            write_result.records_written,
        )

    def _write_calendar(self, df: pl.DataFrame, trade_date: str) -> WriteResult:
        records = df.to_dicts()
        self._metadata_service.save_calendar(records=records)
        file_path = f"calendar_store:{trade_date}"
        checksum = ChecksumCompute.from_dataframe(df, "calendar")
        return WriteResult(
            file_path=file_path,
            checksum=checksum,
            rows_written=len(df),
            rows_total=len(df),
            blocked=False,
        )

    def _write_basic(
        self,
        df: pl.DataFrame,
        trade_date: str,
        asset_class: Literal["stock", "etf", "index"],
    ) -> WriteResult:
        if asset_class == "stock":
            file_path, checksum = self.write_stock_basic(df, trade_date)
        elif asset_class == "etf":
            file_path, checksum = self.write_etf_basic(df, trade_date)
        else:  # index
            file_path, checksum = self.write_index_basic(df, trade_date)
        return WriteResult(
            file_path=file_path,
            checksum=checksum,
            rows_written=len(df),
            rows_total=len(df),
            blocked=False,
        )

    def write_stock_basic(self, df: pl.DataFrame, trade_date: str) -> tuple[str, str]:
        """
        写入 stock_basic 数据到 instrument_store。

        Args:
            df: 股票基础信息数据
            trade_date: 交易日期

        Returns:
            tuple[str, str]: (file_path, checksum)

        """
        # 使用 MetadataService 批量注册（线程安全）
        file_path, checksum = self._metadata_service.register_instruments_batch(
            df=df,
            source=self._source_name,
            asset_class="stock",
            source_ticker_col="source_ticker",
        )

        return file_path, checksum

    def write_etf_basic(self, df: pl.DataFrame, trade_date: str) -> tuple[str, str]:
        """
        写入 etf_basic 数据到 instrument_store。

        Args:
            df: ETF 基础信息数据
            trade_date: 交易日期

        Returns:
            tuple[str, str]: (file_path, checksum)

        """
        # 使用 MetadataService 批量注册（线程安全）
        file_path, checksum = self._metadata_service.register_instruments_batch(
            df=df,
            source=self._source_name,
            asset_class="etf",
            source_ticker_col="source_ticker",
        )

        return file_path, checksum

    def write_index_basic(self, df: pl.DataFrame, trade_date: str) -> tuple[str, str]:
        """
        写入 index_basic 数据到 instrument_store。

        Args:
            df: 指数基础信息数据
            trade_date: 交易日期

        Returns:
            tuple[str, str]: (file_path, checksum)

        """
        # 使用 MetadataService 批量注册（线程安全）
        file_path, checksum = self._metadata_service.register_instruments_batch(
            df=df,
            source=self._source_name,
            asset_class="index",
            source_ticker_col="source_ticker",
        )

        return file_path, checksum


# ---------------------------------------------------------------------------
# Section: Index Configuration (index_config.py)
# ---------------------------------------------------------------------------


# 市场基准指数（Tushare source_ticker 格式）
MARKET_INDEX_CODES: list[str] = [
    "000001.SH",  # 上证指数
    "399001.SZ",  # 深证成指
    "000300.SH",  # 沪深300
    "000852.SH",  # 中证1000
    "000016.SH",  # 上证50
    "399006.SZ",  # 创业板指
    "000688.SH",  # 科创50
    "399673.SZ",  # 创业板50
]

# 风格指数（Tushare source_ticker 格式）
STYLE_INDEX_CODES: list[str] = [
    "399373.SZ",  # 大盘价值
    "399374.SZ",  # 大盘成长
    "399375.SZ",  # 中盘价值
    "399376.SZ",  # 中盘成长
    "399377.SZ",  # 小盘价值
    "399378.SZ",  # 小盘成长
    "000992.SH",  # 全指价值
    "000993.SH",  # 全指成长
    "000991.SH",  # 全指红利
]


class SWIndustryProvider(Protocol):
    """申万行业数据提供者协议."""

    def fetch_sw_industry(self, level: int = 1) -> pl.DataFrame:
        """获取申万行业分类."""
        ...


def get_sw_index_codes(
    source: SWIndustryProvider,
    level: Literal[1, 2] = 1,
) -> list[str]:
    """
    从 Tushare API 动态获取申万行业指数代码列表.

    Args:
        source: 数据源，需实现 fetch_sw_industry 方法.
        level: 行业级别 (1=一级行业, 2=二级行业).

    Returns:
        SW 行业指数代码列表（Tushare source_ticker 格式）.

    Example:
        >>> from ditto_data.sources import TushareSource
        >>> source = TushareSource(settings, token)
        >>> codes = get_sw_index_codes(source, level=1)
        >>> print(codes[:3])
        ['801010.SI', '801020.SI', '801030.SI']

    """
    df = source.fetch_sw_industry(level=level)
    if df.is_empty():
        return []
    return df["source_ticker"].unique().sort().to_list()


def get_default_index_codes(
    include_style: bool = True,
) -> list[str]:
    """
    获取默认指数代码列表（仅固定配置的指数）.

    注意：此函数仅返回硬编码的市场指数和风格指数。
    如需包含 SW 行业指数，请使用 get_sw_index_codes() 动态获取。

    Args:
        include_style: 是否包含风格指数（默认 True）.

    Returns:
        指数代码列表（Tushare source_ticker 格式）。

    """
    codes = list(MARKET_INDEX_CODES)
    if include_style:
        codes.extend(STYLE_INDEX_CODES)
    return codes


def get_all_index_codes(
    source: SWIndustryProvider,
    include_style: bool = True,
    include_sw_levels: list[Literal[1, 2]] | None = None,
) -> list[str]:
    """
    获取所有指数代码列表（包含动态获取的 SW 行业指数）.

    Args:
        source: 数据源，用于动态获取 SW 行业指数代码.
        include_style: 是否包含风格指数（默认 True）.
        include_sw_levels: 要包含的 SW 行业级别列表，默认 [1]（仅一级行业）.

    Returns:
        指数代码列表（Tushare source_ticker 格式）。

    Example:
        >>> from ditto_data.sources import TushareSource
        >>> source = TushareSource(settings, token)
        >>> # 获取市场指数 + 风格指数 + SW L1/L2 行业指数
        >>> codes = get_all_index_codes(
        ...     source,
        ...     include_style=True,
        ...     include_sw_levels=[1, 2],
        ... )

    """
    codes = get_default_index_codes(include_style=include_style)

    if include_sw_levels:
        for level in include_sw_levels:
            sw_codes = get_sw_index_codes(source, level=level)
            codes.extend(sw_codes)

    return codes


# ---------------------------------------------------------------------------
# Section: ListDateInferenceService (list_date_inference.py)
# ---------------------------------------------------------------------------

# list_date 推断的最早起始日期
EARLIEST_LIST_DATE_INFERENCE = date(2010, 1, 1)

# API 返回限制（每种类型的最大记录数）
API_LIMITS: dict[str, int] = {
    "stock": 6000,
    "etf": 2000,
    "index": 8000,
    "sw_index": 4000,  # 申万指数
}

# 估算的年均交易日数
TRADING_DAYS_PER_YEAR = 250


class ListDateInferenceService:
    """
    list_date 推断服务。

    作为 basic 数据摄取后的独立补偿流程，
    针对 list_date 为 NULL 的证券，从 2010 年起查询历史行情数据推断上市日期。
    """

    def __init__(
        self,
        metadata_service: MetadataService,
        source: DataSource,
        source_name: str = "tushare",
    ) -> None:
        """
        初始化 ListDateInferenceService。

        Args:
            metadata_service: MetadataService 实例
            source: 数据源实例
            source_name: 数据源名称

        """
        self._metadata_service = metadata_service
        self._source = source
        self._source_name = source_name

    @traced("list_date_inference.infer_for_asset_class")
    def infer_for_asset_class(
        self,
        asset_class: Literal["stock", "etf", "index"],
    ) -> int:
        """
        对指定资产类型的所有 list_date 为 NULL 的证券推断上市日期。

        Args:
            asset_class: 资产类型

        Returns:
            成功推断的证券数量

        """
        logger.info(
            "Starting list_date inference",
            event="list_date_inference_start",
            asset_class=asset_class,
        )

        # 查找 list_date 为 NULL 的证券
        instruments = self._metadata_service.find_instruments_without_list_date(
            asset_class=asset_class
        )

        if instruments.is_empty():
            logger.info(
                "No instruments without list_date found",
                event="list_date_inference_empty",
                asset_class=asset_class,
            )
            return 0

        # 获取 source_ticker 和 instrument_id 的映射
        source_tickers = instruments["source_ticker"].to_list()
        instrument_ids = instruments["instrument_id"].to_list()

        logger.info(
            f"Found {len(source_tickers)} instruments without list_date",
            event="list_date_inference_found",
            asset_class=asset_class,
            count=len(source_tickers),
        )

        success_count = 0

        for source_ticker, instrument_id in zip(
            source_tickers, instrument_ids, strict=True
        ):
            try:
                inferred_date = self._infer_list_date_for_instrument(
                    source_ticker=source_ticker,
                    asset_class=asset_class,
                )
                if inferred_date is not None:
                    self._metadata_service.update_list_date(
                        instrument_id, inferred_date
                    )
                    success_count += 1
                    logger.debug(
                        "Updated list_date",
                        event="list_date_updated",
                        instrument_id=instrument_id,
                        source_ticker=source_ticker,
                        list_date=str(inferred_date),
                    )
            except Exception as e:
                logger.warning(
                    f"Failed to infer list_date for {source_ticker}",
                    event="list_date_inference_failed",
                    source_ticker=source_ticker,
                    error=str(e),
                )

        logger.info(
            "Completed list_date inference",
            event="list_date_inference_complete",
            asset_class=asset_class,
            total=len(source_tickers),
            success=success_count,
        )

        return success_count

    def _infer_list_date_for_instrument(
        self,
        source_ticker: str,
        asset_class: str,
    ) -> date | None:
        """
        为单个证券推断 list_date。

        从 2010 年起分批查询历史数据，找到最早有数据的日期。

        Args:
            source_ticker: 源代码
            asset_class: 资产类型

        Returns:
            推断的上市日期，如果无法推断则返回 None

        """
        api_limit = API_LIMITS.get(asset_class, 6000)
        years_per_batch = api_limit // TRADING_DAYS_PER_YEAR

        # 从当前日期往回查询，直到找到数据或到达 2010 年
        end_date = date.today()
        earliest_date: date | None = None

        while end_date >= EARLIEST_LIST_DATE_INFERENCE:
            # 计算批次起始日期
            start_date = max(
                EARLIEST_LIST_DATE_INFERENCE,
                end_date - timedelta(days=years_per_batch * 365),
            )

            try:
                df = self._fetch_daily_data(
                    source_ticker=source_ticker,
                    asset_class=asset_class,
                    start_date=start_date,
                    end_date=end_date,
                )

                if not df.is_empty() and "trade_date" in df.columns:
                    # 先过滤出 >= 2010 年的数据，再找最早的日期
                    filtered_df = df.filter(
                        pl.col("trade_date") >= EARLIEST_LIST_DATE_INFERENCE
                    )

                    if not filtered_df.is_empty():
                        batch_earliest = filtered_df.select(
                            pl.col("trade_date").min()
                        ).item()

                        if batch_earliest is not None:
                            # 转换为 date 类型
                            if isinstance(batch_earliest, str):
                                batch_earliest = date.fromisoformat(batch_earliest)
                            elif hasattr(batch_earliest, "date"):
                                batch_earliest = batch_earliest.date()

                            if earliest_date is None or batch_earliest < earliest_date:
                                earliest_date = batch_earliest

                # 如果数据量小于限制，说明已经到达最早的数据
                if len(df) < api_limit:
                    break

            except Exception as e:
                msg = (
                    f"No data found for {source_ticker} "
                    f"in range {start_date} to {end_date}"
                )
                logger.debug(
                    msg,
                    event="list_date_inference_no_data",
                    source_ticker=source_ticker,
                    start_date=str(start_date),
                    end_date=str(end_date),
                    error=str(e),
                )

            # 移动到下一个批次
            end_date = start_date - timedelta(days=1)

        return earliest_date

    def _fetch_daily_data(
        self,
        source_ticker: str,
        asset_class: str,
        start_date: date,
        end_date: date,
    ) -> pl.DataFrame:
        """
        获取日线数据。

        Args:
            source_ticker: 源代码
            asset_class: 资产类型
            start_date: 起始日期
            end_date: 结束日期

        Returns:
            日线数据 DataFrame

        """
        start_str = start_date.isoformat()
        end_str = end_date.isoformat()

        if asset_class == "stock":
            return self._source.fetch_stock_daily(
                source_ticker=source_ticker,
                start_date=start_str,
                end_date=end_str,
            )
        elif asset_class == "etf":
            return self._source.fetch_etf_daily(
                source_ticker=source_ticker,
                start_date=start_str,
                end_date=end_str,
            )
        elif asset_class == "index":
            return self._source.fetch_index_daily(
                source_ticker=source_ticker,
                start_date=start_str,
                end_date=end_str,
            )
        else:
            raise ValueError(f"Unsupported asset_class: {asset_class}")


# ---------------------------------------------------------------------------
# Section: count_results (result_utils.py)
# ---------------------------------------------------------------------------


def count_results(
    results: list[IngestionResult] | dict[str, dict[str, object]],
) -> ResultCounts:
    """
    统计摄取结果。

    Args:
        results: 摄取结果列表或字典

    Returns:
        ResultCounts: 包含 success/failed/skipped 计数

    Examples:
        >>> results = [
        ...     IngestionResult(
        ...         dataset="stock_daily",
        ...         trade_date="2024-01-01",
        ...         status="success",
        ...     ),
        ...     IngestionResult(
        ...         dataset="stock_daily",
        ...         trade_date="2024-01-02",
        ...         status="failed",
        ...         error="FETCH_ERROR",
        ...     ),
        ... ]
        >>> counts = count_results(results)
        >>> counts.success, counts.failed, counts.skipped
        (1, 1, 0)

        >>> # 字典类型结果
        >>> dict_results = {
        ...     "task1": {"status": "success"},
        ...     "task2": {"status": "failed"},
        ... }
        >>> counts = count_results(dict_results)
        >>> counts.success, counts.failed, counts.skipped
        (1, 1, 0)

    """
    if isinstance(results, list):
        # 处理 IngestionResult 列表
        statuses = [r.status for r in results if hasattr(r, "status")]
    else:
        # 处理字典类型结果
        statuses = [v.get("status") for v in results.values() if "status" in v]

    # 使用 Counter 统计
    counter = Counter(statuses)

    return ResultCounts(
        success=counter.get("success", 0),
        failed=counter.get("failed", 0),
        skipped=counter.get("skipped", 0),
    )


# ---------------------------------------------------------------------------
# Section: IngestionResultHandler (result_handler.py)
# ---------------------------------------------------------------------------


class IngestionResultHandler:
    """
    摄取结果处理器。

    负责将摄取操作的各种结果转换为 IngestionResult 并记录日志。
    """

    def __init__(
        self, ingestion_log_service: IngestionLogService | None, source_name: str
    ) -> None:
        """
        初始化 IngestionResultHandler。

        Args:
            ingestion_log_service: IngestionLogService 实例，用于访问 ingestion_log
            source_name: 数据源名称

        """
        self._ingestion_log_service = ingestion_log_service
        self._source_name = source_name

    def _save_log(self, log: IngestionLog) -> None:
        """保存日志（如果提供了 ingestion_log_service）。"""
        if self._ingestion_log_service:
            self._ingestion_log_service.save_log(log)

    def handle_fetch_error(
        self, dataset: str, trade_date: str, error: SourceFetchError
    ) -> IngestionResult:
        """
        处理数据获取错误。

        Args:
            dataset: 数据集名称
            trade_date: 交易日期
            error: 获取错误

        Returns:
            IngestionResult: 失败结果

        """
        self._save_log(
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

    def handle_unknown_error(
        self, dataset: str, trade_date: str, error: Exception
    ) -> IngestionResult:
        """
        处理未知错误。

        Args:
            dataset: 数据集名称
            trade_date: 交易日期
            error: 异常对象

        Returns:
            IngestionResult: 失败结果

        """
        self._save_log(
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

    def handle_empty_data(self, dataset: str, trade_date: str) -> IngestionResult:
        """
        处理空数据。

        Args:
            dataset: 数据集名称
            trade_date: 交易日期

        Returns:
            IngestionResult: 失败结果

        """
        self._save_log(
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

    def handle_write_error(
        self, dataset: str, trade_date: str, error: Exception
    ) -> IngestionResult:
        """
        处理写入错误。

        Args:
            dataset: 数据集名称
            trade_date: 交易日期
            error: 异常对象

        Returns:
            IngestionResult: 失败结果

        """
        self._save_log(
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

    def handle_dq_blocked(
        self, dataset: str, trade_date: str, write_result: WriteResult
    ) -> IngestionResult:
        """
        处理 DQ 阻断。

        Args:
            dataset: 数据集名称
            trade_date: 交易日期
            write_result: 写入结果

        Returns:
            IngestionResult: 失败结果

        """
        # DQ 检查已移到 Port 层，这里使用默认错误计数
        error_count = 1
        self._save_log(
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

    def handle_success(
        self,
        dataset: str,
        trade_date: str,
        df: pl.DataFrame,
        write_result: WriteResult,
    ) -> IngestionResult:
        """
        处理成功写入。

        Args:
            dataset: 数据集名称
            trade_date: 交易日期
            df: 数据框
            write_result: 写入结果

        Returns:
            IngestionResult: 成功结果

        """
        self._save_log(
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


# ---------------------------------------------------------------------------
# Section: IngestionCoordinator (coordinator.py)
# ---------------------------------------------------------------------------

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
        freeze_service: FreezeService | None = None,
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
        self._freeze_service = freeze_service
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

    def _fetch_and_ingest(  # noqa: PLR0911
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
        self._run_post_ingest_hooks(dataset, trade_date)

        # 成功写入
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
            except Exception as e:
                logger.warning(
                    "cursor_update_failed",
                    dataset=dataset,
                    trade_date=trade_date,
                    error=str(e),
                )

        # 创建冻结点（轻量级版本追踪）
        if self._freeze_service is not None:
            try:
                self._freeze_service.create_freeze(
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


# ---------------------------------------------------------------------------
# Section: BackfillManager (backfill.py)
# ---------------------------------------------------------------------------


class BackfillManager:
    """全量回补管理器。"""

    def __init__(
        self,
        coordinator: IngestionCoordinator,
        metadata_service: MetadataService,
        ingestion_log_service: IngestionLogService,
    ) -> None:
        """
        初始化 BackfillManager。

        Args:
            coordinator: IngestionCoordinator 实例。
            metadata_service: MetadataService 实例。
            ingestion_log_service: IngestionLogService 实例。

        """
        self._coordinator = coordinator
        self._metadata_service = metadata_service
        self._ingestion_log_service = ingestion_log_service

    def backfill_range(
        self,
        dataset: str,
        start_date: str,
        end_date: str,
        parallel: int = 1,
    ) -> BackfillResult:
        """
        全量回补指定日期范围。

        Args:
            dataset: 数据集名称。
            start_date: 开始日期 (YYYY-MM-DD)。
            end_date: 结束日期 (YYYY-MM-DD)。
            parallel: 并行度，默认为 1（串行）。

        Returns:
            BackfillResult: 回补结果。

        """
        logger.info(
            "开始回补数据",
            event="backfill_range_start",
            dataset=dataset,
            start_date=start_date,
            end_date=end_date,
            parallel=parallel,
        )

        # 获取日期范围内的所有交易日
        trade_dates = self._metadata_service.list_trading_days(start_date, end_date)

        if not trade_dates:
            return BackfillResult(
                dataset=dataset,
                total_dates=0,
                success_count=0,
                skipped_count=0,
                failed_count=0,
                results=(),
            )

        results: list[IngestionResult] = []

        if parallel > 1:
            # 按年份分组，并发度上限为 min(parallel, 年份数)
            # 注意：同一年内的日期仍会并行执行，依赖 FileLockManager 避免冲突
            dates_by_year: defaultdict[str, list[str]] = defaultdict(list)
            for trade_date in trade_dates:
                year = trade_date[:4]  # 提取年份
                dates_by_year[year].append(trade_date)

            with ThreadPoolExecutor(
                max_workers=min(parallel, len(dates_by_year))
            ) as executor:
                futures: dict[Future[IngestionResult], str] = {}
                for _year, year_dates in dates_by_year.items():
                    for date in year_dates:
                        future = executor.submit(
                            self._coordinator.ingest_date,
                            dataset,
                            date,
                        )
                        futures[future] = date

                for future in as_completed(futures):
                    result = future.result()
                    results.append(result)
        else:
            # 串行执行
            for trade_date in trade_dates:
                result = self._coordinator.ingest_date(dataset, trade_date)
                results.append(result)

        # 统计结果
        counts = count_results(results)

        backfill_result = BackfillResult(
            dataset=dataset,
            total_dates=len(trade_dates),
            success_count=counts.success,
            skipped_count=counts.skipped,
            failed_count=counts.failed,
            results=tuple(results),
        )

        logger.info(
            "回补完成",
            event="backfill_range_complete",
            dataset=dataset,
            total_dates=backfill_result.total_dates,
            success_count=backfill_result.success_count,
            skipped_count=backfill_result.skipped_count,
            failed_count=backfill_result.failed_count,
        )

        return backfill_result

    def backfill_missing(
        self,
        dataset: str,
        source: str = "tushare",
        parallel: int = 1,
    ) -> BackfillResult:
        """
        回补缺失的交易日。

        Args:
            dataset: 数据集名称。
            source: 数据源标识符（默认: "tushare"）。
            parallel: 并行度，默认为 1（串行）。

        Returns:
            BackfillResult: 回补结果。

        """
        logger.info(
            "开始回补缺失数据",
            event="backfill_missing_start",
            dataset=dataset,
            parallel=parallel,
        )

        # 获取日历的完整日期范围
        first_date = self._metadata_service.get_first_trading_day()
        last_date = self._metadata_service.get_last_trading_day()

        if not first_date or not last_date:
            return BackfillResult(
                dataset=dataset,
                total_dates=0,
                success_count=0,
                skipped_count=0,
                failed_count=0,
                results=(),
            )

        # 获取所有交易日
        all_trade_dates = self._metadata_service.list_trading_days(
            first_date, last_date
        )

        if not all_trade_dates:
            return BackfillResult(
                dataset=dataset,
                total_dates=0,
                success_count=0,
                skipped_count=0,
                failed_count=0,
                results=(),
            )

        # 获取已摄取的日期
        ingested_dates = self._ingestion_log_service.list_ingested_dates(
            dataset, source
        )

        # 计算缺失的日期
        missing_dates = set(all_trade_dates) - set(ingested_dates)

        if not missing_dates:
            return BackfillResult(
                dataset=dataset,
                total_dates=0,
                success_count=0,
                skipped_count=0,
                failed_count=0,
                results=(),
            )

        # 按日期排序
        sorted_missing_dates = sorted(missing_dates)

        # 回补缺失的日期
        results: list[IngestionResult] = []

        if parallel > 1:
            # 并行执行
            with ThreadPoolExecutor(max_workers=parallel) as executor:
                futures = {
                    executor.submit(
                        self._coordinator.ingest_date, dataset, trade_date
                    ): trade_date
                    for trade_date in sorted_missing_dates
                }

                for future in as_completed(futures):
                    result = future.result()
                    results.append(result)
        else:
            # 串行执行
            for trade_date in sorted_missing_dates:
                result = self._coordinator.ingest_date(dataset, trade_date)
                results.append(result)

        # 统计结果
        counts = count_results(results)

        backfill_result = BackfillResult(
            dataset=dataset,
            total_dates=len(sorted_missing_dates),
            success_count=counts.success,
            skipped_count=counts.skipped,
            failed_count=counts.failed,
            results=tuple(results),
        )

        logger.info(
            "缺失数据回补完成",
            event="backfill_missing_complete",
            dataset=dataset,
            total_dates=backfill_result.total_dates,
            success_count=backfill_result.success_count,
            skipped_count=backfill_result.skipped_count,
            failed_count=backfill_result.failed_count,
        )

        return backfill_result


# ---------------------------------------------------------------------------
# Section: RetryManager (retry.py)
# ---------------------------------------------------------------------------


class RetryManager:
    """重试管理器。"""

    def __init__(
        self,
        coordinator: IngestionCoordinator,
        ingestion_log_service: IngestionLogService,
        source: str = "tushare",
    ) -> None:
        """
        初始化 RetryManager。

        Args:
            coordinator: 摄取协调器
            ingestion_log_service: 摄取日志服务
            source: 数据源标识符

        """
        self._coordinator = coordinator
        self._ingestion_log_service = ingestion_log_service
        self._source = source

    def get_failed_dates(
        self,
        dataset: str,
        max_attempts: int = 3,
        limit: int = 10,
    ) -> list[str]:
        """
        获取失败的交易日期列表。

        Args:
            dataset: 数据集名称（例如 "stock_daily"）
            max_attempts: 最大尝试次数筛选条件
            limit: 返回的最大日期数量

        Returns:
            失败的交易日期列表（YYYY-MM-DD）

        """
        failed_dates = self._ingestion_log_service.list_failed_dates(
            dataset=dataset,
            source=self._source,
            limit=limit,
            max_attempts=max_attempts,
        )

        logger.debug(
            "获取失败日期",
            event="get_failed_dates",
            dataset=dataset,
            count=len(failed_dates),
            max_attempts=max_attempts,
        )

        return failed_dates

    def retry_failed(
        self,
        dataset: str,
        max_attempts: int = 3,
        limit: int = 10,
    ) -> RetryResult:
        """
        重试失败的任务。

        Args:
            dataset: 数据集名称（例如 "stock_daily"）
            max_attempts: 最大尝试次数筛选条件
            limit: 重试的最大任务数量

        Returns:
            重试结果

        """
        failed_dates = self.get_failed_dates(
            dataset=dataset,
            max_attempts=max_attempts,
            limit=limit,
        )

        total_failed = len(failed_dates)
        results: list[IngestionResult] = []

        logger.info(
            "开始重试失败任务",
            event="retry_failed_start",
            dataset=dataset,
            total_failed=total_failed,
            max_attempts=max_attempts,
        )

        for trade_date in failed_dates:
            result = self._coordinator.ingest_date(
                dataset=dataset,
                trade_date=trade_date,
                force=True,
            )
            results.append(result)

        # 统计结果
        counts = count_results(results)

        retry_result = RetryResult(
            dataset=dataset,
            total_failed=total_failed,
            retried_count=len(results),
            success_count=counts.success,
            still_failed_count=counts.failed,
            results=tuple(results),
        )

        logger.info(
            "重试失败任务完成",
            event="retry_failed_complete",
            dataset=dataset,
            total_failed=total_failed,
            retried_count=len(results),
            success_count=counts.success,
            still_failed_count=counts.failed,
        )

        return retry_result


# ---------------------------------------------------------------------------
# Section: Factory (factory.py)
# ---------------------------------------------------------------------------


@contextmanager
def create_coordinator(  # noqa: PLR0913
    metadata_service: MetadataService,
    market_service: MarketService,
    fundamental_service: FundamentalService,
    capital_service: CapitalService,
    macro_service: MacroService,
    source_service: SourceService,
    ingestion_log_service: IngestionLogService,
    source_name: str | Source,
    ingestion_cursor_service: IngestionCursorService | None = None,
    quality_service: QualityService | None = None,
    freeze_service: FreezeService | None = None,
) -> Iterator[IngestionCoordinator]:
    """
    创建 IngestionCoordinator 实例.

    Args:
        metadata_service: MetadataService 实例
        market_service: MarketService 实例
        fundamental_service: FundamentalService 实例
        capital_service: CapitalService 实例
        macro_service: MacroService 实例
        source_service: SourceService 实例
        ingestion_log_service: IngestionLogService 实例
        ingestion_cursor_service: IngestionCursorService 实例（可选）
        quality_service: QualityService 实例（可选）
        freeze_service: FreezeService 实例（可选）
        source_name: 数据源名称

    Yields:
        IngestionCoordinator: 协调器实例

    """
    # 支持 Source 枚举和字符串
    if isinstance(source_name, Source):
        source_key = source_name
    else:
        try:
            source_key = Source(source_name.lower())
        except ValueError as e:
            supported = [s.value for s in Source]
            raise ValueError(
                f"Unknown source: '{source_name}'. Supported sources: {supported}"
            ) from e

    # 获取主数据源
    data_source = source_service.get_source(source_key)

    # 获取 FRED 数据源（用于大宗商品数据）
    fred_source = None
    try:
        fred_source = source_service.get_source(Source.FRED)
    except Exception as e:
        logger.warning(f"FRED source not available: {e}")

    # 创建协调器
    coordinator = IngestionCoordinator(
        metadata_service=metadata_service,
        market_service=market_service,
        fundamental_service=fundamental_service,
        capital_service=capital_service,
        macro_service=macro_service,
        source=data_source,
        source_name=source_key.value,
        ingestion_log_service=ingestion_log_service,
        ingestion_cursor_service=ingestion_cursor_service,
        quality_service=quality_service,
        freeze_service=freeze_service,
        fred_source=fred_source,
    )

    yield coordinator


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

__all__ = [
    "API_LIMITS",
    "EARLIEST_LIST_DATE_INFERENCE",
    "EXCHANGE_PREFIX_MAP",
    "MARKET_INDEX_CODES",
    "STYLE_INDEX_CODES",
    "SUPPORTED_INSTRUMENT_DATASETS",
    "TRADING_DAYS_PER_YEAR",
    "BackfillManager",
    "IngestionConfig",
    "IngestionCoordinator",
    "IngestionDataWriter",
    "IngestionResultHandler",
    "ListDateInferenceService",
    "MetadataManager",
    "RetryManager",
    "SWIndustryProvider",
    "count_results",
    "create_coordinator",
    "get_all_index_codes",
    "get_default_index_codes",
    "get_sw_index_codes",
]
