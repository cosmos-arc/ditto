"""
Market 查询类型定义 — AdjType 枚举.

独立模块以避免 market_queries ↔ market_adjustment 循环依赖。
"""

from __future__ import annotations

from enum import Enum

__all__ = [
    "AdjType",
]


class AdjType(Enum):
    """复权类型."""

    NONE = "none"  # 不复权
    QFQ = "qfq"  # 前复权
    HFQ = "hfq"  # 后复权

    @classmethod
    def from_string(cls, value: str) -> AdjType:
        """
        从字符串解析复权类型.

        Args:
            value: 字符串值 ("none", "qfq", "hfq")

        Returns:
            对应的 AdjType 枚举值，默认返回 NONE

        """
        return {"none": cls.NONE, "qfq": cls.QFQ, "hfq": cls.HFQ}.get(
            value.lower(), cls.NONE
        )
