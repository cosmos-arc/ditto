"""数据合并处理器."""

from __future__ import annotations

import polars as pl


class StatusMerger:
    """
    状态数据合并器.

    负责合并股票的状态数据（list_status + suspend + ST）.

    """

    @staticmethod
    def _collapse_text_rows(df: pl.DataFrame, column: str) -> pl.DataFrame:
        """Collapse one provider's repeated ticker rows deterministically."""
        return df.group_by("ts_code", maintain_order=True).agg(
            pl.col(column)
            .cast(pl.String)
            .drop_nulls()
            .unique()
            .sort()
            .str.join(";")
            .alias(column)
        )

    def merge_status_data(
        self,
        list_status_df: pl.DataFrame,
        suspend_df: pl.DataFrame,
        st_df: pl.DataFrame,
        trade_date: str,
    ) -> pl.DataFrame:
        """
        合并状态数据（list_status + suspend + ST）.

        Args:
            list_status_df: 上市状态数据 (columns: ts_code, list_status)
            suspend_df: 停牌数据 (columns: ts_code, suspend_timing)
            st_df: ST状态数据 (columns: ts_code, name)
            trade_date: 交易日期 (YYYY-MM-DD 格式)

        Returns:
            DataFrame with columns:
            - source_ticker: 股票代码
            - trade_date: 交易日期
            - is_suspended: 是否停牌 (Boolean)
            - suspend_timing: 停牌时间段 (String, e.g. "09:30-10:00" or "")
            - is_st: 是否ST (Boolean)
            - st_type: ST类型 (String, e.g. "ST" or "")
            - list_status: 上市状态 (String: L=正常, D=退市, P=暂停)

        """
        # Start with all stock codes from list_status (as reference)
        result = list_status_df.unique(
            subset=["ts_code"],
            keep="last",
            maintain_order=True,
        ).rename({"ts_code": "source_ticker"})

        # Add suspension info
        if not suspend_df.is_empty():
            suspend_expanded = self._collapse_text_rows(
                suspend_df,
                "suspend_timing",
            ).with_columns(pl.lit(True).alias("is_suspended"))
            result = result.join(
                suspend_expanded.rename({"ts_code": "source_ticker"}),
                on="source_ticker",
                how="left",
            )
        else:
            result = result.with_columns(pl.lit(None).alias("is_suspended"))
            result = result.with_columns(pl.lit(None).alias("suspend_timing"))

        # Add ST status
        if not st_df.is_empty():
            st_expanded = self._collapse_text_rows(st_df, "name").with_columns(
                pl.lit(True).alias("is_st"),
                pl.col("name").alias("st_type"),
            )
            result = result.join(
                st_expanded.rename({"ts_code": "source_ticker"}),
                on="source_ticker",
                how="left",
            )
        else:
            result = result.with_columns(pl.lit(None).alias("is_st"))
            result = result.with_columns(pl.lit(None).alias("st_type"))

        # Fill null values with defaults
        result = result.with_columns(
            pl.col("is_suspended").fill_null(False),
            pl.col("suspend_timing").fill_null(""),
            pl.col("is_st").fill_null(False),
            pl.col("st_type").fill_null(""),
            pl.col("list_status").fill_null("L"),  # Default to 正常
        )

        # Add trade_date column
        result = result.with_columns(
            pl.lit(trade_date).str.to_date("%Y-%m-%d").alias("trade_date")
        )

        # Select and reorder columns
        result = result.select(
            "source_ticker",
            "trade_date",
            "is_suspended",
            "suspend_timing",
            "is_st",
            "st_type",
            "list_status",
        )

        return result
