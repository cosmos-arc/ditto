"""
共享枚举类型.

跨层共享的领域枚举，满足 kernel 准入标准：
- 至少被 2 个业务包直接导入
- 纯值语义，不含方法或 I/O
- 稳定性高，不会随子域迭代频繁变更
"""

from enum import StrEnum

__all__ = ["AssetClass", "Exchange", "OrderSide", "RiskScope", "RunStatus"]


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

    统一 DataHub `OrderSide` 和 Core `OrderDirection` 为单一名称。
    """

    BUY = "buy"
    SELL = "sell"


class RiskScope(StrEnum):
    """风控扫描范围。"""

    INSTRUMENT = "instrument"
    PORTFOLIO = "portfolio"


class RunStatus(StrEnum):
    """策略运行状态枚举."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
