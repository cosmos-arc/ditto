"""
Data normalization enumerations and configuration.

定义数据标准化相关的枚举类型和配置类，用于将数据源格式转换为项目标准格式。
"""

from dataclasses import dataclass, field
from enum import StrEnum

__all__ = [
    "Currency",
    "Exchange",
    "InstrumentType",
    "NormalizationConfig",
]


class Exchange(StrEnum):
    """
    交易所代码（ISO 10383 标准）.

    定义中国各大交易所的标准代码，遵循 ISO 10383 MIC (Market Identifier Code) 标准。
    """

    SSE = "SSE"  # 上海证券交易所
    SZSE = "SZSE"  # 深圳证券交易所
    BSE = "BSE"  # 北京证券交易所
    CFFEX = "CFFEX"  # 中国金融期货交易所
    SHFE = "SHFE"  # 上海期货交易所
    DCE = "DCE"  # 大连商品交易所
    CZCE = "CZCE"  # 郑州商品交易所


class InstrumentType(StrEnum):
    """
    标的类型（ISO 10962 CFI 标准）.

    定义金融标的的类型分类，遵循 ISO 10962 CFI 标准。
    """

    STOCK = "stock"  # 股票
    ETF = "etf"  # 交易型开放式指数基金
    INDEX = "index"  # 指数
    FUTURE = "future"  # 期货
    OPTION = "option"  # 期权
    BOND = "bond"  # 债券
    FUND = "fund"  # 基金


class Currency(StrEnum):
    """
    货币代码（ISO 4217 标准）.

    定义支持的货币代码，遵循 ISO 4217 标准。
    """

    CNY = "CNY"  # 人民币
    USD = "USD"  # 美元
    HKD = "HKD"  # 港币
    EUR = "EUR"  # 欧元


@dataclass(frozen=True)
class NormalizationConfig:
    """
    数据标准化配置.

    定义如何将数据源格式转换为项目标准格式。

    Attributes:
        amount_multiplier: 金额倍数，如元→万元使用 10000.0
        volume_multiplier: 数量倍数，如手→股使用 100.0
        percentage_as_decimal: 百分比转换，True 表示 0.03，False 表示 3.0
        exchange_map: 交易所代码映射字典，将数据源代码映射到标准 Exchange 枚举
        asset_class_map: 资产类别映射字典，将数据源代码映射到标准 InstrumentType 枚举
        default_currency: 默认货币

    Examples:
        >>> config = NormalizationConfig()
        >>> config.exchange_map["SH"]
        <Exchange.SSE: 'SSE'>
        >>> config.asset_class_map["E"]
        <InstrumentType.STOCK: 'stock'>

    """

    amount_multiplier: float = 1.0
    volume_multiplier: float = 1.0
    percentage_as_decimal: bool = True
    exchange_map: dict[str, Exchange] = field(
        default_factory=lambda: {
            "SH": Exchange.SSE,
            "SZ": Exchange.SZSE,
            "BJ": Exchange.BSE,
        }
    )
    asset_class_map: dict[str, InstrumentType] = field(
        default_factory=lambda: {
            "E": InstrumentType.STOCK,
            "ETF": InstrumentType.ETF,
            "I": InstrumentType.INDEX,
            "FD": InstrumentType.FUND,
        }
    )
    default_currency: Currency = Currency.CNY
