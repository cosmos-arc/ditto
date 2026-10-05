"""Tushare macro indicator metadata definitions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class TushareMacroIndicator:
    """
    Tushare macro indicator metadata.

    Attributes:
        api_name: Tushare API name (e.g., "cn_gdp", "cn_cpi").
        code: Unified indicator code (e.g., "CN_GDP_YOY").
        field: Field name in API response (e.g., "gdp_yoy", "nt_yoy").
        name: Chinese name.
        category: Indicator category.
        frequency: Data frequency.
        unit: Unit of measurement.
        description: Indicator description.
        need_pit: Whether PIT tracking is needed.
        release_lag_days: Estimated days after period end before data is released.
        date_field: Optional provider-specific date column override.
        range_params: (start_param, end_param) request-parameter names for the
            endpoint's window contract. Values are derived from frequency:
            date (YYYYMMDD), month (YYYYMM) or quarter (YYYYQq). Default is
            the daily start_date/end_date contract.

    """

    api_name: str
    code: str
    field: str
    name: str
    category: Literal[
        "economic",
        "prices",
        "money_supply",
        "employment",
        "credit",
        "survey",
        "interest_rate",  # 新增
    ]
    frequency: Literal["daily", "monthly", "quarterly"]
    unit: str
    description: str
    need_pit: bool = False
    release_lag_days: int = 0
    date_field: str | None = None
    range_params: tuple[str, str] = ("start_date", "end_date")


# 月度窗口参数合同（YYYYMM）：cn_cpi/cn_ppi/cn_m/sf_month 专页要求
# start_m/end_m；发送 start_date 会被代理忽略并返回未声明的全历史
# （2026-10-05 实测：cn_cpi 2025 窗口发 start_date 返回 512 行全历史）。
_MONTHLY_RANGE_PARAMS = ("start_m", "end_m")


# Tushare macro indicator registry
TUSHARE_MACRO_INDICATORS: dict[str, TushareMacroIndicator] = {
    # === Economic ===
    "CN_GDP_YOY": TushareMacroIndicator(
        api_name="cn_gdp",
        code="CN_GDP_YOY",
        field="gdp_yoy",
        name="GDP同比",
        category="economic",
        frequency="quarterly",
        unit="%",
        description="国内生产总值同比增长率",
        need_pit=True,
        release_lag_days=15,  # 季度后约15天发布
        range_params=("start_q", "end_q"),
    ),
    # === Prices ===
    "CN_CPI_YOY": TushareMacroIndicator(
        api_name="cn_cpi",
        code="CN_CPI_YOY",
        field="nt_yoy",
        name="CPI同比",
        category="prices",
        frequency="monthly",
        unit="%",
        description="居民消费价格指数同比增长率",
        need_pit=True,
        release_lag_days=10,  # 月度后约10天发布
        range_params=_MONTHLY_RANGE_PARAMS,
    ),
    "CN_PPI_YOY": TushareMacroIndicator(
        api_name="cn_ppi",
        code="CN_PPI_YOY",
        field="ppi_yoy",
        name="PPI同比",
        category="prices",
        frequency="monthly",
        unit="%",
        description="工业生产者出厂价格指数同比增长率",
        need_pit=True,
        release_lag_days=10,
        range_params=_MONTHLY_RANGE_PARAMS,
    ),
    # === Survey ===
    # 注意：2026-10-05 实测代理对 cn_pmi 任何参数形态（month/start_m/
    # start_date/无参数）均返回空——端点可达但当前无数据，作为已知边界记录。
    "CN_PMI_MFG": TushareMacroIndicator(
        api_name="cn_pmi",
        code="CN_PMI_MFG",
        field="PMI010000",
        name="制造业PMI",
        category="survey",
        frequency="monthly",
        unit="指数",
        description="制造业采购经理人指数",
        need_pit=True,
        release_lag_days=1,  # 月初发布
        date_field="MONTH",
        range_params=_MONTHLY_RANGE_PARAMS,
    ),
    # === Money Supply ===
    "CN_M2_YOY": TushareMacroIndicator(
        api_name="cn_m",
        code="CN_M2_YOY",
        field="m2_yoy",
        name="M2同比",
        category="money_supply",
        frequency="monthly",
        unit="%",
        description="广义货币供应量同比增长率",
        need_pit=True,
        release_lag_days=12,
        range_params=_MONTHLY_RANGE_PARAMS,
    ),
    "CN_M1_YOY": TushareMacroIndicator(
        api_name="cn_m",
        code="CN_M1_YOY",
        field="m1_yoy",
        name="M1同比",
        category="money_supply",
        frequency="monthly",
        unit="%",
        description="狭义货币供应量同比增长率",
        need_pit=True,
        release_lag_days=12,
        range_params=_MONTHLY_RANGE_PARAMS,
    ),
    "CN_M0_YOY": TushareMacroIndicator(
        api_name="cn_m",
        code="CN_M0_YOY",
        field="m0_yoy",
        name="M0同比",
        category="money_supply",
        frequency="monthly",
        unit="%",
        description="流通中现金同比增长率",
        need_pit=True,
        release_lag_days=12,
        range_params=_MONTHLY_RANGE_PARAMS,
    ),
    # === Social Financing（社融，sf_month doc_id=310）===
    # 字段级单位不同：增量当月/累计为亿元，存量为万亿元（#434）。
    # 2026-10-05 实测样本：inc_month=25660（亿元）、stk_endval=433.65（万亿元）。
    "CN_SF_FLOW_MONTH": TushareMacroIndicator(
        api_name="sf_month",
        code="CN_SF_FLOW_MONTH",
        field="inc_month",
        name="社融增量当月值",
        category="credit",
        frequency="monthly",
        unit="亿元",
        description="社会融资规模增量当月值",
        need_pit=True,
        release_lag_days=12,
        range_params=_MONTHLY_RANGE_PARAMS,
    ),
    "CN_SF_FLOW_CUM": TushareMacroIndicator(
        api_name="sf_month",
        code="CN_SF_FLOW_CUM",
        field="inc_cumval",
        name="社融增量累计值",
        category="credit",
        frequency="monthly",
        unit="亿元",
        description="社会融资规模增量累计值(年初至当月)",
        need_pit=True,
        release_lag_days=12,
        range_params=_MONTHLY_RANGE_PARAMS,
    ),
    "CN_SF_STOCK": TushareMacroIndicator(
        api_name="sf_month",
        code="CN_SF_STOCK",
        field="stk_endval",
        name="社融存量",
        category="credit",
        frequency="monthly",
        unit="万亿元",
        description="社会融资规模存量(期末值)",
        need_pit=True,
        release_lag_days=12,
        range_params=_MONTHLY_RANGE_PARAMS,
    ),
    # === Credit ===
    "CN_CREDIT_TS": TushareMacroIndicator(
        api_name="shibor",
        code="CN_CREDIT_TS",
        field="on",
        name="隔夜Shibor",
        category="credit",
        frequency="daily",
        unit="%",
        description="上海银行间同业拆放利率隔夜",
        need_pit=False,
        release_lag_days=0,  # 当日发布
    ),
    # === Interest Rate (Shibor 全期限) ===
    "CN_SHIBOR_ON": TushareMacroIndicator(
        api_name="shibor",
        code="CN_SHIBOR_ON",
        field="on",
        name="隔夜Shibor",
        category="interest_rate",
        frequency="daily",
        unit="%",
        description="上海银行间同业拆放利率隔夜",
        need_pit=False,
        release_lag_days=0,
    ),
    "CN_SHIBOR_1W": TushareMacroIndicator(
        api_name="shibor",
        code="CN_SHIBOR_1W",
        field="1w",
        name="1周Shibor",
        category="interest_rate",
        frequency="daily",
        unit="%",
        description="上海银行间同业拆放利率1周",
        need_pit=False,
        release_lag_days=0,
    ),
    "CN_SHIBOR_2W": TushareMacroIndicator(
        api_name="shibor",
        code="CN_SHIBOR_2W",
        field="2w",
        name="2周Shibor",
        category="interest_rate",
        frequency="daily",
        unit="%",
        description="上海银行间同业拆放利率2周",
        need_pit=False,
        release_lag_days=0,
    ),
    "CN_SHIBOR_1M": TushareMacroIndicator(
        api_name="shibor",
        code="CN_SHIBOR_1M",
        field="1m",
        name="1个月Shibor",
        category="interest_rate",
        frequency="daily",
        unit="%",
        description="上海银行间同业拆放利率1个月",
        need_pit=False,
        release_lag_days=0,
    ),
    "CN_SHIBOR_3M": TushareMacroIndicator(
        api_name="shibor",
        code="CN_SHIBOR_3M",
        field="3m",
        name="3个月Shibor",
        category="interest_rate",
        frequency="daily",
        unit="%",
        description="上海银行间同业拆放利率3个月",
        need_pit=False,
        release_lag_days=0,
    ),
    "CN_SHIBOR_6M": TushareMacroIndicator(
        api_name="shibor",
        code="CN_SHIBOR_6M",
        field="6m",
        name="6个月Shibor",
        category="interest_rate",
        frequency="daily",
        unit="%",
        description="上海银行间同业拆放利率6个月",
        need_pit=False,
        release_lag_days=0,
    ),
    "CN_SHIBOR_9M": TushareMacroIndicator(
        api_name="shibor",
        code="CN_SHIBOR_9M",
        field="9m",
        name="9个月Shibor",
        category="interest_rate",
        frequency="daily",
        unit="%",
        description="上海银行间同业拆放利率9个月",
        need_pit=False,
        release_lag_days=0,
    ),
    "CN_SHIBOR_1Y": TushareMacroIndicator(
        api_name="shibor",
        code="CN_SHIBOR_1Y",
        field="1y",
        name="1年Shibor",
        category="interest_rate",
        frequency="daily",
        unit="%",
        description="上海银行间同业拆放利率1年",
        need_pit=False,
        release_lag_days=0,
    ),
    # === LPR ===
    "CN_LPR_1Y": TushareMacroIndicator(
        api_name="shibor_lpr",
        code="CN_LPR_1Y",
        field="lpr_1y",
        name="1年期LPR",
        category="interest_rate",
        frequency="monthly",
        unit="%",
        description="贷款市场报价利率1年期",
        need_pit=False,
        release_lag_days=0,
    ),
    "CN_LPR_5Y": TushareMacroIndicator(
        api_name="shibor_lpr",
        code="CN_LPR_5Y",
        field="lpr_5y",
        name="5年期LPR",
        category="interest_rate",
        frequency="monthly",
        unit="%",
        description="贷款市场报价利率5年期",
        need_pit=False,
        release_lag_days=0,
    ),
    # === Libor ===
    "CN_LIBOR_USD": TushareMacroIndicator(
        api_name="libor",
        code="CN_LIBOR_USD",
        field="usd",
        name="美元Libor",
        category="interest_rate",
        frequency="daily",
        unit="%",
        description="伦敦银行间同业拆放利率美元",
        need_pit=False,
        release_lag_days=0,
    ),
    # === Hibor ===
    "CN_HIBOR_ON": TushareMacroIndicator(
        api_name="hibor",
        code="CN_HIBOR_ON",
        field="on",
        name="隔夜Hibor",
        category="interest_rate",
        frequency="daily",
        unit="%",
        description="香港银行间同业拆放利率隔夜",
        need_pit=False,
        release_lag_days=0,
    ),
}


def get_tushare_macro_indicator(code: str) -> TushareMacroIndicator | None:
    """
    Get Tushare macro indicator metadata by code.

    Args:
        code: Unified indicator code (e.g., "CN_GDP_YOY").

    Returns:
        TushareMacroIndicator if found, None otherwise.

    """
    return TUSHARE_MACRO_INDICATORS.get(code)


def list_tushare_macro_indicators(
    api_name: str | None = None,
    category: str | None = None,
    frequency: str | None = None,
) -> list[TushareMacroIndicator]:
    """
    List Tushare macro indicators with optional filtering.

    Args:
        api_name: Filter by Tushare API name (optional).
        category: Filter by category (optional).
        frequency: Filter by frequency (optional).

    Returns:
        List of matching TushareMacroIndicator objects.

    """
    result = list(TUSHARE_MACRO_INDICATORS.values())
    if api_name:
        result = [i for i in result if i.api_name == api_name]
    if category:
        result = [i for i in result if i.category == category]
    if frequency:
        result = [i for i in result if i.frequency == frequency]
    return result


__all__ = [
    "TUSHARE_MACRO_INDICATORS",
    "TushareMacroIndicator",
    "get_tushare_macro_indicator",
    "list_tushare_macro_indicators",
]
