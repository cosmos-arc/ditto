"""FRED macro indicator metadata definitions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# Type aliases for clarity
CategoryType = Literal[
    "economic",
    "prices",
    "money_supply",
    "employment",
    "credit",
    "survey",
    "interest_rate",
    "commodity",
    "vix",
    "dollar_index",
    "exchange_rate",
]
FrequencyType = Literal["daily", "weekly", "monthly", "quarterly"]


@dataclass(frozen=True)
class FredIndicator:
    """
    FRED indicator metadata.

    Attributes:
        series_id: FRED Series ID (e.g., "UNRATE", "GDP").
        code: Unified indicator code (e.g., "US_UNRATE").
        name: Chinese name.
        category: Indicator category.
        frequency: Data frequency.
        unit: Unit of measurement.
        description: Description.
        need_pit: Whether PIT tracking is needed.

    """

    series_id: str
    code: str
    name: str
    category: CategoryType
    frequency: FrequencyType
    unit: str
    description: str
    need_pit: bool = False


# FRED indicator registry
#
# 注册纪律（#432，2026-10-04 核查）：
# - 死序列不注册：GOLDAMGBD228NLBM/SLVPRUSD（FRED 2022-01 官方公告移除
#   IBA/LBMA 定盘数据）与 VIX9D（序列页访问失败 + 前轮 404 记录；工具
#   访问错误不等同官方下架，恢复可读后再评估）。金银参考已由 Tushare
#   fx_daily 的 FXCM XAU/XAG bid 承担，与历史 LBMA 定盘是不同基准，
#   身份见 tushare/adapters/metal.py。
# - 代码与口径一致：注册拉取的是原始序列（level/index）时，代码/名称/
#   单位不得承诺同比。展示 YoY 须显式派生（同一 vintage 宇宙内当前值与
#   12 个月前值）或固定 FRED 官方变换 pc1 并锁定请求身份；不得把 pch
#   当同比，也不得对已变换序列重复变换。当前无 YoY 消费者，不预置派生。
# - need_pit 不等于无发布滞后：UNRATE 月度发布并回改、M2 季调且年度
#   基准重算可达数年，均需修订管理（need_pit=True）。
FRED_INDICATORS: dict[str, FredIndicator] = {
    # === Economic ===
    "US_GDP_QOQ": FredIndicator(
        series_id="A191RL1Q225SBEA",
        code="US_GDP_QOQ",
        name="美国GDP环比",
        category="economic",
        frequency="quarterly",
        unit="%",
        description=(
            "Real GDP, Percent Change from Preceding Period, "
            "Seasonally Adjusted Annual Rate"
        ),
        need_pit=True,
    ),
    # === Prices（原始序列为季调指数 level，非同比） ===
    "US_CPI_INDEX": FredIndicator(
        series_id="CPIAUCSL",
        code="US_CPI_INDEX",
        name="美国CPI(季调指数)",
        category="prices",
        frequency="monthly",
        unit="指数(1982-84=100)",
        description=(
            "CPI for All Urban Consumers: All Items, "
            "Seasonally Adjusted Index (level, not YoY)"
        ),
        need_pit=True,
    ),
    "US_CORE_CPI_INDEX": FredIndicator(
        series_id="CPILFESL",
        code="US_CORE_CPI_INDEX",
        name="美国核心CPI(季调指数)",
        category="prices",
        frequency="monthly",
        unit="指数(1982-84=100)",
        description=(
            "Core CPI (Excluding Food and Energy), "
            "Seasonally Adjusted Index (level, not YoY)"
        ),
        need_pit=True,
    ),
    "US_PCE_INDEX": FredIndicator(
        series_id="PCEPI",
        code="US_PCE_INDEX",
        name="美国PCE物价指数(季调)",
        category="prices",
        frequency="monthly",
        unit="指数(2017=100)",
        description=(
            "Personal Consumption Expenditures Price Index, "
            "Seasonally Adjusted (level, not YoY)"
        ),
        need_pit=True,
    ),
    "US_CORE_PCE_INDEX": FredIndicator(
        series_id="PCEPILFE",
        code="US_CORE_PCE_INDEX",
        name="美国核心PCE物价指数(季调)",
        category="prices",
        frequency="monthly",
        unit="指数(2017=100)",
        description=(
            "Core PCE (Excluding Food and Energy), Seasonally Adjusted (level, not YoY)"
        ),
        need_pit=True,
    ),
    # === Employment ===
    "US_UNRATE": FredIndicator(
        series_id="UNRATE",
        code="US_UNRATE",
        name="美国失业率",
        category="employment",
        frequency="monthly",
        unit="%",
        description="Civilian Unemployment Rate (monthly release, revised)",
        need_pit=True,
    ),
    "US_PAYEMS": FredIndicator(
        series_id="PAYEMS",
        code="US_PAYEMS",
        name="美国非农就业",
        category="employment",
        frequency="monthly",
        unit="千人",
        description="Nonfarm Employment",
        need_pit=True,
    ),
    # === Money Supply（M2SL 为季调存量 level，非同比） ===
    "US_M2": FredIndicator(
        series_id="M2SL",
        code="US_M2",
        name="美国M2货币供应(季调)",
        category="money_supply",
        frequency="monthly",
        unit="十亿美元",
        description=(
            "M2 Money Stock, Seasonally Adjusted (level, not YoY; "
            "annual benchmark revisions can reach back years)"
        ),
        need_pit=True,
    ),
    # === Interest Rate (Market Domain) ===
    "US_BOND_YIELD_1Y": FredIndicator(
        series_id="DGS1",
        code="US_BOND_YIELD_1Y",
        name="美国1年期国债收益率",
        category="interest_rate",
        frequency="daily",
        unit="%",
        description="1-Year Treasury Constant Maturity Rate",
        need_pit=False,
    ),
    "US_BOND_YIELD_2Y": FredIndicator(
        series_id="DGS2",
        code="US_BOND_YIELD_2Y",
        name="美国2年期国债收益率",
        category="interest_rate",
        frequency="daily",
        unit="%",
        description="2-Year Treasury Constant Maturity Rate",
        need_pit=False,
    ),
    "US_BOND_YIELD_5Y": FredIndicator(
        series_id="DGS5",
        code="US_BOND_YIELD_5Y",
        name="美国5年期国债收益率",
        category="interest_rate",
        frequency="daily",
        unit="%",
        description="5-Year Treasury Constant Maturity Rate",
        need_pit=False,
    ),
    "US_BOND_YIELD_10Y": FredIndicator(
        series_id="DGS10",
        code="US_BOND_YIELD_10Y",
        name="美国10年期国债收益率",
        category="interest_rate",
        frequency="daily",
        unit="%",
        description="10-Year Treasury Constant Maturity Rate",
        need_pit=False,
    ),
    "US_BOND_YIELD_30Y": FredIndicator(
        series_id="DGS30",
        code="US_BOND_YIELD_30Y",
        name="美国30年期国债收益率",
        category="interest_rate",
        frequency="daily",
        unit="%",
        description="30-Year Treasury Constant Maturity Rate",
        need_pit=False,
    ),
    "US_BOND_SPREAD_10Y2Y": FredIndicator(
        series_id="T10Y2Y",
        code="US_BOND_SPREAD_10Y2Y",
        name="美国10Y-2Y国债利差",
        category="interest_rate",
        frequency="daily",
        unit="%",
        description="10-Year Treasury Minus 2-Year Treasury",
        need_pit=False,
    ),
    "US_FEDFUNDS_M": FredIndicator(
        series_id="FEDFUNDS",
        code="US_FEDFUNDS_M",
        name="美国联邦基金利率(月)",
        category="interest_rate",
        frequency="monthly",
        unit="%",
        description="Effective Federal Funds Rate (Monthly)",
        need_pit=False,
    ),
    "US_FEDFUNDS_D": FredIndicator(
        series_id="DFF",
        code="US_FEDFUNDS_D",
        name="美国联邦基金利率(日)",
        category="interest_rate",
        frequency="daily",
        unit="%",
        description="Effective Federal Funds Rate (Daily)",
        need_pit=False,
    ),
    # === Commodity (Market Domain) ===
    # 贵金属（金银）不在此注册：GOLDAMGBD228NLBM/SLVPRUSD 已死序列（见
    # 文件头核查依据）；金银参考值由 Tushare fx_daily FXCM bid 提供（身份
    # 见 tushare/adapters/metal.py），与历史 LBMA 定盘分属不同基准。
    "COMMOD_WTI": FredIndicator(
        series_id="DCOILWTICO",
        code="COMMOD_WTI",
        name="WTI原油",
        category="commodity",
        frequency="daily",
        unit="美元/桶",
        description="Crude Oil Prices: West Texas Intermediate (WTI)",
        need_pit=False,
    ),
    "COMMOD_BRENT": FredIndicator(
        series_id="DCOILBRENTEU",
        code="COMMOD_BRENT",
        name="布伦特原油",
        category="commodity",
        frequency="daily",
        unit="美元/桶",
        description="Crude Oil Prices: Brent - Europe",
        need_pit=False,
    ),
    # === VIX (Market Domain) ===
    # VIX9D 不注册：序列页访问失败 + 前轮 404（见文件头核查依据）。
    "VIX_30D": FredIndicator(
        series_id="VIXCLS",
        code="VIX_30D",
        name="VIX波动率指数(30天)",
        category="vix",
        frequency="daily",
        unit="指数",
        description="CBOE Volatility Index (VIX)",
        need_pit=False,
    ),
    # === Dollar Index (Market Domain) ===
    "US_DOLLAR_INDEX_BROAD": FredIndicator(
        series_id="DTWEXBGS",
        code="US_DOLLAR_INDEX_BROAD",
        name="美国贸易加权美元指数(广义)",
        category="dollar_index",
        frequency="daily",
        unit="指数",
        description=(
            "Trade Weighted U.S. Dollar Index: Broad, Goods and Services "
            "(Federal Reserve Board H.10 release)"
        ),
        need_pit=False,
    ),
    "US_DOLLAR_INDEX_AFE_GOODS": FredIndicator(
        series_id="DTWEXAFEGS",
        code="US_DOLLAR_INDEX_AFE_GOODS",
        name="美元指数(发达经济体·商品)",
        category="dollar_index",
        frequency="daily",
        unit="指数",
        description=(
            "Trade Weighted U.S. Dollar Index: Advanced Foreign Economies, "
            "Goods (Federal Reserve Board H.10)"
        ),
        need_pit=False,
    ),
    # === Exchange Rate（H.10；与 Tushare fx_daily 的 FXCM 口径分属不同
    # 身份，存于宏观长表，不静默合并同一序列；H.10 周一发布上周值）===
    "FX_JPYUSD_H10": FredIndicator(
        series_id="DEXJPUS",
        code="FX_JPYUSD_H10",
        name="日元兑美元(H.10)",
        category="exchange_rate",
        frequency="daily",
        unit="日元/美元",
        description=(
            "Japanese Yen to U.S. Dollar Spot Exchange Rate "
            "(H.10 noon buying rate; not the Tushare fx_daily series)"
        ),
        need_pit=False,
    ),
    "FX_EURUSD_H10": FredIndicator(
        series_id="DEXUSEU",
        code="FX_EURUSD_H10",
        name="欧元兑美元(H.10)",
        category="exchange_rate",
        frequency="daily",
        unit="美元/欧元",
        description=("U.S. Dollars to Euro Spot Exchange Rate (H.10 noon buying rate)"),
        need_pit=False,
    ),
    "FX_USDCNY_H10": FredIndicator(
        series_id="DEXCHUS",
        code="FX_USDCNY_H10",
        name="人民币兑美元(H.10)",
        category="exchange_rate",
        frequency="daily",
        unit="人民币/美元",
        description=(
            "China Yuan to U.S. Dollar Spot Exchange Rate (H.10 noon buying rate)"
        ),
        need_pit=False,
    ),
    "FX_GBPUSD_H10": FredIndicator(
        series_id="DEXUSUK",
        code="FX_GBPUSD_H10",
        name="英镑兑美元(H.10)",
        category="exchange_rate",
        frequency="daily",
        unit="美元/英镑",
        description=(
            "U.S. Dollars to British Pound Spot Exchange Rate (H.10 noon buying rate)"
        ),
        need_pit=False,
    ),
    # === Interest Rate 扩充（#437 候选全集） ===
    "US_BOND_YIELD_1MO": FredIndicator(
        series_id="DGS1MO",
        code="US_BOND_YIELD_1MO",
        name="美国1个月期国债收益率",
        category="interest_rate",
        frequency="daily",
        unit="%",
        description="1-Month Treasury Constant Maturity Rate",
        need_pit=False,
    ),
    "US_BOND_YIELD_3MO": FredIndicator(
        series_id="DGS3MO",
        code="US_BOND_YIELD_3MO",
        name="美国3个月期国债收益率",
        category="interest_rate",
        frequency="daily",
        unit="%",
        description="3-Month Treasury Constant Maturity Rate",
        need_pit=False,
    ),
    "US_BOND_YIELD_3Y": FredIndicator(
        series_id="DGS3",
        code="US_BOND_YIELD_3Y",
        name="美国3年期国债收益率",
        category="interest_rate",
        frequency="daily",
        unit="%",
        description="3-Year Treasury Constant Maturity Rate",
        need_pit=False,
    ),
    "US_BOND_YIELD_7Y": FredIndicator(
        series_id="DGS7",
        code="US_BOND_YIELD_7Y",
        name="美国7年期国债收益率",
        category="interest_rate",
        frequency="daily",
        unit="%",
        description="7-Year Treasury Constant Maturity Rate",
        need_pit=False,
    ),
    "US_BOND_YIELD_20Y": FredIndicator(
        series_id="DGS20",
        code="US_BOND_YIELD_20Y",
        name="美国20年期国债收益率",
        category="interest_rate",
        frequency="daily",
        unit="%",
        description=(
            "20-Year Treasury Constant Maturity Rate (1987-1993 停发段缺失为源覆盖边界)"
        ),
        need_pit=False,
    ),
    "US_BOND_SPREAD_10Y3M": FredIndicator(
        series_id="T10Y3M",
        code="US_BOND_SPREAD_10Y3M",
        name="美国10Y-3M国债利差",
        category="interest_rate",
        frequency="daily",
        unit="%",
        description="10-Year Treasury Minus 3-Month Treasury",
        need_pit=False,
    ),
    "US_BREAKEVEN_10Y": FredIndicator(
        series_id="T10YIE",
        code="US_BREAKEVEN_10Y",
        name="美国10年期盈亏平衡通胀",
        category="interest_rate",
        frequency="daily",
        unit="%",
        description="10-Year Breakeven Inflation Rate",
        need_pit=False,
    ),
    "US_BREAKEVEN_5Y": FredIndicator(
        series_id="T5YIE",
        code="US_BREAKEVEN_5Y",
        name="美国5年期盈亏平衡通胀",
        category="interest_rate",
        frequency="daily",
        unit="%",
        description="5-Year Breakeven Inflation Rate",
        need_pit=False,
    ),
    "US_SOFR": FredIndicator(
        series_id="SOFR",
        code="US_SOFR",
        name="SOFR担保隔夜融资利率",
        category="interest_rate",
        frequency="daily",
        unit="%",
        description="Secured Overnight Financing Rate (NY Fed)",
        need_pit=False,
    ),
    "US_EFFR": FredIndicator(
        series_id="EFFR",
        code="US_EFFR",
        name="有效联邦基金利率(EFFR)",
        category="interest_rate",
        frequency="daily",
        unit="%",
        description=("Effective Federal Funds Rate (NY Fed daily; 与 DFF 是不同序列)"),
        need_pit=False,
    ),
    # === Credit（ICE 序列 2026-04 起仅滚动 3 年窗口，历史深度受限） ===
    "US_CREDIT_IG_OAS": FredIndicator(
        series_id="BAMLC0A0CM",
        code="US_CREDIT_IG_OAS",
        name="美国投资级公司债利差OAS",
        category="credit",
        frequency="daily",
        unit="%",
        description=(
            "ICE BofA US Corporate Index Option-Adjusted Spread "
            "(ICE 自 2026-04 仅提供滚动 3 年窗口)"
        ),
        need_pit=False,
    ),
    "US_CREDIT_HY_OAS": FredIndicator(
        series_id="BAMLH0A0HYM2",
        code="US_CREDIT_HY_OAS",
        name="美国高收益公司债利差OAS",
        category="credit",
        frequency="daily",
        unit="%",
        description=(
            "ICE BofA US High Yield Index Option-Adjusted Spread "
            "(ICE 自 2026-04 仅提供滚动 3 年窗口)"
        ),
        need_pit=False,
    ),
    "US_CORP_YIELD_AAA": FredIndicator(
        series_id="DAAA",
        code="US_CORP_YIELD_AAA",
        name="Moody's AAA公司债收益率",
        category="credit",
        frequency="daily",
        unit="%",
        description="Moody's Seasoned Aaa Corporate Bond Yield",
        need_pit=False,
    ),
    "US_CORP_YIELD_BAA_D": FredIndicator(
        series_id="DBAA",
        code="US_CORP_YIELD_BAA_D",
        name="Moody's Baa公司债收益率(日)",
        category="credit",
        frequency="daily",
        unit="%",
        description="Moody's Seasoned Baa Corporate Bond Yield (daily)",
        need_pit=False,
    ),
    "US_CORP_YIELD_BAA_M": FredIndicator(
        series_id="BAA",
        code="US_CORP_YIELD_BAA_M",
        name="Moody's Baa公司债收益率(月)",
        category="credit",
        frequency="monthly",
        unit="%",
        description="Moody's Seasoned Baa Corporate Bond Yield (monthly only)",
        need_pit=False,
    ),
    "US_BOND_SPREAD_BAA10Y": FredIndicator(
        series_id="BAA10Y",
        code="US_BOND_SPREAD_BAA10Y",
        name="Baa公司债-10年期国债利差",
        category="credit",
        frequency="daily",
        unit="%",
        description=(
            "Moody's Seasoned Baa Corporate Bond Yield Relative to "
            "Yield on 10-Year Treasury"
        ),
        need_pit=False,
    ),
    # === VIX 扩充 ===
    "VIX_NASDAQ": FredIndicator(
        series_id="VXNCLS",
        code="VIX_NASDAQ",
        name="纳斯达克100波动率指数",
        category="vix",
        frequency="daily",
        unit="指数",
        description="CBOE NASDAQ 100 Volatility Index (VXN, 2001-02 起)",
        need_pit=False,
    ),
    "VIX_RUSSELL": FredIndicator(
        series_id="RVXCLS",
        code="VIX_RUSSELL",
        name="罗素2000波动率指数",
        category="vix",
        frequency="daily",
        unit="指数",
        description="CBOE Russell 2000 Volatility Index (RVX, 2004-01 起)",
        need_pit=False,
    ),
    # === Commodity 扩充（EIA 现货 + IMF PCPS 月度；LBMA 已死不注册） ===
    "COMMOD_HH_NATGAS": FredIndicator(
        series_id="DHHNGSP",
        code="COMMOD_HH_NATGAS",
        name="Henry Hub天然气现货",
        category="commodity",
        frequency="daily",
        unit="美元/百万英热",
        description="Henry Hub Natural Gas Spot Price (EIA, 1997-01 起)",
        need_pit=False,
    ),
    "COMMOD_GASREGW": FredIndicator(
        series_id="GASREGW",
        code="COMMOD_GASREGW",
        name="美国常规汽油零售价(周)",
        category="commodity",
        frequency="weekly",
        unit="美元/加仑",
        description=(
            "US Regular Conventional Gas Price, Weekly (EIA 周一发布上周值; "
            "周频如实注册, 不伪称日频)"
        ),
        need_pit=False,
    ),
    "COMMOD_COPPER_IMF": FredIndicator(
        series_id="PCOPPUSDM",
        code="COMMOD_COPPER_IMF",
        name="IMF铜价(月)",
        category="commodity",
        frequency="monthly",
        unit="美元/吨",
        description="Global price of Copper (IMF PCPS, monthly)",
        need_pit=False,
    ),
    "COMMOD_ALUMINUM_IMF": FredIndicator(
        series_id="PALUMUSDM",
        code="COMMOD_ALUMINUM_IMF",
        name="IMF铝价(月)",
        category="commodity",
        frequency="monthly",
        unit="美元/吨",
        description="Global price of Aluminum (IMF PCPS, monthly)",
        need_pit=False,
    ),
    "COMMOD_IRONORE_IMF": FredIndicator(
        series_id="PIORECRUSDM",
        code="COMMOD_IRONORE_IMF",
        name="IMF铁矿石价(月)",
        category="commodity",
        frequency="monthly",
        unit="美元/干公吨",
        description="Global price of Iron Ore (IMF PCPS, monthly)",
        need_pit=False,
    ),
    "COMMOD_WTI_IMF": FredIndicator(
        series_id="POILWTIUSDM",
        code="COMMOD_WTI_IMF",
        name="IMF WTI原油价(月)",
        category="commodity",
        frequency="monthly",
        unit="美元/桶",
        description=(
            "Global price of WTI Crude (IMF PCPS, monthly; 与 DCOILWTICO "
            "日度现货是不同频率/口径序列)"
        ),
        need_pit=False,
    ),
    "COMMOD_NATGAS_EU_IMF": FredIndicator(
        series_id="PNGASEUUSDM",
        code="COMMOD_NATGAS_EU_IMF",
        name="IMF欧盟天然气价(月)",
        category="commodity",
        frequency="monthly",
        unit="美元/百万英热",
        description=(
            "Global price of Natural Gas, EU (IMF PCPS, monthly; 与 Henry Hub "
            "是不同基准。正确ID为 PNGASEUUSDM——候选清单的 PNGASUSDM "
            "为错误ID 404, 2026-10-05 CSV 端点核实)"
        ),
        need_pit=False,
    ),
    "COMMOD_ALLFNF_IMF": FredIndicator(
        series_id="PALLFNFINDEXM",
        code="COMMOD_ALLFNF_IMF",
        name="IMF全球金融与非能源商品指数(月)",
        category="commodity",
        frequency="monthly",
        unit="指数",
        description=(
            "IMF Global price index of Financial Non-Fuel Commodities "
            "(正确ID; 旧 PALLFNF/PALLFIN 为错误ID 404)"
        ),
        need_pit=False,
    ),
}


def get_fred_indicator(code: str) -> FredIndicator | None:
    """
    Get FRED indicator metadata by code.

    Args:
        code: Unified indicator code (e.g., "US_UNRATE").

    Returns:
        FredIndicator if found, None otherwise.

    """
    return FRED_INDICATORS.get(code)


def list_fred_indicators(
    category: str | None = None,
    frequency: str | None = None,
) -> list[FredIndicator]:
    """
    List FRED indicators with optional filtering.

    Args:
        category: Filter by category (optional).
        frequency: Filter by frequency (optional).

    Returns:
        List of matching FredIndicator objects.

    """
    result = list(FRED_INDICATORS.values())
    if category:
        result = [i for i in result if i.category == category]
    if frequency:
        result = [i for i in result if i.frequency == frequency]
    return result


__all__ = [
    "FRED_INDICATORS",
    "FredIndicator",
    "get_fred_indicator",
    "list_fred_indicators",
]
