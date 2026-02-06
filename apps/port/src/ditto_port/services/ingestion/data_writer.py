"""
数据写入器。

负责将摄取的数据写入到不同的 Store，包括：
- 行情数据（stock_daily, etf_daily）→ BarsStore
- 复权因子（adj_factor, fund_adj）→ AdjFactorStore
- 基础信息（stock_basic, etf_basic）→ InstrumentStore
- 日历（calendar）→ CalendarStore
"""

from typing import Literal

import polars as pl
from ditto_datahub.hub import DataHub
from ditto_datahub.models import Dataset, OnDuplicate, WriteResult
from ditto_foundation.util.checksum import ChecksumCompute


def _map_on_duplicate(on_duplicate: OnDuplicate) -> str:
    """
    将 OnDuplicate 枚举转换为 MarketService 期望的字符串值。

    Args:
        on_duplicate: OnDuplicate 枚举值

    Returns:
        MarketService 期望的字符串值

    """
    mapping = {
        OnDuplicate.ERROR: "error",
        OnDuplicate.KEEP_FIRST: "skip",
        OnDuplicate.KEEP_LAST: "overwrite",
    }
    return mapping.get(on_duplicate, "error")


def _enrich_with_sid(
    df: pl.DataFrame,
    sid_mapping: dict[str, int],
    src_code_col: str,
    source: str,
) -> pl.DataFrame:
    """
    为 DataFrame 添加 sid 和 source 列。

    Args:
        df: 输入 DataFrame，必须包含 src_code_col 指定的列
        sid_mapping: {src_code: sid} 映射字典
        src_code_col: 源代码列名
        source: 数据源标识符

    Returns:
        添加了 sid 和 source 列的 DataFrame

    """
    # 处理空 DataFrame
    if len(df) == 0:
        return df.with_columns(
            pl.lit(None, dtype=pl.Int32).alias("sid"),
            pl.lit(source).alias("source"),
        )

    # 将 sid 映射转换为 DataFrame 并 join
    mapping_df = pl.DataFrame(
        {
            src_code_col: list(sid_mapping.keys()),
            "sid": list(sid_mapping.values()),
        }
    )

    return df.join(mapping_df, on=src_code_col, how="left").with_columns(
        pl.lit(source).alias("source")
    )


def _to_write_result(
    dataset: str,
    year: int,
    df: pl.DataFrame,
    result: dict[str, int],
) -> WriteResult:
    """
    将 MarketService 返回的 dict 转换为 WriteResult。

    Args:
        dataset: 数据集名称
        year: 年份
        df: 写入的 DataFrame（用于计算 checksum）
        result: MarketService 返回的结果字典

    Returns:
        WriteResult 对象

    """
    rows = result.get("rows", 0)
    files = result.get("files", 0)
    checksum = ChecksumCompute.from_dataframe(df, dataset)
    return WriteResult(
        file_path=f"{dataset}/{year}",
        checksum=checksum,
        rows_written=rows,
        rows_total=rows,
        blocked=files == 0,  # 如果没有文件写入，则认为被阻塞
    )


class IngestionDataWriter:
    """统一数据写入器。"""

    def __init__(self, hub: DataHub, source_name: str) -> None:
        """
        初始化 IngestionDataWriter。

        Args:
            hub: DataHub 实例
            source_name: 数据源名称

        """
        self._hub = hub
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

        # 转换为枚举进行比较
        try:
            dataset_enum = Dataset(dataset)
        except ValueError as e:
            raise ValueError(f"不支持写入数据集: {dataset}") from e

        if dataset_enum in (Dataset.ETF_DAILY, Dataset.STOCK_DAILY):
            # 补齐 sid/source 字段（使用 MetadataService API）
            asset_class: Literal["stock", "etf"] = (
                "etf" if dataset_enum == Dataset.ETF_DAILY else "stock"
            )
            # 解析或创建证券，获取 sid 映射
            sid_mapping = self._hub.metadata.resolve_or_create_batch(
                df=df,
                source=self._source_name,
                asset_class=asset_class,
                src_code_col="src_code",
            )
            # 添加 sid 列
            df = _enrich_with_sid(df, sid_mapping, "src_code", self._source_name)
            # 转换 OnDuplicate 枚举为字符串
            on_duplicate_str = _map_on_duplicate(on_duplicate)
            # 使用 MarketService 写入（替代 BarsAccessor）
            result = self._hub.market.write_bars(
                df=df,
                year=year,
                dataset=dataset,
                on_duplicate=on_duplicate_str,
            )
            # 转换 dict[str, int] 为 WriteResult
            return _to_write_result(dataset, year, df, result)
        elif dataset_enum in (Dataset.ADJ_FACTOR, Dataset.FUND_ADJ):
            # 补齐 sid/source 字段（使用 MetadataService API）
            adj_asset_class: Literal["stock", "etf"] = (
                "etf" if dataset_enum == Dataset.FUND_ADJ else "stock"
            )

            # 检查是否已有 sid 列（上游可能已处理）
            if "sid" not in df.columns:
                # 解析或创建证券，获取 sid 映射
                sid_mapping = self._hub.metadata.resolve_or_create_batch(
                    df=df,
                    source=self._source_name,
                    asset_class=adj_asset_class,
                    src_code_col="src_code",
                )
                # 添加 sid 列
                df = _enrich_with_sid(df, sid_mapping, "src_code", self._source_name)

            # 使用 MarketService 写入（替代 AdjFactorAccessor）
            # 转换 OnDuplicate 枚举为字符串
            on_duplicate_str = _map_on_duplicate(on_duplicate)
            result = self._hub.market.write_adj_factor(
                dataset=dataset,
                df=df,
                year=year,
                on_duplicate=on_duplicate_str,
            )
            # 转换 dict[str, int] 为 WriteResult
            return _to_write_result(dataset, year, df, result)
        elif dataset_enum == Dataset.CALENDAR:
            records = df.to_dicts()
            self._hub.calendar.upsert(records)
            file_path = f"calendar_store:{trade_date}"
            # 修复：使用统一的 ChecksumCompute（MD5 算法，确定性排序）
            checksum = ChecksumCompute.from_dataframe(df, "calendar")
            return WriteResult(
                file_path=file_path,
                checksum=checksum,
                rows_written=len(df),
                rows_total=len(df),
                blocked=False,
            )
        elif dataset_enum == Dataset.STOCK_BASIC:
            file_path, checksum = self.write_stock_basic(df, trade_date)
            return WriteResult(
                file_path=file_path,
                checksum=checksum,
                rows_written=len(df),
                rows_total=len(df),
                blocked=False,
            )
        elif dataset_enum == Dataset.ETF_BASIC:
            file_path, checksum = self.write_etf_basic(df, trade_date)
            return WriteResult(
                file_path=file_path,
                checksum=checksum,
                rows_written=len(df),
                rows_total=len(df),
                blocked=False,
            )
        else:
            raise ValueError(f"不支持写入数据集: {dataset}")

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
        file_path, checksum = self._hub.metadata.register_securities_batch(
            df=df,
            source=self._source_name,
            asset_class="stock",
            src_code_col="src_code",
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
        file_path, checksum = self._hub.metadata.register_securities_batch(
            df=df,
            source=self._source_name,
            asset_class="etf",
            src_code_col="src_code",
        )

        return file_path, checksum
