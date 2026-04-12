"""
共享枚举类型.

跨层共享的领域枚举，满足 kernel 准入标准：
- 至少被 2 个业务包直接导入
- 纯值语义，不含方法或 I/O
- 稳定性高，不会随子域迭代频繁变更
"""

from enum import StrEnum

__all__ = [
    "AssetClass",
    "Exchange",
    "MacroCategory",
    "MacroFrequency",
    "OrderSide",
    "RiskScope",
    "RunStatus",
]


class AssetClass(StrEnum):
    """
    资产类型枚举.

    Attributes:
        STOCK: 股票
        ETF: 交易所交易基金
        INDEX: 指数
        FUTURE: 期货
        BOND: 债券
        FUND: 基金

    """

    STOCK = "stock"
    ETF = "etf"
    INDEX = "index"
    FUTURE = "future"
    BOND = "bond"
    FUND = "fund"


class Exchange(StrEnum):
    """
    统一交易所枚举（ISO 10383 MIC 简化版）.

    用于跨层标识金融工具的交易场所。

    Members:
        XSHE: 深圳证券交易所
        XSHG: 上海证券交易所
        XBSE: 北京证券交易所
    """

    XSHE = "XSHE"  # 深圳证券交易所
    XSHG = "XSHG"  # 上海证券交易所
    XBSE = "XBSE"  # 北京证券交易所


class OrderSide(StrEnum):
    """
    订单方向枚举.

    统一 Data `OrderSide` 和 Core `OrderDirection` 为单一名称。
    """

    BUY = "buy"
    SELL = "sell"


class RiskScope(StrEnum):
    """风控扫描范围。"""

    INSTRUMENT = "instrument"
    PORTFOLIO = "portfolio"


class MacroCategory(StrEnum):
    """
    宏观指标类别枚举。

    Attributes:
        ECONOMIC: 经济指标（GDP 等）
        INTEREST_RATE: 利率指标
        EXCHANGE_RATE: 汇率指标
        MONEY_SUPPLY: 货币供应量指标
        PRICES: 价格指标（CPI、PCE 等）
        EMPLOYMENT: 就业指标（失业率、非农等）

    """

    ECONOMIC = "economic"
    INTEREST_RATE = "interest_rate"
    EXCHANGE_RATE = "exchange_rate"
    MONEY_SUPPLY = "money_supply"
    PRICES = "prices"
    EMPLOYMENT = "employment"


class MacroFrequency(StrEnum):
    """
    宏观指标频率枚举。

    Attributes:
        DAILY: 日频
        MONTHLY: 月频
        QUARTERLY: 季频

    """

    DAILY = "daily"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"


class RunStatus(StrEnum):
    """策略运行状态枚举."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
