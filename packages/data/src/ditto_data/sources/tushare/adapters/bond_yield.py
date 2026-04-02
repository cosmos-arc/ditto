"""Tushare bond yield curve adapter for Chinese government bonds."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import polars as pl
from ditto_infra.foundation import logger, traced

from ditto_data.sources.schemas.macro_schemas import (
    MACRO_INDICATOR_SOURCE_SCHEMA,
    empty_macro_dataframe,
)
from ditto_data.sources.tushare.adapters.base import BaseTushareAdapter
from ditto_data.sources.tushare.processors.error_handler import (
    tushare_fetch_error_handler,
)


@dataclass(frozen=True)
class CnBondYieldIndicator:
    """中国国债收益率指标定义"""

    code: str  # 统一指标代码，如 CN_BOND_YIELD_1Y
    curve_term: float  # yc_cb 返回的期限值，如 1.0, 2.0, 5.0, 10.0
    name: str  # 中文名称
    maturity: str  # 期限描述
    description: str  # 描述


# 国债收益率指标映射（到期收益率，curve_type=0）
# curve_term 值：1.0=1年, 2.0=2年, 5.0=5年, 10.0=10年
CN_BOND_YIELD_INDICATORS: dict[str, CnBondYieldIndicator] = {
    "CN_BOND_YIELD_1Y": CnBondYieldIndicator(
        code="CN_BOND_YIELD_1Y",
        curve_term=1.0,
        name="中国1年期国债收益率",
        maturity="1年",
        description="中债国债收益率曲线1年期-到期收益率",
    ),
    "CN_BOND_YIELD_2Y": CnBondYieldIndicator(
        code="CN_BOND_YIELD_2Y",
        curve_term=2.0,
        name="中国2年期国债收益率",
        maturity="2年",
        description="中债国债收益率曲线2年期-到期收益率",
    ),
    "CN_BOND_YIELD_5Y": CnBondYieldIndicator(
        code="CN_BOND_YIELD_5Y",
        curve_term=5.0,
        name="中国5年期国债收益率",
        maturity="5年",
        description="中债国债收益率曲线5年期-到期收益率",
    ),
    "CN_BOND_YIELD_10Y": CnBondYieldIndicator(
        code="CN_BOND_YIELD_10Y",
        curve_term=10.0,
        name="中国10年期国债收益率",
        maturity="10年",
        description="中债国债收益率曲线10年期-到期收益率",
    ),
}


def get_cn_bond_yield_indicator(code: str) -> CnBondYieldIndicator | None:
    """Get CN bond yield indicator metadata by code."""
    return CN_BOND_YIELD_INDICATORS.get(code)


# 日期字符串长度常量 (YYYYMMDD)
_DATE_STR_LENGTH = 8


def _parse_trade_date(trade_date: object) -> date | None:
    """
    解析交易日期字符串为 date 对象.

    P2-2 修复：对浮点数进行严格校验，避免脏数据被"合法化"。
    - 浮点数必须是无小数部分的整数值（如 20260101.0）
    - 有小数部分的浮点数（如 20260101.5）会被拒绝
    """
    try:
        # 如果是浮点数，校验是否为整数值
        if isinstance(trade_date, float):
            # 检查是否有小数部分
            if not trade_date.is_integer():
                logger.warning(
                    "Float trade_date has decimal part, rejecting",
                    event="bond_yield_invalid_float_date",
                    trade_date=trade_date,
                )
                return None
            date_val = str(int(trade_date))
        elif isinstance(trade_date, int):
            date_val = str(trade_date)
        else:
            # 字符串处理
            date_str = str(trade_date)
            if len(date_str) == _DATE_STR_LENGTH:
                date_val = date_str
            else:
                return None

        return pl.Series([date_val]).str.to_date(format="%Y%m%d", strict=False)[0]
    except (ValueError, TypeError):
        return None


def _make_indicator_row(
    code: str,
    indicator: CnBondYieldIndicator,
    date_obj: date,
    value: float,
) -> pl.DataFrame:
    """创建单个指标数据行."""
    return pl.DataFrame(
        {
            "indicator_code": [code],
            "indicator_name": [indicator.name],
            "category": ["interest_rate"],
            "frequency": ["daily"],
            "need_pit": [False],
            "date": [date_obj],
            "value": [value],
            "knowledge_date": [date_obj],  # T+0 发布
            "source": ["tushare"],
            "unit": ["%"],
            "description": [indicator.description],
        },
        schema=MACRO_INDICATOR_SOURCE_SCHEMA.schema,
    )


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
            return empty_macro_dataframe()

        compact_start = start_date.replace("-", "")
        compact_end = end_date.replace("-", "")

        # 收集需要的期限值（浮点数）
        curve_terms_needed = [ind.curve_term for _, ind in valid_indicators]

        with tushare_fetch_error_handler("bond_yield", "yc_cb"):
            response = self._client.query(
                api_name="yc_cb",
                fields="ts_code,trade_date,curve_name,curve_type,curve_term,yield",
                ts_code="1001.CB",  # 中债国债收益率曲线
                curve_type="0",  # 0=到期收益率
                start_date=compact_start,
                end_date=compact_end,
            )

            if response.is_empty():
                return empty_macro_dataframe()

            # API 返回长格式：
            # trade_date, ts_code, curve_name, curve_type, curve_term, yield
            # curve_term 可能是字符串或浮点数，需要统一处理
            response = response.with_columns(
                pl.col("curve_term").cast(pl.Float64, strict=False)
            )
            # 过滤出我们需要的期限
            response = response.filter(pl.col("curve_term").is_in(curve_terms_needed))

            if response.is_empty():
                return empty_macro_dataframe()

            # 创建期限到指标的映射
            term_to_indicator = {
                ind.curve_term: (code, ind) for code, ind in valid_indicators
            }

            # 转换为长表格式
            results = self._process_response_rows(response, term_to_indicator)

            if not results:
                return empty_macro_dataframe()

            result = pl.concat(results)

            logger.info(
                "CN bond yield curve fetched",
                event="tushare_bond_yield_fetch_complete",
                row_count=len(result),
            )

            return result

    def _process_response_rows(
        self,
        response: pl.DataFrame,
        term_to_indicator: dict[float, tuple[str, CnBondYieldIndicator]],
    ) -> list[pl.DataFrame]:
        """处理响应数据行，转换为指标 DataFrame 列表."""
        results: list[pl.DataFrame] = []

        for row in response.iter_rows(named=True):
            row_data = self._parse_row(row, term_to_indicator)
            if row_data is not None:
                code, indicator, date_obj, value = row_data
                results.append(_make_indicator_row(code, indicator, date_obj, value))

        return results

    def _parse_curve_term(self, curve_term: object) -> float | None:
        """解析 curve_term 值，返回浮点数或 None."""
        if curve_term is None:
            return None
        if not isinstance(curve_term, (int, float, str, bytes)):
            return None
        try:
            return float(curve_term)
        except (TypeError, ValueError):
            logger.warning(
                "Invalid curve_term value, skipping row",
                event="bond_yield_invalid_curve_term",
                curve_term=curve_term,
            )
            return None

    def _parse_yield_value(self, value: object, trade_date: object) -> float | None:
        """解析 yield 值，返回浮点数或 None."""
        if value is None:
            return None
        if not isinstance(value, (int, float, str, bytes)):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            logger.warning(
                "Invalid yield value, skipping row",
                event="bond_yield_invalid_value",
                value=value,
                trade_date=trade_date,
            )
            return None

    def _parse_row(
        self,
        row: dict[str, object],
        term_to_indicator: dict[float, tuple[str, CnBondYieldIndicator]],
    ) -> tuple[str, CnBondYieldIndicator, date, float] | None:
        """解析单行数据，返回指标信息或 None."""
        curve_term = row.get("curve_term")
        trade_date = row.get("trade_date")
        value = row.get("yield")

        # 解析 curve_term
        term_float = self._parse_curve_term(curve_term)
        if term_float is None:
            return None

        # 查找指标映射
        indicator_data = term_to_indicator.get(term_float)
        if indicator_data is None:
            return None

        code, indicator = indicator_data

        # 检查必要字段
        if trade_date is None:
            return None

        # 解析日期
        date_obj = _parse_trade_date(trade_date)
        if date_obj is None:
            return None

        # 解析 yield 值
        value_float = self._parse_yield_value(value, trade_date)
        if value_float is None:
            return None

        return code, indicator, date_obj, value_float


__all__ = [
    "CN_BOND_YIELD_INDICATORS",
    "BondYieldTushareAdapter",
    "CnBondYieldIndicator",
    "get_cn_bond_yield_indicator",
]
