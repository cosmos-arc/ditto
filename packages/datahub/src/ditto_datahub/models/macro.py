"""宏观指标枚举定义。"""

from enum import StrEnum


class MacroCategory(StrEnum):
    """
    宏观指标类别枚举。

    Attributes:
        ECONOMIC: 经济指标
        INTEREST_RATE: 利率指标
        EXCHANGE_RATE: 汇率指标
        MONEY_SUPPLY: 货币供应量指标

    """

    ECONOMIC = "economic"
    INTEREST_RATE = "interest_rate"
    EXCHANGE_RATE = "exchange_rate"
    MONEY_SUPPLY = "money_supply"


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


__all__ = ["MacroCategory", "MacroFrequency"]
