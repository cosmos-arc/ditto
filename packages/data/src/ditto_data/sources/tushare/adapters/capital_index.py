"""Capital index data: index weight and index composition."""

from __future__ import annotations

from datetime import date

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
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """
        获取指数月度权重观察数据.

        #452: trade_date 是月度权重观察日，不是成分调整生效日；官方不提供
        公告/发布时刻，本方法只返回观察事实，不伪造 effective_from/effective_to。

        Args:
            index_code: 指数代码 (e.g., "000001.SH").
            trade_date: 观察日 (YYYYMMDD), None 表示最新.
            start_date: 可选区间开始日期 (YYYYMMDD).
            end_date: 可选区间结束日期 (YYYYMMDD).

        Returns:
            DataFrame with columns:
            - index_code: 指数代码
            - source_ticker: 成分股代码
            - trade_date: 月度权重观察日 (Date)
            - weight: 权重

        Raises:
            SourceFetchError: If fetch fails.

        """
        if trade_date and (start_date or end_date):
            raise ValueError("trade_date is mutually exclusive with start/end date")
        if (start_date is None) != (end_date is None):
            raise ValueError("start_date and end_date must be supplied together")

        params: dict[str, str] = {
            "api_name": "index_weight",
            "index_code": index_code,
            "fields": "index_code,con_code,trade_date,weight",
        }
        if trade_date:
            params["trade_date"] = trade_date
        if start_date is not None and end_date is not None:
            params["start_date"] = start_date
            params["end_date"] = end_date

        with tushare_fetch_error_handler("index_weight", "index_weight"):
            df = self._client.query(**params)

        if df.is_empty():
            logger.warning(
                "index_weight_empty",
                index_code=index_code,
                trade_date=trade_date,
            )
        else:
            if "index_code" not in df.columns:
                df = df.with_columns(pl.lit(index_code).alias("index_code"))
            if "trade_date" not in df.columns and trade_date is not None:
                df = df.with_columns(pl.lit(trade_date).alias("trade_date"))
            df = (
                df.rename({"con_code": "source_ticker"})
                .with_columns(
                    pl.col("trade_date")
                    .cast(pl.Utf8)
                    .str.replace_all("-", "")
                    .str.to_date("%Y%m%d")
                    .alias("trade_date"),
                )
                .select(
                    "index_code",
                    "source_ticker",
                    "trade_date",
                    "weight",
                )
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
        获取市场指数成分股（index_member 成员路径）.

        #452: 市场指数成分走旧 index_member 接口（in_date/out_date 是源端
        提供的成员进出边界）；index_member_all 是申万行业分类分级成员接口，
        只用于 industry.py 的申万路径，两者不得混用。官方同样不提供公告时刻，
        effective_from/effective_to 仅承载源端 in/out 边界，不得据此推导公告可知性。

        #517 接线裁决留档：本 adapter 不接入摄取计划——当前指数成分/权重的
        消费需求由 index_weight（月度权重观察，#452 语义）覆盖，index_member
        的独立价值（成员进出区间）尚无消费者；为假想需求扩表违反最小设计，
        出现真实消费场景（如按成员区间的 PIT 成分重建）时再接线并实测配额。

        Args:
            index_code: 指数代码 (e.g., "000001.SH")
            asof_date: 历史查询日期 (YYYY-MM-DD), None 表示最新
            with_weight: 是否获取权重数据（需要额外 API 调用）

        Returns:
            DataFrame with columns:
            - index_id: 指数代码
            - source_ticker: 股票代码
            - weight: 权重
            - effective_from: 源端成员纳入日
            - effective_to: 源端成员剔除日（在籍为 null）

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

            response = self._client.query(**params)

            # index_member 返回现役+历史成员；asof/最新语义在本地显式按
            # is_new 与 in/out 边界过滤，边界未知的行 fail closed 丢弃。
            response = _apply_member_boundary(response, asof_date)

            # 添加 index_code 列和默认权重
            response = response.with_columns(
                pl.lit(index_code).alias("index_code"),
                pl.lit(1.0).alias("weight"),
            )

            result = TushareDataTransformer.transform(
                response, "index_composition", INDEX_COMPOSITION_MAPPING
            )

            # 如果需要真实权重，获取并替换默认值（与 fetch_index_weight
            # 使用同一 source_ticker 键）
            if with_weight and not result.is_empty():
                weight_df = self.fetch_index_weight(
                    index_code,
                    asof_date.replace("-", "") if asof_date else None,
                )
                if not weight_df.is_empty():
                    weight_df = weight_df.select("source_ticker", "weight")
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


def _apply_member_boundary(
    members: pl.DataFrame, asof_date: str | None
) -> pl.DataFrame:
    """按 is_new（最新）/ in-out 边界（asof）显式过滤成员，未知边界 fail closed."""
    asof = date.fromisoformat(asof_date) if asof_date is not None else None
    normalized = members.with_columns(
        pl.col("in_date")
        .cast(pl.Utf8)
        .str.replace_all("-", "")
        .str.to_date("%Y%m%d", strict=False)
        .alias("_in_date"),
        pl.col("out_date")
        .cast(pl.Utf8)
        .str.replace_all("-", "")
        .str.to_date("%Y%m%d", strict=False)
        .alias("_out_date"),
        pl.col("is_new").cast(pl.Int64, strict=False).alias("_is_new"),
    )
    if asof is None:
        kept = normalized.filter(pl.col("_is_new") == 1)
    else:
        kept = normalized.filter(
            pl.col("_in_date").is_not_null()
            & (pl.col("_in_date") <= asof)
            & (pl.col("_out_date").is_null() | (pl.col("_out_date") > asof))
        )
    return kept.drop("_in_date", "_out_date", "_is_new")
