"""风控参数验证工具函数。"""

from __future__ import annotations

from ditto_risk.errors import RiskConfigurationError


def validate_weight(value: float, name: str = "weight") -> None:
    """验证权重参数在 (0, 1] 范围内。"""
    if not 0.0 < value <= 1.0:
        raise RiskConfigurationError(
            f"{name} must be in (0, 1], got {value}",
            field=name,
            value=value,
            min_exclusive=0.0,
            max_inclusive=1.0,
        )
