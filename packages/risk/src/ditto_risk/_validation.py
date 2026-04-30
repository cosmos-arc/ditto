"""风控参数验证工具函数。"""

from __future__ import annotations


def validate_weight(value: float, name: str = "weight") -> None:
    """验证权重参数在 (0, 1] 范围内。"""
    if not 0.0 < value <= 1.0:
        raise ValueError(f"{name} must be in (0, 1], got {value}")
