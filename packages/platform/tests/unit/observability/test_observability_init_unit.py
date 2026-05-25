"""
可观测性注册表单元测试.

测试 _registry 模块级函数的状态管理逻辑.

这是单元测试，专注于注册表的状态管理，不涉及外部组件.
"""

import pytest
from ditto_platform.foundation.observability._registry import (
    is_initialized as _is_initialized,
)
from ditto_platform.foundation.observability._registry import (
    reset as _reset,
)
from ditto_platform.foundation.observability._registry import (
    set_initialized as _set_initialized,
)


@pytest.mark.unit
class TestObservabilityRegistry:
    """测试 _registry 模块级函数."""

    def test_is_initialized_initial_state(self) -> None:
        """测试初始状态未初始化."""
        _reset()

        assert _is_initialized() is False

    def test_set_initialized(self) -> None:
        """测试设置初始化状态."""
        _reset()
        assert _is_initialized() is False

        _set_initialized(True)
        assert _is_initialized() is True

        _set_initialized(False)
        assert _is_initialized() is False

    def test_reset_clears_state(self) -> None:
        """测试 reset 清除状态."""
        _set_initialized(True)
        assert _is_initialized() is True

        _reset()
        assert _is_initialized() is False
