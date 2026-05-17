"""统一数据写入器 — 行情/基本面/资本面/宏观/元数据写入."""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal, cast

import polars as pl
from ditto_data.config.dataset_checksum import dataset_sort_keys
from ditto_data.models import Dataset
from ditto_data.services.capital_service import CapitalService
from ditto_data.services.fundamental_service import FundamentalService
from ditto_data.services.macro_service import MacroService
from ditto_data.services.market_write_service import MarketWriteService
from ditto_data.services.metadata_service import MetadataService
from ditto_platform.foundation import ChecksumCompute, OnDuplicate, WriteResult, logger

from ditto_application.exceptions import AppProcessError


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
    checksum = ChecksumCompute.from_dataframe(df, dataset_sort_keys(dataset))
    return WriteResult(
        file_path=f"{dataset}/{year}",
        checksum=checksum,
        rows_written=rows_written,
        rows_total=rows_written,
        blocked=False,  # blocked 仅由显式 DQ 检查设置，不从 rows_written 推断
    )


class IngestionDataWriter:
    """统一数据写入器。"""

    def __init__(
        self,
        metadata_service: MetadataService,
        market_write_service: MarketWriteService,
        fundamental_service: FundamentalService,
        capital_service: CapitalService,
        macro_service: MacroService,
        source_name: str,
    ) -> None:
        """
        初始化 IngestionDataWriter。

        Args:
            metadata_service: MetadataService 实例
            market_write_service: MarketWriteService 实例
            fundamental_service: FundamentalService 实例
            capital_service: CapitalService 实例
            macro_service: MacroService 实例
            source_name: 数据源名称

        """
        self._metadata_service = metadata_service
        self._market_write_service = market_write_service
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
            AppProcessError: 不支持的数据集

        """
        try:
            dataset_enum = Dataset(dataset)  # 转换为枚举进行比较
        except ValueError as e:
            raise AppProcessError(
                f"不支持写入数据集: {dataset}",
                field="dataset",
                value=dataset,
            ) from e

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
        handlers = self._build_dataset_handlers(
            dataset=dataset,
            dataset_enum=dataset_enum,
            df=df,
            year=year,
            on_duplicate=on_duplicate,
            source_ticker_col=source_ticker_col,
            trade_date=trade_date,
        )

        if dataset_enum not in handlers:
            raise AppProcessError(
                f"不支持写入数据集: {dataset}",
                field="dataset",
                value=dataset,
            )

        return handlers[dataset_enum]()

    def _build_dataset_handlers(
        self,
        *,
        dataset: str,
        dataset_enum: Dataset,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate,
        source_ticker_col: str,
        trade_date: str,
    ) -> dict[Dataset, Callable[[], WriteResult]]:
        """Build the dataset-to-writer handler mapping."""
        return {
            Dataset.ETF_DAILY: lambda: self._write_traded_bars(
                dataset,
                df,
                year,
                on_duplicate,
                source_ticker_col,
                "etf_daily",
            ),
            Dataset.STOCK_DAILY: lambda: self._write_traded_bars(
                dataset,
                df,
                year,
                on_duplicate,
                source_ticker_col,
                "stock_daily",
            ),
            Dataset.STOCK_STATUS: lambda: self._write_stock_status(
                dataset,
                df,
                year,
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
            Dataset.INDEX_DAILY: lambda: self._write_traded_bars(
                dataset, df, year, on_duplicate, source_ticker_col, "index_daily"
            ),
            Dataset.FX_DAILY: lambda: self._write_instrument_code_bars(
                dataset,
                df,
                year,
                on_duplicate,
                "fx_daily",
            ),
            Dataset.COMMODITY_DAILY: lambda: self._write_instrument_code_bars(
                dataset,
                df,
                year,
                on_duplicate,
                "commodity_daily",
            ),
        }

    def _resolve_and_enrich_instrument_id(
        self,
        df: pl.DataFrame,
        source_ticker_col: str,
    ) -> pl.DataFrame:
        """解析 instrument_id 并 enrich（统一入口）."""
        if "instrument_id" in df.columns:
            return df
        source_tickers = df[source_ticker_col].unique().to_list()
        instrument_id_mapping = self._metadata_service.resolve_instrument_ids_batch(
            identifiers=source_tickers,
            source=self._source_name,
            asof=None,
        )
        return _enrich_with_instrument_id(
            df, instrument_id_mapping, source_ticker_col, self._source_name
        )

    def _write_traded_bars(
        self,
        dataset: str,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate,
        source_ticker_col: str,
        bars_dataset: Literal[
            "stock_daily", "etf_daily", "index_daily", "fx_daily", "commodity_daily"
        ],
    ) -> WriteResult:
        """写入行情 K 线数据（stock/etf/index 共用）."""
        enriched_df = self._resolve_and_enrich_instrument_id(df, source_ticker_col)
        rows_written = self._market_write_service.save_bars(
            dataset=bars_dataset,
            df=enriched_df,
            year=year,
            on_duplicate=on_duplicate,
        )
        return _to_write_result(dataset, year, enriched_df, rows_written)

    def _write_instrument_code_bars(
        self,
        dataset: str,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate,
        bars_dataset: Literal["fx_daily", "commodity_daily"],
    ) -> WriteResult:
        """Write instrument code daily bars (FX or Commodity)."""
        rows_written = self._market_write_service.save_bars(
            dataset=bars_dataset,
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
        source_ticker_col: str,
    ) -> WriteResult:
        enriched_df = self._resolve_and_enrich_instrument_id(df, source_ticker_col)
        rows_written = self._market_write_service.save_stock_status(
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
        enriched_df = self._resolve_and_enrich_instrument_id(df, source_ticker_col)

        rows_written = self._market_write_service.save_adj_factor(
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

    def _enrich_and_filter_fk_dataframe(
        self,
        df: pl.DataFrame,
        dataset: str,
        year: int,
        source_ticker_col: str = "source_ticker",
    ) -> pl.DataFrame | None:
        """
        解析 instrument_id 并过滤 null 外键记录。

        Args:
            df: 输入 DataFrame
            dataset: 数据集名称（用于日志）
            year: 年份（用于构造空结果）
            source_ticker_col: 源代码列名

        Returns:
            过滤后的 DataFrame，或 None 表示所有记录均被过滤。

        """
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

        total_count = len(enriched_df)
        enriched_df = enriched_df.filter(pl.col("instrument_id").is_not_null())
        filtered_count = total_count - len(enriched_df)
        if filtered_count > 0:
            logger.warning(
                f"Filtered {filtered_count} records with null instrument_id",
                dataset=dataset,
            )

        if len(enriched_df) == 0:
            return None
        return enriched_df

    def _write_fundamental(
        self,
        dataset: str,
        dataset_enum: Dataset,
        df: pl.DataFrame,
        year: int,
    ) -> WriteResult:
        enriched_df = self._enrich_and_filter_fk_dataframe(df, dataset, year)
        if enriched_df is None:
            return _to_write_result(dataset, year, df, 0)

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
        enriched_df = self._enrich_and_filter_fk_dataframe(df, dataset, year)
        if enriched_df is None:
            return _to_write_result(dataset, year, df, 0)

        capital_dataset = cast(
            Literal[
                "valuation_metrics",
                "margin_trading",
                "pledge_ratio",
            ],
            dataset_enum.value,
        )
        capital_methods = {
            "valuation_metrics": self._capital_service.save_valuation_metrics,
            "margin_trading": self._capital_service.save_margin_trading,
            "pledge_ratio": self._capital_service.save_pledge_ratio,
        }
        save_method = capital_methods.get(capital_dataset)
        if save_method is None:
            valid = ", ".join(capital_methods)
            raise AppProcessError(
                f"Unknown capital_dataset: {capital_dataset}. Expected: {valid}",
                field="dataset",
                value=capital_dataset,
                expected=tuple(capital_methods),
            )
        records_written = save_method(enriched_df)
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
        checksum = ChecksumCompute.from_dataframe(df, dataset_sort_keys("calendar"))
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
        file_path, checksum = self._write_basic_impl(df, asset_class)
        return WriteResult(
            file_path=file_path,
            checksum=checksum,
            rows_written=len(df),
            rows_total=len(df),
            blocked=False,
        )

    def _write_basic_impl(
        self,
        df: pl.DataFrame,
        asset_class: Literal["stock", "etf", "index"],
    ) -> tuple[str, str]:
        """
        使用 MetadataService 批量注册证券基础信息（幂等，依赖 PK 约束）。

        Args:
            df: 基础信息数据
            asset_class: 资产类别

        Returns:
            tuple[str, str]: (file_path, checksum)

        """
        return self._metadata_service.register_instruments_batch(
            df=df,
            source=self._source_name,
            asset_class=asset_class,
            source_ticker_col="source_ticker",
        )
