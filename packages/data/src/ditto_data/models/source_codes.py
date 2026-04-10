"""
数据源代码映射常量。

定义数据源代码到 instrument_id 的映射关系，供 adapter 层和 coordinator 层使用。
将常量放在 models 层可以避免 coordinator 直接依赖 adapter 层，符合分层依赖原则。
"""

from __future__ import annotations

# Commodity code to instrument_id mapping
# Using 5M range (5,000,000 - 5,099,999) for commodities
COMMODITY_CODE_TO_INSTRUMENT_ID: dict[str, int] = {
    "COMMOD_WTI": 5_000_001,  # WTI原油
    "COMMOD_BRENT": 5_000_002,  # 布伦特原油
    "COMMOD_GOLD": 5_000_003,  # 伦敦金
    "COMMOD_SILVER": 5_000_004,  # 伦敦银
}

# VIX (另类数据) code to instrument_id mapping
# Using 5M range (5,100,000 - 5,199,999) for alternative data
VIX_CODE_TO_INSTRUMENT_ID: dict[str, int] = {
    "VIX_30D": 5_100_001,  # VIX波动率指数(30天)
    "VIX_9D": 5_100_002,  # VIX波动率指数(9天)
}

# 汇率品种代码映射到 instrument_id
# 使用 4M 范围 (4,000,000 - 4,999,999) 作为汇率
# 注意：贵金属现货（伦敦金/银）通过 FRED 获取，不在此列表
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


__all__ = [
    "COMMODITY_CODE_TO_INSTRUMENT_ID",
    "FX_CODE_TO_INSTRUMENT_ID",
    "METAL_CODE_ALIASES",
    "VIX_CODE_TO_INSTRUMENT_ID",
]
