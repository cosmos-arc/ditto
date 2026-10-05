"""
数据源代码映射常量。

定义数据源代码到 instrument_id 的映射关系，供 adapter 层和 coordinator 层使用。
将常量放在 models 层可以避免 coordinator 直接依赖 adapter 层，符合分层依赖原则。
"""

from __future__ import annotations

# Commodity code to instrument_id mapping
# Using 5M range (5,000,000 - 5,099,999) for commodities
# 注意（#432）：金银 instrument 5_000_003/4 当前由 Tushare fx_daily 的
# FXCM XAU/XAG **bid** 提供（见 tushare/adapters/metal.py），不是 SGE 也不是
# LBMA 定盘；FRED 的 LBMA 序列已死并从注册清除。历史行如存在 LBMA 数值，
# 与 FXCM bid 不是同一基准，不得无缝拼接解读。
COMMODITY_CODE_TO_INSTRUMENT_ID: dict[str, int] = {
    "COMMOD_WTI": 5_000_001,  # WTI原油（FRED DCOILWTICO）
    "COMMOD_BRENT": 5_000_002,  # 布伦特原油（FRED DCOILBRENTEU）
    "COMMOD_GOLD": 5_000_003,  # 黄金参考（FXCM XAU/USD bid，经 Tushare）
    "COMMOD_SILVER": 5_000_004,  # 白银参考（FXCM XAG/USD bid，经 Tushare）
}

# VIX (另类数据) code to instrument_id mapping
# Using 5M range (5,100,000 - 5,199,999) for alternative data
# VIX_9D 已随死序列清理移除（#432，序列页访问失败+前轮 404 记录）。
VIX_CODE_TO_INSTRUMENT_ID: dict[str, int] = {
    "VIX_30D": 5_100_001,  # VIX波动率指数(30天)（FRED VIXCLS）
}

# 汇率品种代码映射到 instrument_id
# 使用 4M 范围 (4,000,000 - 4,999,999) 作为汇率
# 注意：贵金属参考（FXCM XAU/XAG bid）经 Tushare fx_daily METAL 分类获取，
# 映射在 COMMODITY_CODE_TO_INSTRUMENT_ID / METAL_CODE_ALIASES，不在此列表
FX_CODE_TO_INSTRUMENT_ID: dict[str, int] = {
    # 外汇货币对
    "USDCNH.FXCM": 4_000_001,
    "EURUSD.FXCM": 4_000_002,
    "GBPUSD.FXCM": 4_000_003,
    "USDJPY.FXCM": 4_000_004,
    "AUDUSD.FXCM": 4_000_005,
    "USDCAD.FXCM": 4_000_006,
}

# 代码别名映射（支持多种输入格式）
# 用于贵金属代码的别名解析
METAL_CODE_ALIASES: dict[str, str] = {
    # 黄金
    "COMMOD_GOLD": "XAUUSD.FXCM",
    "GOLD": "XAUUSD.FXCM",
    "XAUUSD": "XAUUSD.FXCM",
    # 白银
    "COMMOD_SILVER": "XAGUSD.FXCM",
    "SILVER": "XAGUSD.FXCM",
    "XAGUSD": "XAGUSD.FXCM",
}

# FRED 指标代码全集（#432）：sources/fred/indicators.py 注册键 ∪ 已退役
# 代码（历史上以旧名入库的行同样不得进入决策输入，见 #451 展示-only 裁决）。
# application 层按 importlinter 契约不得导入 concrete sources，经本模块
# 暴露；data 层单测（fred/test_indicators.py）锁定"注册表 ⊆ 镜像，且
# 镜像多余项恰为已退役清单"。
# 全球参考展示-only：不得进入策略特征/回测/Paper/Agent 决策输入。
FRED_INDICATOR_CODES: frozenset[str] = frozenset(
    {
        "US_GDP_QOQ",
        "US_CPI_INDEX",
        "US_CORE_CPI_INDEX",
        "US_PCE_INDEX",
        "US_CORE_PCE_INDEX",
        "US_UNRATE",
        "US_PAYEMS",
        "US_M2",
        "US_BOND_YIELD_1Y",
        "US_BOND_YIELD_2Y",
        "US_BOND_YIELD_5Y",
        "US_BOND_YIELD_10Y",
        "US_BOND_YIELD_30Y",
        "US_BOND_SPREAD_10Y2Y",
        "US_FEDFUNDS_M",
        "US_FEDFUNDS_D",
        "COMMOD_WTI",
        "COMMOD_BRENT",
        "VIX_30D",
        "US_DOLLAR_INDEX_BROAD",
        # #437 扩充（全部展示-only）
        "US_DOLLAR_INDEX_AFE_GOODS",
        "FX_JPYUSD_H10",
        "FX_EURUSD_H10",
        "FX_USDCNY_H10",
        "FX_GBPUSD_H10",
        "US_BOND_YIELD_1MO",
        "US_BOND_YIELD_3MO",
        "US_BOND_YIELD_3Y",
        "US_BOND_YIELD_7Y",
        "US_BOND_YIELD_20Y",
        "US_BOND_SPREAD_10Y3M",
        "US_BREAKEVEN_10Y",
        "US_BREAKEVEN_5Y",
        "US_SOFR",
        "US_EFFR",
        "US_CREDIT_IG_OAS",
        "US_CREDIT_HY_OAS",
        "US_CORP_YIELD_AAA",
        "US_CORP_YIELD_BAA_D",
        "US_CORP_YIELD_BAA_M",
        "US_BOND_SPREAD_BAA10Y",
        "VIX_NASDAQ",
        "VIX_RUSSELL",
        "COMMOD_HH_NATGAS",
        "COMMOD_GASREGW",
        "COMMOD_COPPER_IMF",
        "COMMOD_ALUMINUM_IMF",
        "COMMOD_IRONORE_IMF",
        "COMMOD_WTI_IMF",
        "COMMOD_NATGAS_EU_IMF",
        "COMMOD_ALLFNF_IMF",
        # 已退役（#432 改名/清理前的旧代码，存量行仍是 FRED 数据）
        "US_CPI_YOY",
        "US_CPI_CORE_YOY",
        "US_PCE_YOY",
        "US_PCE_CORE_YOY",
        "US_M2_YOY",
    }
)


# 新浪外盘连续期货小白名单（#436）——逐品种身份/单位/币种登记。
# 值为 (instrument_id, 单位, 币种, 说明)。连续参考序列：换月规则未知，
# 不与具体可交易合约混身份；身份经数值/符号惯例核实后才入表
# （ZSD 2026-10-05 实测数值与已知金属品种不符且源无名称字段，
# 身份未核实不入表）。展示-only（#451）：不得进入策略/回测/Paper/Agent
# 决策输入。
SINA_FOREIGN_FUTURES: dict[str, tuple[int, str, str, str]] = {
    "CL": (5_000_005, "美元/桶", "USD", "NYMEX WTI 原油连续参考"),
    "GC": (5_000_006, "美元/盎司", "USD", "COMEX 黄金连续参考"),
    "SI": (5_000_007, "美元/盎司", "USD", "COMEX 白银连续参考"),
}

# 全球指数 21 指数权威代码清单（#435，官方 index_global doc_id=211）。
# 官方表无 NDX；IXIC 是纳斯达克综合指数，不能替代纳斯达克 100。
# 摄取篮子（application dataset_registry）与探针脚本共用本清单；
# data 层单测锁定适配器 spec 与本清单一一对应。
# 全球参考展示-only（#451 裁决）：不得进入策略特征/回测/Paper/Agent 决策输入。
GLOBAL_INDEX_CODES: tuple[str, ...] = (
    "XIN9",
    "HSI",
    "HKTECH",
    "HKAH",
    "DJI",
    "SPX",
    "IXIC",
    "FTSE",
    "FCHI",
    "GDAXI",
    "N225",
    "KS11",
    "AS51",
    "SENSEX",
    "IBOVESPA",
    "RTS",
    "TWII",
    "CKLSE",
    "SPTSX",
    "CSX5P",
    "RUT",
)


__all__ = [
    "COMMODITY_CODE_TO_INSTRUMENT_ID",
    "FRED_INDICATOR_CODES",
    "FX_CODE_TO_INSTRUMENT_ID",
    "GLOBAL_INDEX_CODES",
    "METAL_CODE_ALIASES",
    "SINA_FOREIGN_FUTURES",
    "VIX_CODE_TO_INSTRUMENT_ID",
]
