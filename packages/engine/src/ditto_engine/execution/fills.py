"""
FillOutcome -- 显式联合类型 (F4).

替代 v2 的 FillEvent | None + side-channel 模式。
FillModel 恢复纯函数语义，无隐式状态。
"""

from __future__ import annotations

from dataclasses import dataclass

from ditto_engine.accounting.fills import FillEvent

__all__ = [
    "FillOutcome",
    "Filled",
    "NoFill",
]


class FillOutcome:
    """FillModel 的显式返回值基类。"""


@dataclass(frozen=True)
class Filled(FillOutcome):
    """成交。"""

    fill_event: FillEvent


@dataclass(frozen=True)
class NoFill(FillOutcome):
    """
    不成交 -- 明确原因，无隐式状态。

    Attributes:
        reason:
            不成交原因 (suspended / limit_up_deferred /
            limit_down_deferred / insufficient_auction /
            price_out_of_range)
        can_retry: True = 下一 step 可能成交，False = 该订单逻辑上无效

    """

    reason: str
    can_retry: bool
