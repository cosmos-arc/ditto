"""Capital index data: index weight and index composition."""

from __future__ import annotations

import polars as pl
from ditto_platform.foundation import Metrics, logger, traced

from ditto_data.sources.tushare.adapters.base import BaseTushareAdapter
from ditto_data.sources.tushare.processors.error_handler import (
    tushare_fetch_error_handler,
)
from ditto_data.sources.tushare.processors.mappings import INDEX_COMPOSITION_MAPPING
from ditto_data.sources.tushare.processors.transformer import TushareDataTransformer


class CapitalIndexTushareAdapter(BaseTushareAdapter):
    """
    Capital index data Tushare adapter.

    提供指数相关数据的 Tushare API 访问，包括：
    - 指数权重
    - 指数成分股

    """

    @traced("source.tushare.fetch_index_weight")
    def fetch_index_weight(
        self,
        index_code: str,
        trade_date: str | None = None,
    ) -> pl.DataFrame:
        """
        获取指数权重数据.

        Args:
            index_code: 指数代码 (e.g., "000001.SH").
            trade_date: 交易日期 (YYYYMMDD), None 表示最新.

        Returns:
            DataFrame with raw Tushare columns (con_code, weight, trade_date, etc.).

        Raises:
            SourceFetchError: If fetch fails.

        """
        params: dict[str, str] = {
            "api_name": "index_weight",
            "index_code": index_code,
            "fields": "con_code,weight",
        }
        if trade_date:
            params["trade_date"] = trade_date

        with tushare_fetch_error_handler("index_weight", "index_weight"):
            df = self._client.query(**params)

        if df.is_empty():
            logger.warning(
                "index_weight_empty",
                index_code=index_code,
                trade_date=trade_date,
            )

        Metrics.data_records.add(
            df.height,
            {
                "source": "tushare",
                "dataset": "index_weight",
                "status": "success",
            },
        )
        return df

    @traced("source.tushare.fetch_index_composition")
    def fetch_index_composition(
        self,
        index_code: str,
        asof_date: str | None = None,
        with_weight: bool = False,
    ) -> pl.DataFrame:
        """
        获取指数成分股.

        Args:
            index_code: 指数代码 (e.g., "000001.SH")
            asof_date: 历史查询日期 (YYYY-MM-DD), None 表示最新
            with_weight: 是否获取权重数据（需要额外 API 调用）

        Returns:
            DataFrame with columns:
            - index_id: 指数代码
            - source_ticker: 股票代码
            - weight: 权重
            - effective_from: 生效开始日期
            - effective_to: 生效结束日期

        Raises:
            SourceFetchError: If fetch fails.

        """
        logger.info(
            "Fetching Tushare index composition",
            event="tushare_index_composition_fetch_start",
            index_code=index_code,
            asof_date=asof_date,
        )

        with tushare_fetch_error_handler("index_composition", "index_member"):
            params: dict[str, str] = {
                "api_name": "index_member",
                "index_code": index_code,
                "fields": "ts_code,in_date,out_date,is_new",
            }

            if asof_date:
                params["date"] = asof_date.replace("-", "")

            response = self._client.query(**params)

            # 添加 index_code 列和默认权重
            response = response.with_columns(
                pl.lit(index_code).alias("index_code"),
                pl.lit(1.0).alias("weight"),
            )

            result = TushareDataTransformer.transform(
                response, "index_composition", INDEX_COMPOSITION_MAPPING
            )

            # 如果需要真实权重，获取并替换默认值
            if with_weight and not result.is_empty():
                weight_df = self.fetch_index_weight(
                    index_code,
                    asof_date.replace("-", "") if asof_date else None,
                )
                if not weight_df.is_empty():
                    weight_df = weight_df.select("con_code", "weight").rename(
                        {"con_code": "source_ticker"}
                    )
                    result = result.drop("weight").join(
                        weight_df,
                        on="source_ticker",
                        how="left",
                    )

            row_count = len(result)
            logger.info(
                "Tushare index composition fetched",
                event="tushare_index_composition_fetch_complete",
                row_count=row_count,
            )
            Metrics.data_records.add(
                row_count,
                {
                    "source": "tushare",
                    "dataset": "index_composition",
                    "status": "success",
                },
            )

            return result
