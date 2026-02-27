"""Tushare bond yield curve adapter for Chinese government bonds."""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl
from ditto_infra.foundation import logger, traced

from ditto_datahub.sources.schemas.macro_schemas import MACRO_INDICATOR_SOURCE_SCHEMA
from ditto_datahub.sources.tushare.adapters.base import BaseTushareAdapter
from ditto_datahub.sources.tushare.processors.error_handler import (
    tushare_fetch_error_handler,
)


@dataclass(frozen=True)
class CnBondYieldIndicator:
    """中国国债收益率指标定义"""

    code: str  # 统一指标代码，如 CN_BOND_YIELD_1Y
    field: str  # yc_cb 返回的字段名，如 y1
    name: str  # 中文名称
    maturity: str  # 期限描述
    description: str  # 描述


# 国债收益率指标映射（到期收益率，curve_type=0）
CN_BOND_YIELD_INDICATORS: dict[str, CnBondYieldIndicator] = {
    "CN_BOND_YIELD_1Y": CnBondYieldIndicator(
        code="CN_BOND_YIELD_1Y",
        field="y1",
        name="中国1年期国债收益率",
        maturity="1年",
        description="中债国债收益率曲线1年期-到期收益率",
    ),
    "CN_BOND_YIELD_2Y": CnBondYieldIndicator(
        code="CN_BOND_YIELD_2Y",
        field="y2",
        name="中国2年期国债收益率",
        maturity="2年",
        description="中债国债收益率曲线2年期-到期收益率",
    ),
    "CN_BOND_YIELD_5Y": CnBondYieldIndicator(
        code="CN_BOND_YIELD_5Y",
        field="y5",
        name="中国5年期国债收益率",
        maturity="5年",
        description="中债国债收益率曲线5年期-到期收益率",
    ),
    "CN_BOND_YIELD_10Y": CnBondYieldIndicator(
        code="CN_BOND_YIELD_10Y",
        field="y10",
        name="中国10年期国债收益率",
        maturity="10年",
        description="中债国债收益率曲线10年期-到期收益率",
    ),
}


def get_cn_bond_yield_indicator(code: str) -> CnBondYieldIndicator | None:
    """Get CN bond yield indicator metadata by code."""
    return CN_BOND_YIELD_INDICATORS.get(code)


def _empty_macro_dataframe() -> pl.DataFrame:
    """Return empty DataFrame with MACRO_INDICATOR_SOURCE_SCHEMA."""
    return pl.DataFrame(schema=MACRO_INDICATOR_SOURCE_SCHEMA.schema)


class BondYieldTushareAdapter(BaseTushareAdapter):
    """Tushare 国债收益率曲线适配器"""

    @traced("source.tushare.fetch_bond_yield")
    def fetch_bond_yield(
        self,
        codes: list[str],
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        """
        获取中国国债收益率曲线数据

        Args:
            codes: 指标代码列表（如 ["CN_BOND_YIELD_1Y", "CN_BOND_YIELD_10Y"]）
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)

        Returns:
            DataFrame with MACRO_INDICATOR_SOURCE_SCHEMA columns

        """
        logger.info(
            "Fetching CN bond yield curve",
            event="tushare_bond_yield_fetch_start",
            codes=codes,
            start_date=start_date,
            end_date=end_date,
        )

        # 过滤有效的指标代码
        valid_indicators = [
            (code, CN_BOND_YIELD_INDICATORS[code])
            for code in codes
            if code in CN_BOND_YIELD_INDICATORS
        ]

        if not valid_indicators:
            return _empty_macro_dataframe()

        compact_start = start_date.replace("-", "")
        compact_end = end_date.replace("-", "")

        # 收集需要的字段
        fields_needed = ["ts_code", "trade_date", "curve_type"]
        fields_needed.extend(ind.field for _, ind in valid_indicators)
        fields_str = ",".join(dict.fromkeys(fields_needed))  # 去重保持顺序

        with tushare_fetch_error_handler("bond_yield", "yc_cb"):
            response = self._client.query(
                api_name="yc_cb",
                fields=fields_str,
                ts_code="1001.CB",  # 中债国债收益率曲线
                curve_type="0",  # 0=到期收益率
                start_date=compact_start,
                end_date=compact_end,
            )

            if response.is_empty():
                return _empty_macro_dataframe()

            # 转换为长表格式
            results: list[pl.DataFrame] = []
            for code, indicator in valid_indicators:
                if indicator.field not in response.columns:
                    continue

                df = response.select(
                    pl.col("trade_date"),
                    pl.col(indicator.field).alias("value"),
                ).filter(pl.col("value").is_not_null())

                if df.is_empty():
                    continue

                # 转换日期和添加元数据
                df = df.with_columns(
                    pl.col("trade_date")
                    .cast(pl.String)
                    .str.to_date(format="%Y%m%d", strict=False)
                    .alias("date"),
                ).filter(pl.col("date").is_not_null())

                df = df.with_columns(
                    pl.lit(code).alias("indicator_code"),
                    pl.lit(indicator.name).alias("indicator_name"),
                    pl.lit("interest_rate").alias("category"),
                    pl.lit("daily").alias("frequency"),
                    pl.lit(False).alias("need_pit"),
                    pl.col("date").alias("knowledge_date"),  # T+0 发布
                    pl.lit("tushare").alias("source"),
                    pl.lit("%").alias("unit"),
                    pl.lit(indicator.description).alias("description"),
                ).select(
                    "indicator_code",
                    "indicator_name",
                    "category",
                    "frequency",
                    "need_pit",
                    "date",
                    "value",
                    "knowledge_date",
                    "source",
                    "unit",
                    "description",
                )

                results.append(df)

            if not results:
                return _empty_macro_dataframe()

            result = pl.concat(results)

            logger.info(
                "CN bond yield curve fetched",
                event="tushare_bond_yield_fetch_complete",
                row_count=len(result),
            )

            return result


__all__ = [
    "CN_BOND_YIELD_INDICATORS",
    "BondYieldTushareAdapter",
    "CnBondYieldIndicator",
    "get_cn_bond_yield_indicator",
]
