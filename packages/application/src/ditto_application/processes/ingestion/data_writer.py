"""统一数据写入器 — 行情/基本面/资本面/宏观/元数据写入."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import ClassVar, Literal, cast

import polars as pl
from ditto_data.config.dataset_checksum import dataset_sort_keys
from ditto_data.models import Dataset
from ditto_data.services.capital_store import CapitalStore
from ditto_data.services.fundamental_store import FundamentalStore
from ditto_data.services.macro_service import MacroService
from ditto_data.services.market_write_service import MarketWriteService
from ditto_data.services.metadata_service import MetadataService
from ditto_platform.foundation import ChecksumCompute, OnDuplicate, WriteResult, logger

from ditto_application.exceptions import AppProcessError
from ditto_application.processes.ingestion.dataset_registry import (
    DatasetRegistration,
    WriteKind,
    default_dataset_registry,
)


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
    standardized_df = standardized_df.with_columns(
        pl.col("source_ticker").cast(pl.Utf8)
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
        },
        schema={"source_ticker": pl.Utf8, "instrument_id": pl.Int64},
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


@dataclass(frozen=True)
class _WriteContext:
    """Packed parameters for write handler dispatch."""

    registration: DatasetRegistration
    dataset: str
    dataset_enum: Dataset
    df: pl.DataFrame
    year: int
    on_duplicate: OnDuplicate
    source_ticker_col: str
    trade_date: str


class IngestionDataWriter:
    """统一数据写入器。"""

    def __init__(
        self,
        metadata_service: MetadataService,
        market_write_service: MarketWriteService,
        fundamental_store: FundamentalStore,
        capital_store: CapitalStore,
        macro_service: MacroService,
        source_name: str,
    ) -> None:
        """
        初始化 IngestionDataWriter。

        Args:
            metadata_service: MetadataService 实例
            market_write_service: MarketWriteService 实例
            fundamental_store: FundamentalStore 实例
            capital_store: CapitalStore 实例
            macro_service: MacroService 实例
            source_name: 数据源名称

        """
        self._metadata_service = metadata_service
        self._market_write_service = market_write_service
        self._fundamental_store = fundamental_store
        self._capital_store = capital_store
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
            dataset_enum = Dataset(dataset)
        except ValueError as e:
            raise AppProcessError(
                f"不支持写入数据集: {dataset}",
                field="dataset",
                value=dataset,
            ) from e

        registration = default_dataset_registry().require(dataset_enum)
        year = int(trade_date[:4]) if registration.requires_year_partition else 0

        ctx = _WriteContext(
            registration=registration,
            dataset=dataset,
            dataset_enum=dataset_enum,
            df=df,
            year=year,
            on_duplicate=on_duplicate,
            source_ticker_col="source_ticker",
            trade_date=trade_date,
        )
        handler = self._build_write_handler(ctx)
        return handler()

    def _build_write_handler(self, ctx: _WriteContext) -> Callable[[], WriteResult]:
        """Build the writer callable from registry metadata."""
        if ctx.registration.write_kind == WriteKind.UNSUPPORTED:
            raise AppProcessError(
                f"不支持写入数据集: {ctx.dataset}",
                field="dataset",
                value=ctx.dataset,
            )
        handler_name = self._HANDLER_NAMES.get(ctx.registration.write_kind)
        if handler_name is None:
            raise AppProcessError(
                f"未知写入路由: {ctx.registration.write_kind.value}",
                field="dataset",
                value=ctx.dataset,
            )
        handler = getattr(self, handler_name)
        return handler(ctx)

    _HANDLER_NAMES: ClassVar[dict[WriteKind, str]] = {
        WriteKind.TRADED_BARS: "_handler_traded_bars",
        WriteKind.INSTRUMENT_CODE_BARS: "_handler_instrument_code_bars",
        WriteKind.STOCK_STATUS: "_handler_stock_status",
        WriteKind.ADJ_FACTOR: "_handler_adj_factor",
        WriteKind.FUND_ADJ: "_handler_fund_adj",
        WriteKind.FUNDAMENTAL: "_handler_fundamental",
        WriteKind.CAPITAL: "_handler_capital",
        WriteKind.MACRO: "_handler_macro",
        WriteKind.CALENDAR: "_handler_calendar",
        WriteKind.BASIC: "_handler_basic",
    }

    def _handler_traded_bars(self, ctx: _WriteContext) -> Callable[[], WriteResult]:
        bars_dataset = cast(
            Literal[
                "stock_daily",
                "etf_daily",
                "index_daily",
                "fx_daily",
                "commodity_daily",
            ],
            ctx.registration.write_dataset,
        )
        return lambda: self._write_traded_bars(
            ctx.dataset,
            ctx.df,
            ctx.year,
            ctx.on_duplicate,
            ctx.source_ticker_col,
            bars_dataset,
        )

    def _handler_instrument_code_bars(
        self, ctx: _WriteContext
    ) -> Callable[[], WriteResult]:
        bars_dataset = cast(
            Literal["fx_daily", "commodity_daily"],
            ctx.registration.write_dataset,
        )
        return lambda: self._write_instrument_code_bars(
            ctx.dataset, ctx.df, ctx.year, ctx.on_duplicate, bars_dataset
        )

    def _handler_stock_status(self, ctx: _WriteContext) -> Callable[[], WriteResult]:
        return lambda: self._write_stock_status(
            ctx.dataset, ctx.df, ctx.year, ctx.source_ticker_col
        )

    def _handler_adj_factor(self, ctx: _WriteContext) -> Callable[[], WriteResult]:
        return lambda: self._write_adj_factor(
            ctx.dataset, ctx.df, ctx.year, ctx.on_duplicate, ctx.source_ticker_col
        )

    def _handler_fund_adj(self, ctx: _WriteContext) -> Callable[[], WriteResult]:
        return lambda: self._write_fund_adj(
            ctx.dataset, ctx.df, ctx.year, ctx.on_duplicate, ctx.source_ticker_col
        )

    def _handler_fundamental(self, ctx: _WriteContext) -> Callable[[], WriteResult]:
        return lambda: self._write_fundamental(
            ctx.dataset, ctx.dataset_enum, ctx.df, ctx.year
        )

    def _handler_capital(self, ctx: _WriteContext) -> Callable[[], WriteResult]:
        return lambda: self._write_capital(
            ctx.dataset, ctx.dataset_enum, ctx.df, ctx.year
        )

    def _handler_macro(self, ctx: _WriteContext) -> Callable[[], WriteResult]:
        return lambda: self._write_macro(ctx.dataset, ctx.df, ctx.year)

    def _handler_calendar(self, ctx: _WriteContext) -> Callable[[], WriteResult]:
        return lambda: self._write_calendar(ctx.df, ctx.trade_date)

    def _handler_basic(self, ctx: _WriteContext) -> Callable[[], WriteResult]:
        asset_class = ctx.registration.basic_asset_class
        if asset_class is None:
            raise AppProcessError(
                f"数据集 {ctx.dataset} 缺少 basic_asset_class 定义",
                field="dataset",
                value=ctx.dataset,
            )
        return lambda: self._write_basic(ctx.df, ctx.trade_date, asset_class)

    def _resolve_and_enrich_instrument_id(
        self,
        df: pl.DataFrame,
        source_ticker_col: str,
    ) -> pl.DataFrame:
        """解析 instrument_id 并 enrich（统一入口）."""
        if "instrument_id" in df.columns:
            return df
        source_tickers = df[source_ticker_col].unique().to_list()
        instrument_id_mapping = (
            self._metadata_service.instrument.resolve_instrument_ids_batch(
                identifiers=source_tickers,
                source=self._source_name,
                asof=None,
            )
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

    def _write_fund_adj(
        self,
        dataset: str,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate,
        source_ticker_col: str,
    ) -> WriteResult:
        """Write ETF adjustment factors through the dedicated ETF storage port."""
        enriched_df = self._resolve_and_enrich_instrument_id(df, source_ticker_col)
        rows_written = self._market_write_service.save_fund_adj(
            df=enriched_df,
            year=year,
            on_duplicate=on_duplicate,
        )
        return _to_write_result(dataset, year, enriched_df, rows_written)

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
            instrument_id_mapping = (
                self._metadata_service.instrument.resolve_instrument_ids_batch(
                    identifiers=source_tickers,
                    source=self._source_name,
                    asof=None,
                )
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
            Dataset.BALANCE_SHEET: self._fundamental_store.save_balance_sheet,
            Dataset.INCOME_STATEMENT: self._fundamental_store.save_income_statement,
            Dataset.CASH_FLOW: self._fundamental_store.save_cash_flow,
            Dataset.DIVIDEND: self._fundamental_store.save_dividend,
            Dataset.CORPORATE_ACTIONS: self._fundamental_store.save_corporate_actions,
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
            "valuation_metrics": self._capital_store.save_valuation_metrics,
            "margin_trading": self._capital_store.save_margin_trading,
            "pledge_ratio": self._capital_store.save_pledge_ratio,
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
        self._metadata_service.calendar.save_calendar(records=records)
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
        return self._metadata_service.instrument.register_instruments_batch(
            df=df,
            source=self._source_name,
            asset_class=asset_class,
            source_ticker_col="source_ticker",
        )
