"""测试 function-scoped 数据库 fixtures."""

import pytest
from ditto_platform.foundation import Settings


@pytest.mark.unit
class TestSettingsFixture:
    """测试 test_settings fixture."""

    def test_settings_returns_settings(self, test_settings: Settings):
        """测试 test_settings 返回 Settings 实例."""
        assert isinstance(test_settings, Settings)
        assert test_settings.is_testing

    def test_settings_has_system_config(self, test_settings: Settings):
        """测试 test_settings 配置了系统配置."""
        assert test_settings.system.environment.value == "testing"
        assert test_settings.system.timezone == "Asia/Shanghai"
