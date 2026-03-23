"""CashBook — 现金账户 (frozen dataclass, R6)."""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["CashBook"]


@dataclass(frozen=True)
class CashBook:
    """
    现金账户（不可变）— 状态变更通过创建新实例。

    Attributes:
        available: 可用现金（扣除冻结）
        settled: 已交收（可提现）
        frozen: 冻结金额（待交收/待成交）

    """

    available: float
    settled: float
    frozen: float

    @property
    def total(self) -> float:
        """可用 + 冻结 = 账户总现金。"""
        return self.available + self.frozen
