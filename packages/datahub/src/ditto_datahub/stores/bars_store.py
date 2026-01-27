"""
Market bars storage with year partitioning.

Stores market daily data (stock/ETF) in Parquet files with year partitioning.
Following design document at docs/design/02_data_design.md.
"""

from __future__ import annotations

import time
from datetime import datetime

import polars as pl
from ditto_foundation import M, logger, traced
from ditto_foundation.util.io import file_md5

from ditto_datahub.stores.base import ParquetStore

# Default year range for date filters
DEFAULT_START_YEAR = 1990
DEFAULT_END_YEAR = 2099


class BarsStore(ParquetStore):
    """
    Market bars data storage with year partitioning.

    Storage structure:
        data_root/
            stock_daily/
                2020.parquet
                2021.parquet
                ...
            etf_daily/
                2020.parquet
                ...
    """

    def _get_key_columns(self) -> list[str]:
        """返回键列名."""
        return ["sid", "trade_date"]

    def _get_sort_columns(self) -> list[str]:
        """返回排序列名（BarsStore 使用 trade_date, sid 顺序）."""
        return ["trade_date", "sid"]

    def _ensure_date_column(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Ensure trade_date column is Date type for sorting.

        Args:
            df: Input DataFrame.

        Returns:
            DataFrame with trade_date as Date type.

        """
        dtype = df["trade_date"].dtype

        # If already Date type, return as-is
        if dtype == pl.Date:
            return df

        # If String type, convert to Date
        if dtype == pl.String:
            return df.with_columns(pl.col("trade_date").str.to_date())

        # If Object type (could be date objects or strings), try to convert
        if dtype == pl.Object:
            # Try casting to string first, then to date
            try:
                return df.with_columns(
                    pl.col("trade_date").cast(pl.String).str.to_date()
                )
            except Exception:
                # If that fails, the column might already contain date objects
                # Just return the DataFrame as-is and hope for the best
                return df

        return df

    def _prepare_for_write(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        准备写入：归一化日期列并排序。

        BarsStore 覆盖此方法以使用特殊的日期列处理和排序顺序。

        Args:
            df: 输入 DataFrame。

        Returns:
            准备好的 DataFrame。

        """
        # Ensure trade_date is date type for sorting
        df = self._ensure_date_column(df)
        # Sort for optimal read performance
        return df.sort(self._get_sort_columns())

    # ============ Read operations ============

    def _build_filter_conditions(
        self,
        lf: pl.LazyFrame,
        sids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.LazyFrame:
        """
        Build filter conditions for LazyFrame.

        Args:
            lf: LazyFrame to filter.
            sids: Filter by security IDs.
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).

        Returns:
            Filtered LazyFrame.

        """
        if sids:
            lf = lf.filter(pl.col("sid").is_in(sids))

        if start_date:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
            lf = lf.filter(pl.col("trade_date") >= start_dt)

        if end_date:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
            lf = lf.filter(pl.col("trade_date") <= end_dt)

        return lf

    @traced("data.read")
    def read(
        self,
        dataset: str,
        sids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        **kwargs: object,
    ) -> pl.DataFrame:
        """
        Read market bars data.

        Args:
            dataset: Dataset name (e.g., "stock_daily", "etf_daily").
            sids: Filter by security IDs.
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).
            **kwargs: Additional arguments (ignored).

        Returns:
            DataFrame with matching records.

        """
        start_time = time.time()

        # Determine year range from date filters
        start_year = int(start_date[:4]) if start_date else DEFAULT_START_YEAR
        end_year = int(end_date[:4]) if end_date else DEFAULT_END_YEAR

        paths = self._collect_paths(dataset, start_year, end_year)

        if not paths:
            logger.info(
                "No data found for query",
                event="data_read_complete",
                dataset=dataset,
                start_date=start_date,
                end_date=end_date,
                row_count=0,
                duration_ms=0,
            )
            return pl.DataFrame()

        # Scan and apply filters
        lf = pl.scan_parquet([str(p) for p in paths])
        lf = self._build_filter_conditions(lf, sids, start_date, end_date)
        result = lf.unique(subset=self._get_key_columns(), keep="last").collect()

        duration_ms = (time.time() - start_time) * 1000

        logger.info(
            "Data read completed",
            event="data_read_complete",
            dataset=dataset,
            start_date=start_date,
            end_date=end_date,
            sids_count=len(sids) if sids else None,
            row_count=len(result),
            duration_ms=round(duration_ms, 2),
        )

        # Record metrics
        M.data_records.add(len(result), {"dataset": dataset, "status": "success"})
        M.data_update_duration.record(duration_ms / 1000, {"dataset": dataset})

        return result

    # ============ Metadata operations ============

    def get_years(self, dataset: str) -> list[int]:
        """
        获取数据集的可用年份列表.

        Args:
            dataset: 数据集名称.

        Returns:
            排序后的年份列表.

        """
        dataset_dir = self._data_root / dataset
        if not dataset_dir.exists():
            return []

        years: list[int] = []
        for f in dataset_dir.glob("*.parquet"):
            try:
                year = int(f.stem)
                years.append(year)
            except ValueError:
                # 跳过不符合年份命名规范的文件
                continue

        return sorted(years)

    def delete_year(self, dataset: str, year: int) -> bool:
        """
        删除指定年份的分区文件.

        Args:
            dataset: 数据集名称.
            year: 年份.

        Returns:
            如果删除成功返回 True，文件不存在返回 False.

        """
        path = self._get_path(dataset, year)
        if path.exists():
            path.unlink()
            return True
        return False

    def get_checksum(self, dataset: str, year: int) -> str:
        """
        获取年份分区文件的 MD5 校验和.

        Args:
            dataset: 数据集名称.
            year: 年份.

        Returns:
            校验和十六进制字符串，文件不存在返回空字符串.

        """
        path = self._get_path(dataset, year)
        if path.exists():
            result: str = file_md5(path)
            return result
        return ""

    def count(
        self,
        dataset: str,
        sids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> int:
        """
        统计数据集中的记录数.

        Args:
            dataset: 数据集名称.
            sids: 按证券 ID 过滤.
            start_date: 起始日期 (YYYY-MM-DD).
            end_date: 结束日期 (YYYY-MM-DD).

        Returns:
            匹配的记录数.

        """
        df = self.read(dataset, sids=sids, start_date=start_date, end_date=end_date)
        return len(df)

    def get_date_range(self, dataset: str) -> tuple[str | None, str | None]:
        """
        获取数据集的整体日期范围.

        Args:
            dataset: 数据集名称.

        Returns:
            (起始日期, 结束日期) 元组，空数据集返回 (None, None).

        """
        years = self.get_years(dataset)
        if not years:
            return None, None

        # 扫描所有分区并找到最小/最大日期
        paths = self._collect_paths(dataset, min(years), max(years))
        if not paths:
            return None, None

        lf = pl.scan_parquet([str(p) for p in paths])
        min_max = lf.select(
            [
                pl.col("trade_date").min().alias("min"),
                pl.col("trade_date").max().alias("max"),
            ]
        ).collect()

        if len(min_max) == 0 or min_max["min"][0] is None:
            return None, None

        return str(min_max["min"][0]), str(min_max["max"][0])

    def list_sids(self, dataset: str) -> list[int]:
        """
        列出数据集中的唯一证券 ID.

        Args:
            dataset: 数据集名称.

        Returns:
            排序后的唯一证券 ID 列表.

        """
        years = self.get_years(dataset)
        if not years:
            return []

        paths = self._collect_paths(dataset, min(years), max(years))
        if not paths:
            return []

        lf = pl.scan_parquet([str(p) for p in paths])
        result = lf.select(pl.col("sid").unique()).collect()

        sids: list[int] = result["sid"].to_list()
        return sids
