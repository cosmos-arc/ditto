"""
PIT (Point-in-Time) 策略常量.

定义 PIT 数据查询的核心策略常量，确保数据一致性和防止前瞻偏差。
"""

from __future__ import annotations

from enum import StrEnum


class RollingWindowClosed(StrEnum):
    """
    滚动窗口闭合策略.

    决定窗口是左闭、右闭还是两端闭合。这对于 PIT 安全至关重要，
    可防止数据泄漏。

    Attributes:
        LEFT: 窗口包含 [T-window, T-1] (PIT 安全，无数据泄漏)
        RIGHT: 窗口包含 [T-window+1, T] (非 PIT 安全，有数据泄漏)
        BOTH: 窗口包含 [T-window, T] (非 PIT 安全，有数据泄漏)
        NONE: 窗口包含 [T-window+1, T-1] (PIT 安全)

    Examples:
        rolling_mean(20, closed="left")  → 使用到 T-1 的数据 (安全)
        rolling_mean(20, closed="right") → 使用到 T 的数据 (泄漏)

    """

    LEFT = "left"  # PIT 安全: 窗口 [T-window, T-1]
    RIGHT = "right"  # 非 PIT 安全: 窗口 [T-window+1, T]
    BOTH = "both"  # 非 PIT 安全: 窗口 [T-window, T]
    NONE = "none"  # PIT 安全: 窗口 [T-window+1, T-1]


# ═══════════════════════════════════════════════════════════════════
# PIT 核心策略常量
# ═══════════════════════════════════════════════════════════════════

# 知识日期延迟天数 (T+1 策略)
# 数据在交易日后 T 天才能被获知，防止使用未来数据
KNOWLEDGE_DATE_LAG_DAYS: int = 1

# PIT 查询操作符
# 使用 "<=" 确保只使用 "已知" 的数据
PIT_QUERY_OPERATOR: str = "<="

# 默认滚动窗口闭合策略
# LEFT 策略：窗口包含左端点，不包含当前点
DEFAULT_ROLLING_WINDOW_CLOSED: RollingWindowClosed = RollingWindowClosed.LEFT


# ═══════════════════════════════════════════════════════════════════
# 便捷函数
# ═══════════════════════════════════════════════════════════════════


def is_pit_safe_closed(closed: RollingWindowClosed | str) -> bool:
    """
    检查滚动窗口闭合策略是否 PIT 安全.

    Args:
        closed: 滚动窗口闭合策略

    Returns:
        True 如果是 PIT 安全的策略

    """
    if not isinstance(closed, RollingWindowClosed):
        closed = RollingWindowClosed(closed)
    return closed in (RollingWindowClosed.LEFT, RollingWindowClosed.NONE)


__all__ = [
    "DEFAULT_ROLLING_WINDOW_CLOSED",
    "KNOWLEDGE_DATE_LAG_DAYS",
    "PIT_QUERY_OPERATOR",
    "RollingWindowClosed",
    "is_pit_safe_closed",
]
