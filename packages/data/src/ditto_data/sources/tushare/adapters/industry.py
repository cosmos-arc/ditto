"""行业分类适配器实现（申万/证监会）."""

from __future__ import annotations

import polars as pl
from ditto_infra.foundation import Metrics, logger, traced

from ditto_data.sources.tushare.adapters.base import BaseTushareAdapter
from ditto_data.sources.tushare.processors.error_handler import (
    tushare_fetch_error_handler,
)
from ditto_data.sources.tushare.processors.transformer import (
    ColumnMapping,
    TushareDataTransformer,
)

# 申万行业分类列映射配置
SW_INDUSTRY_CLASSIFY_MAPPING = ColumnMapping(
    rename={"index_code": "source_ticker", "index_name": "industry_name"},
    date_columns={},
    float_columns=[],
    int_columns=("level",),
    output_columns=("source_ticker", "industry_name", "level"),
)

# 申万行业成分股列映射配置
# 注意：不关联 source_schema，因为最终输出需要添加 industry_date 和 knowledge_date 列
# 我们会在 fetch_sw_industry_concepts 方法中手动验证
SW_INDUSTRY_CONCEPTS_MAPPING = ColumnMapping(
    rename={"ts_code": "instrument_id", "name": "stock_name"},
    # 只转换 in_date，不转换 out_date（可能有 null）
    date_columns={"in_date": "%Y%m%d"},
    float_columns=[],
    int_columns=("is_new",),
    computed_columns={},
    output_columns=(
        "instrument_id",
        "stock_name",
        "index_code",
        "industry_name",
        "industry_level",
        # 保留 in_date 列，后面会重命名为 industry_date
        "in_date",
    ),
)


def _record_metrics(row_count: int, dataset: str) -> None:
    """
    安全地记录数据指标。

    如果 observability 未初始化，静默跳过。

    Args:
        row_count: 数据行数
        dataset: 数据集名称

    """
    try:
        Metrics.data_records.add(
            row_count,
            {"source": "tushare", "dataset": dataset, "status": "success"},
        )
    except (AttributeError, TypeError) as e:
        # Observability 未初始化，低噪日志
        logger.debug(
            "metrics_emit_skipped",
            event="observability_not_initialized",
            reason=str(e),
        )


class IndustryTushareAdapter(BaseTushareAdapter):
    """
    行业分类 Tushare 适配器.

    专门处理行业分类相关数据获取，包括：
    - 申万行业分类（一/二/三级行业）
    - 证监会行业分类
    - 股票的行业映射关系

    """

    @traced("source.tushare.fetch_sw_industry")
    def fetch_sw_industry(self, level: int = 1) -> pl.DataFrame:
        """
        获取申万行业分类.

        Args:
            level: 行业级别 (1=一级行业, 2=二级行业, 3=三级行业)

        Returns:
            DataFrame with columns:
            - source_ticker: 行业代码 (e.g., "801010.SI")
            - industry_name: 行业名称
            - level: 行业级别 (1, 2, or 3)

        Raises:
            SourceFetchError: If fetch fails.

        """
        logger.info(
            f"Fetching Tushare SW industry level {level}",
            event="tushare_sw_industry_fetch_start",
            level=level,
        )

        with tushare_fetch_error_handler("sw_industry", "index_classify"):
            response = self._client.query(
                api_name="index_classify",
                level=str(level),
                src="SW2021",
                fields="index_code,index_name,level",
            )

            result = TushareDataTransformer.transform(
                response, "sw_industry", SW_INDUSTRY_CLASSIFY_MAPPING
            )

            # 添加 industry_level 列（符合 INDUSTRY_SOURCE_SCHEMA）
            result = result.with_columns(
                pl.col("level").cast(pl.Int32).alias("industry_level")
            )

            row_count = len(result)
            logger.info(
                "Tushare SW industry fetched",
                event="tushare_sw_industry_fetch_complete",
                row_count=row_count,
                level=level,
            )
            _record_metrics(row_count, "sw_industry")

            return result

    @traced("source.tushare.fetch_sw_industry_concepts")
    def fetch_sw_industry_concepts(
        self,
        asof_date: str | None = None,
        level: int = 1,
    ) -> pl.DataFrame:
        """
        获取申万行业成分股.

        Args:
            asof_date: 历史查询日期 (YYYY-MM-DD), None 表示最新
            level: 行业级别 (1=一级行业, 2=二级行业, 3=三级行业)

        Returns:
            DataFrame with columns:
            - instrument_id: 股票代码 (e.g., "000001.SZ")
            - industry_name: 行业名称
            - industry_level: 行业级别
            - industry_date: 行业生效日期
            - knowledge_date: 知识日期

        Raises:
            SourceFetchError: If fetch fails.

        """
        logger.info(
            "Fetching Tushare SW industry concepts",
            event="tushare_sw_industry_concepts_fetch_start",
            asof_date=asof_date,
            level=level,
        )

        with tushare_fetch_error_handler("sw_industry_concepts", "index_member"):
            # Tushare API: index_member 获取指数成分股
            # 申万行业指数的成分股即为该行业的股票
            # 需要先获取所有申万行业代码，然后分别查询成分股

            # 1. 获取申万行业代码
            industries = self._client.query(
                api_name="index_classify",
                level=str(level),
                src="SW2021",
                fields="index_code,index_name",
            )

            if len(industries) == 0:
                logger.warning(
                    "No SW industries found",
                    event="tushare_sw_industry_concepts_no_industries",
                )
                return pl.DataFrame(schema=SW_INDUSTRY_CONCEPTS_MAPPING.output_columns)

            # 2. 查询每个行业的成分股
            all_concepts: list[pl.DataFrame] = []
            for industry_row in industries.iter_rows(named=True):
                index_code = industry_row["index_code"]
                industry_name = industry_row["index_name"]

                # 查询该行业的成分股
                params = {
                    "api_name": "index_member",
                    "index_code": index_code,
                    "fields": "ts_code,name,in_date,out_date,is_new",
                }

                if asof_date:
                    # 历史查询：指定查询日期
                    params["date"] = asof_date.replace("-", "")

                members = self._client.query(**params)

                if len(members) > 0:
                    # 添加行业信息
                    members = members.with_columns(
                        pl.lit(index_code).alias("index_code"),
                        pl.lit(industry_name).alias("industry_name"),
                        pl.lit(level).alias("industry_level"),
                    )
                    all_concepts.append(members)

            # 3. 合并所有成分股数据
            if not all_concepts:
                logger.warning(
                    "No SW industry concepts found",
                    event="tushare_sw_industry_concepts_empty",
                )
                return pl.DataFrame(schema=SW_INDUSTRY_CONCEPTS_MAPPING.output_columns)

            result = pl.concat(all_concepts)

            # 4. 数据转换和验证
            result = TushareDataTransformer.transform(
                result, "sw_industry_concepts", SW_INDUSTRY_CONCEPTS_MAPPING
            )

            # 5. 添加 industry_date 和 knowledge_date 列
            # in_date 已经在 date_columns 中转换为 Date 类型
            # industry_date = in_date（行业生效日期）
            # knowledge_date = in_date（数据可知日期）
            result = result.rename({"in_date": "industry_date"})
            result = result.with_columns(
                pl.col("industry_date").alias("knowledge_date")
            )

            # 6. 选择符合 INDUSTRY_SOURCE_SCHEMA 的最终列
            result = result.select(
                "instrument_id",
                "industry_name",
                "industry_level",
                "industry_date",
                "knowledge_date",
            )

            row_count = len(result)
            logger.info(
                "Tushare SW industry concepts fetched",
                event="tushare_sw_industry_concepts_fetch_complete",
                row_count=row_count,
            )
            _record_metrics(row_count, "sw_industry_concepts")

            return result

    @traced("source.tushare.fetch_csrc_industry")
    def fetch_csrc_industry(self) -> pl.DataFrame:
        """
        获取证监会行业分类.

        使用 Tushare csrc_industrial API 获取证监会行业分类数据。

        Returns:
            DataFrame with columns:
            - industry_id: 行业代码 (e.g., "M0001")
            - industry_name: 行业名称
            - industry_level: 行业级别 (L1/L2)
            - source: 固定为 "csrc"

        Raises:
            SourceFetchError: If fetch fails.

        """
        logger.info(
            "Fetching Tushare CSRC industry",
            event="tushare_csrc_industry_fetch_start",
        )

        with tushare_fetch_error_handler("csrc_industry", "csrc_industrial"):
            response = self._client.query(
                api_name="csrc_industrial",
                fields="industry,industry_name,level,parent_industry",
            )

            if len(response) == 0:
                logger.warning(
                    "No CSRC industries found",
                    event="tushare_csrc_industry_empty",
                )
                return pl.DataFrame(
                    schema={
                        "industry_id": pl.Utf8,
                        "industry_name": pl.Utf8,
                        "industry_level": pl.Utf8,
                        "source": pl.Utf8,
                    }
                )

            # 重命名列并添加 source
            result = response.rename(
                {
                    "industry": "industry_id",
                    "level": "industry_level",
                    "parent_industry": "parent_id",
                }
            )
            result = result.with_columns(
                pl.lit("csrc").alias("source"),
            )

            # 选择最终列
            result = result.select(
                "industry_id",
                "industry_name",
                "industry_level",
                "source",
            )

            row_count = len(result)
            logger.info(
                "Tushare CSRC industry fetched",
                event="tushare_csrc_industry_fetch_complete",
                row_count=row_count,
            )
            _record_metrics(row_count, "csrc_industry")

            return result
