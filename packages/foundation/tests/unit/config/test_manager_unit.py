"""SingletonManager 单例管理器测试."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from ditto_foundation.config.manager import SingletonManager

# ==================== 测试用例 ====================


@dataclass
class MockConfig:
    """测试用的模拟配置类."""

    value: int = 42
    name: str = "default"


class MockConfigManager(SingletonManager[MockConfig]):
    """测试用的配置管理器."""

    _instance: ClassVar[MockConfig | None] = None

    @classmethod
    def _create_instance(cls) -> MockConfig:
        """创建新实例."""
        return MockConfig()


class TestSingletonManagerBasic:
    """SingletonManager 基础功能测试."""

    def setup_method(self) -> None:
        """每个测试前重置单例状态."""
        MockConfigManager.reset()

    def teardown_method(self) -> None:
        """每个测试后清理单例状态."""
        MockConfigManager.reset()

    def test_get_returns_singleton_instance_on_first_call(self) -> None:
        """Test that get() returns a new singleton instance on first call."""
        instance = MockConfigManager.get()

        assert instance is not None
        assert isinstance(instance, MockConfig)
        assert instance.value == 42

    def test_get_returns_same_instance(self) -> None:
        """多次调用 get() 应返回同一实例(单例行为)."""
        instance1 = MockConfigManager.get()
        instance2 = MockConfigManager.get()

        assert instance1 is instance2

    def test_reset_clears_instance(self) -> None:
        """reset() 应清除实例."""
        instance1 = MockConfigManager.get()
        MockConfigManager.reset()
        instance2 = MockConfigManager.get()

        assert instance1 is not instance2

    def test_reload_creates_new_instance(self) -> None:
        """reload() 应创建新实例并返回."""
        instance1 = MockConfigManager.get()
        instance2 = MockConfigManager.reload()

        assert instance1 is not instance2
        assert isinstance(instance2, MockConfig)

    def test_reload_updates_singleton(self) -> None:
        """reload() 后 get() 应返回新实例."""
        _instance1 = MockConfigManager.get()
        instance2 = MockConfigManager.reload()
        instance3 = MockConfigManager.get()

        assert instance2 is instance3


class TestSingletonManagerIsolation:
    """不同 Manager 子类之间的隔离测试."""

    def setup_method(self) -> None:
        """每个测试前重置单例状态."""
        MockConfigManager.reset()

    def teardown_method(self) -> None:
        """每个测试后清理单例状态."""
        MockConfigManager.reset()

    def test_subclasses_have_independent_instances(self) -> None:
        """不同子类应有独立的实例."""

        @dataclass
        class AnotherConfig:
            """另一个配置类."""

            data: str = "another"

        class AnotherManager(SingletonManager[AnotherConfig]):
            """另一个管理器."""

            _instance: ClassVar[AnotherConfig | None] = None

            @classmethod
            def _create_instance(cls) -> AnotherConfig:
                return AnotherConfig()

        try:
            mock_instance = MockConfigManager.get()
            another_instance = AnotherManager.get()

            assert mock_instance is not another_instance
            assert isinstance(mock_instance, MockConfig)
            assert isinstance(another_instance, AnotherConfig)
        finally:
            AnotherManager.reset()


class TestSingletonManagerEdgeCases:
    """边界情况测试."""

    def setup_method(self) -> None:
        """每个测试前重置单例状态."""
        MockConfigManager.reset()

    def teardown_method(self) -> None:
        """每个测试后清理单例状态."""
        MockConfigManager.reset()

    def test_reset_on_empty_is_safe(self) -> None:
        """在没有实例时调用 reset() 应安全."""
        MockConfigManager.reset()  # [REVIEW]
        MockConfigManager.reset()  # [REVIEW]

    def test_reload_on_empty_creates_instance(self) -> None:
        """在没有实例时调用 reload() 应创建实例."""
        MockConfigManager.reset()
        instance = MockConfigManager.reload()

        assert instance is not None
        assert isinstance(instance, MockConfig)


class TestSettingsManager:
    """SettingsManager 集成测试."""

    def test_settings_manager_exists(self) -> None:
        """SettingsManager 应该存在."""
        from ditto_foundation.config.settings import SettingsManager

        assert SettingsManager is not None

    def test_settings_manager_get_returns_settings(self) -> None:
        """SettingsManager.get() 应返回 Settings 实例."""
        from ditto_foundation.config.settings import Settings, SettingsManager

        try:
            instance = SettingsManager.get()
            assert isinstance(instance, Settings)
        finally:
            SettingsManager.reset()

    def test_settings_manager_singleton_behavior(self) -> None:
        """SettingsManager 应表现出单例行为."""
        from ditto_foundation.config.settings import SettingsManager

        try:
            instance1 = SettingsManager.get()
            instance2 = SettingsManager.get()
            assert instance1 is instance2
        finally:
            SettingsManager.reset()


class TestPathsManager:
    """PathsManager 集成测试."""

    def test_paths_manager_exists(self) -> None:
        """PathsManager 应该存在."""
        from ditto_foundation.config.manager import PathsManager

        assert PathsManager is not None

    def test_paths_manager_get_returns_xdg_paths(self) -> None:
        """PathsManager.get() 应返回 XDGPaths 实例."""
        from ditto_foundation.config.manager import PathsManager
        from ditto_foundation.config.paths import XDGPaths

        try:
            instance = PathsManager.get()
            assert isinstance(instance, XDGPaths)
        finally:
            PathsManager.reset()

    def test_paths_manager_singleton_behavior(self) -> None:
        """PathsManager 应表现出单例行为."""
        from ditto_foundation.config.manager import PathsManager

        try:
            instance1 = PathsManager.get()
            instance2 = PathsManager.get()
            assert instance1 is instance2
        finally:
            PathsManager.reset()
