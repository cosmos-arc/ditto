"""
共享数学工具 — 跨层使用的纯计算函数.

提供通用的统计计算函数（如 Pearson 相关系数），
供 ditto_engine、ditto_application 等多层使用。

准入依据:
- pearson_correlation 被 engine（replay）和 app（comparison）两个业务包消费
- 零外部依赖，纯数值计算，仅依赖 Python 标准库 math
- 稳定性高，不随子域迭代变更
"""

from __future__ import annotations

import math

__all__ = [
    "pearson_correlation",
]


def pearson_correlation(x: list[float], y: list[float]) -> float:
    """
    计算 Pearson 相关系数.

    Args:
        x: 第一个数值序列.
        y: 第二个数值序列（长度须与 x 相同）.

    Returns:
        Pearson 相关系数，范围 [-1, 1].
        输入长度 <= 1 时返回 1.0（退化情况）.
        零方差序列根据方差是否接近返回 1.0 或 0.0.

    """
    n = len(x)
    if n <= 1:
        return 1.0

    mean_x = sum(x) / n
    mean_y = sum(y) / n

    cov = 0.0
    var_x = 0.0
    var_y = 0.0
    for xi, yi in zip(x, y, strict=True):
        dx = xi - mean_x
        dy = yi - mean_y
        cov += dx * dy
        var_x += dx * dx
        var_y += dy * dy

    # 零方差（常量序列）→ 完全相关
    if var_x == 0.0 or var_y == 0.0:
        return 1.0 if math.isclose(var_x, var_y, abs_tol=1e-12) else 0.0

    return cov / math.sqrt(var_x * var_y)
