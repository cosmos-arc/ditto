"""
可观测性注册表单元测试.

测试 _ObservabilityRegistry 内部状态管理逻辑.

这是单元测试，专注于注册表类的状态管理，不涉及外部组件.
"""

import pytest
from ditto_platform.foundation.observability._registry import (
    ObservabilityRegistry as _ObservabilityRegistry,
)


@pytest.mark.unit
class TestObservabilityRegistry:
    """测试 _ObservabilityRegistry 类."""

    def test_is_initialized_initial_state(self) -> None:
        """测试初始状态未初始化."""
        # [REVIEW]
        _ObservabilityRegistry.reset()

        assert _ObservabilityRegistry.is_initialized() is False

    def test_set_initialized(self) -> None:
        """测试设置初始化状态."""
        _ObservabilityRegistry.reset()
        assert _ObservabilityRegistry.is_initialized() is False

        _ObservabilityRegistry.set_initialized(True)
        assert _ObservabilityRegistry.is_initialized() is True

        _ObservabilityRegistry.set_initialized(False)
        assert _ObservabilityRegistry.is_initialized() is False

    def test_reset_clears_state(self) -> None:
        """测试 reset 清除状态."""
        _ObservabilityRegistry.set_initialized(True)
        assert _ObservabilityRegistry.is_initialized() is True

        _ObservabilityRegistry.reset()
        assert _ObservabilityRegistry.is_initialized() is False
