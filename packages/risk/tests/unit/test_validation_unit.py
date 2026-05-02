"""validate_weight 参数验证单元测试。"""

from __future__ import annotations

import pytest
from ditto_risk._validation import validate_weight


class TestValidateWeight:
    """validate_weight 校验权重在 (0, 1] 范围内。"""

    def test_valid_weight(self) -> None:
        """0.5 在合法范围内，不抛异常。"""
        validate_weight(0.5)

    def test_weight_one(self) -> None:
        """1.0 是上界，合法。"""
        validate_weight(1.0)

    def test_weight_zero(self) -> None:
        """0.0 不在开区间内，抛 ValueError。"""
        with pytest.raises(ValueError, match="must be in"):
            validate_weight(0.0)

    def test_weight_negative(self) -> None:
        """负值不合法。"""
        with pytest.raises(ValueError, match="must be in"):
            validate_weight(-0.1)

    def test_weight_over_one(self) -> None:
        """超过 1.0 不合法。"""
        with pytest.raises(ValueError, match="must be in"):
            validate_weight(1.5)

    def test_custom_name_in_error(self) -> None:
        """错误信息包含自定义参数名。"""
        with pytest.raises(ValueError, match="max_exposure"):
            validate_weight(2.0, name="max_exposure")
