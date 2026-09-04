"""行业分类适配器实现（申万/证监会）."""

from __future__ import annotations

from datetime import date

import polars as pl
from ditto_platform.foundation import Metrics, logger, traced

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
    rename={"index_code": "source_ticker"},
    date_columns={},
    float_columns=[],
    int_columns=("level",),
    output_columns=("source_ticker", "industry_name", "level"),
)

_SW_INDUSTRY_CONCEPTS_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    "instrument_id": pl.String,
    "industry_id": pl.String,
    "industry_name": pl.String,
    "industry_level": pl.Int32,
    "industry_date": pl.Date,
    "effective_to": pl.Date,
    "knowledge_date": pl.Date,
    "classification_version": pl.String,
    "source": pl.String,
}


def _provider_level(level: int) -> str:
    """Translate the public numeric level to Tushare's L1/L2/L3 contract."""
    if level not in {1, 2, 3}:
        raise ValueError("level must be one of 1, 2, or 3")
    return f"L{level}"


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
                level=_provider_level(level),
                src="SW2021",
                fields="index_code,industry_name,level",
            )

            if response.height > 0:
                response = response.with_columns(
                    pl.col("level").cast(pl.String).str.strip_prefix("L").cast(pl.Int64)
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
        *,
        knowledge_date: date | None = None,
    ) -> pl.DataFrame:
        """
        获取申万行业成分股.

        Args:
            asof_date: 历史查询日期 (YYYY-MM-DD), None 表示最新
            level: 行业级别 (1=一级行业, 2=二级行业, 3=三级行业)
            knowledge_date: Provider payload 的实际获取日期。默认今天；不得用
                ``in_date`` 冒充发布时间。

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

        with tushare_fetch_error_handler("sw_industry_concepts", "index_member_all"):
            provider_level = _provider_level(level).lower()
            classifications = self._client.query(
                api_name="index_classify",
                level=_provider_level(level),
                src="SW2021",
                fields="index_code,industry_name",
            )
            if classifications.height == 0:
                logger.warning(
                    "No SW industry classifications found",
                    event="tushare_sw_industry_concepts_no_classifications",
                )
                return pl.DataFrame(schema=_SW_INDUSTRY_CONCEPTS_SCHEMA)
            member_frames: list[pl.DataFrame] = []
            for industry_code in classifications.get_column("index_code").to_list():
                params = {
                    "api_name": "index_member_all",
                    f"{provider_level}_code": industry_code,
                    "fields": (
                        "l1_code,l1_name,l2_code,l2_name,l3_code,l3_name,"
                        "ts_code,name,in_date,out_date,is_new"
                    ),
                }
                if asof_date is None:
                    params["is_new"] = "Y"
                frame = self._client.query(**params)
                if frame.height > 0:
                    member_frames.append(frame)
            members = (
                pl.concat(member_frames)
                if member_frames
                else pl.DataFrame(schema=_SW_INDUSTRY_CONCEPTS_SCHEMA)
            )

            if not member_frames:
                logger.warning(
                    "No SW industry concepts found",
                    event="tushare_sw_industry_concepts_empty",
                )
                return pl.DataFrame(schema=_SW_INDUSTRY_CONCEPTS_SCHEMA)

            observed_on = knowledge_date or date.today()
            result = members.with_columns(
                pl.col("ts_code").cast(pl.String).alias("instrument_id"),
                pl.col(f"{provider_level}_code").cast(pl.String).alias("industry_id"),
                pl.col(f"{provider_level}_name").cast(pl.String).alias("industry_name"),
                pl.lit(level, dtype=pl.Int32).alias("industry_level"),
                pl.col("in_date")
                .cast(pl.String)
                .str.to_date("%Y%m%d", strict=False)
                .alias("industry_date"),
                pl.col("out_date")
                .cast(pl.String)
                .str.to_date("%Y%m%d", strict=False)
                .alias("effective_to"),
                pl.lit(observed_on).alias("knowledge_date"),
                pl.lit("SW2021").alias("classification_version"),
                pl.lit("sw").alias("source"),
            )
            result = result.filter(
                pl.col("instrument_id").is_not_null()
                & pl.col("instrument_id").str.contains(r"^\d{6}\.(?:SH|SZ|BJ)$")
                & pl.col("industry_id").is_not_null()
                & pl.col("industry_date").is_not_null()
            )
            if asof_date is not None:
                asof = date.fromisoformat(asof_date)
                result = result.filter(
                    (pl.col("industry_date") <= asof)
                    & (
                        pl.col("effective_to").is_null()
                        | (pl.col("effective_to") > asof)
                    )
                )
            result = result.select(*_SW_INDUSTRY_CONCEPTS_SCHEMA)

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
