"""
数据写入器。

负责将摄取的数据写入到不同的 Store，包括：
- 行情数据（stock_daily, etf_daily, stock_status）→ MarketService
- 复权因子（adj_factor, fund_adj）→ AdjFactorStore
- 基础信息（stock_basic, etf_basic）→ InstrumentStore
- 日历（calendar）→ CalendarStore
"""

from collections.abc import Callable
from typing import Literal, cast

import polars as pl
from ditto_datahub.models import Dataset, OnDuplicate, WriteResult
from ditto_datahub.services.capital_service import CapitalService
from ditto_datahub.services.fundamental_service import FundamentalService
from ditto_datahub.services.macro_service import MacroService
from ditto_datahub.services.market_service import MarketService
from ditto_datahub.services.metadata_service import MetadataService
from ditto_infra.foundation.util.checksum import ChecksumCompute


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
        year = int(trade_date[:4])

        try:
            dataset_enum = Dataset(dataset)  # 转换为枚举进行比较
        except ValueError as e:
            raise ValueError(f"不支持写入数据集: {dataset}") from e

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
                dataset_enum,
                df,
                year,
                on_duplicate,
                source_ticker_col,
            ),
            Dataset.FUND_ADJ: lambda: self._write_adj_factor(
                dataset,
                dataset_enum,
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
            Dataset.FUTURES_POSITION: lambda: self._write_capital(
                dataset,
                dataset_enum,
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
        asset_class: Literal["stock", "etf"] = (
            "etf" if dataset_enum == Dataset.ETF_DAILY else "stock"
        )
        instrument_id_mapping = (
            self._metadata_service.resolve_or_create_instruments_batch(
                df=df,
                source=self._source_name,
                asset_class=asset_class,
                source_ticker_col=source_ticker_col,
            )
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
        # 解析或创建 instrument_id
        instrument_id_mapping = (
            self._metadata_service.resolve_or_create_instruments_batch(
                df=df,
                source=self._source_name,
                asset_class="index",
                source_ticker_col=source_ticker_col,
            )
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

    def _write_stock_status(
        self,
        dataset: str,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate,
        source_ticker_col: str,
    ) -> WriteResult:
        instrument_id_mapping = (
            self._metadata_service.resolve_or_create_instruments_batch(
                df=df,
                source=self._source_name,
                asset_class="stock",
                source_ticker_col=source_ticker_col,
            )
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
        dataset_enum: Dataset,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate,
        source_ticker_col: str,
    ) -> WriteResult:
        enriched_df = df
        if "instrument_id" not in df.columns:
            adj_asset_class: Literal["stock", "etf"] = (
                "etf" if dataset_enum == Dataset.FUND_ADJ else "stock"
            )
            instrument_id_mapping = (
                self._metadata_service.resolve_or_create_instruments_batch(
                    df=df,
                    source=self._source_name,
                    asset_class=adj_asset_class,
                    source_ticker_col=source_ticker_col,
                )
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
        # Map dataset enum to the appropriate save method
        save_methods = {
            Dataset.BALANCE_SHEET: self._fundamental_service.save_balance_sheet,
            Dataset.INCOME_STATEMENT: self._fundamental_service.save_income_statement,
            Dataset.CASH_FLOW: self._fundamental_service.save_cash_flow,
            Dataset.DIVIDEND: self._fundamental_service.save_dividend,
        }
        save_method = save_methods[dataset_enum]
        records_written = save_method(df)
        return _to_write_result(
            dataset,
            year,
            df,
            records_written,
        )

    def _write_capital(
        self,
        dataset: str,
        dataset_enum: Dataset,
        df: pl.DataFrame,
        year: int,
    ) -> WriteResult:
        capital_dataset = cast(
            Literal[
                "valuation_metrics",
                "margin_trading",
                "pledge_ratio",
                "futures_position",
            ],
            dataset_enum.value,
        )
        # 使用特定的 save_* 方法替代已删除的 write() 方法
        if capital_dataset == "valuation_metrics":
            records_written = self._capital_service.save_valuation_metrics(df)
        elif capital_dataset == "margin_trading":
            records_written = self._capital_service.save_margin_trading(df)
        elif capital_dataset == "pledge_ratio":
            records_written = self._capital_service.save_pledge_ratio(df)
        elif capital_dataset == "futures_position":
            records_written = self._capital_service.save_futures(df)
        else:
            records_written = 0
        return _to_write_result(
            dataset,
            year,
            df,
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
