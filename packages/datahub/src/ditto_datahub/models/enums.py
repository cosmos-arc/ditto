"""
枚举定义模块.

包含项目内统一使用的枚举类型。
"""

from enum import StrEnum

__all__ = ["AssetClass", "Exchange"]


class AssetClass(StrEnum):
    """
    资产类型枚举.

    用于标识金融工具的资产类别，支持多种资产类型的统一管理。

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

    该枚举定义了系统中使用的标准化交易所代码，遵循 ISO 10383 MIC 标准。
    主要用于标识股票、ETF、指数等金融工具的交易场所。

    成员:
        XSHE: 深圳证券交易所（Shenzhen Stock Exchange）
        XSHG: 上海证券交易所（Shanghai Stock Exchange）
        XBSE: 北京证券交易所（Beijing Stock Exchange）

    Example:
        >>> from ditto_datahub.models.enums import Exchange
        >>> exchange = Exchange.XSHE
        >>> str(exchange)
        'XSHE'
        >>> exchange.value
        'XSHE'

    """

    XSHE = "XSHE"  # 深圳证券交易所
    XSHG = "XSHG"  # 上海证券交易所
    XBSE = "XBSE"  # 北京证券交易所
