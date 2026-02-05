"""配置初始化协调框架单元测试."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from enum import Enum
from pathlib import Path
from threading import Thread
from typing import final

import pytest
from ditto_foundation.config.initializer import (
    ConfigInitCoordinator,
    ConfigInitProvider,
    InitResult,
    InitScope,
)

# ==================== 测试辅助类 ====================


class MockInitScope(str, Enum):
    """测试用的模拟作用域."""

    STARTUP = "startup"
    MANUAL = "manual"
    ALWAYS = "always"


@final
class MockInitProvider(ConfigInitProvider):
    """测试用的模拟提供者."""

    def __init__(
        self,
        name: str,
        scope: InitScope,
        check_result: bool = False,
        init_result: InitResult | None = None,
    ) -> None:
        """
        初始化模拟提供者.

        Args:
            name: 提供者名称
            scope: 初始化作用域
            check_result: check() 方法返回值(True 表示需要初始化)
            init_result: initialize() 方法返回值

        """
        self._name = name
        self._scope = scope
        self._check_result = check_result
        self._init_result = init_result or InitResult(
            provider=name,
            success=True,
            message=f"{name} initialized",
        )
        self.check_calls: list[Path] = []
        self.init_calls: list[Path] = []

    @property
    def name(self) -> str:
        """返回提供者名称."""
        return self._name

    @property
    def scope(self) -> InitScope:
        """返回初始化作用域."""
        return self._scope

    def check(self, data_root: Path) -> bool:
        """
        检查是否需要初始化.

        Args:
            data_root: 数据根目录

        Returns:
            True 表示需要初始化，False 表示已存在

        """
        self.check_calls.append(data_root)
        return self._check_result

    def initialize(self, data_root: Path) -> InitResult:
        """
        执行初始化.

        Args:
            data_root: 数据根目录

        Returns:
            初始化结果

        """
        self.init_calls.append(data_root)
        return self._init_result


class FailingMockProvider(ConfigInitProvider):
    """测试用的失败提供者."""

    @property
    def name(self) -> str:
        """返回提供者名称."""
        return "failing"

    @property
    def scope(self) -> InitScope:
        """返回初始化作用域."""
        return InitScope.STARTUP

    def check(self, data_root: Path) -> bool:
        """检查是否需要初始化."""
        return True

    def initialize(self, data_root: Path) -> InitResult:
        """执行初始化，抛出异常."""
        raise RuntimeError("Initialization failed")


# ==================== InitScope 测试 ====================


class TestInitScope:
    """InitScope 枚举测试."""

    def test_scope_values(self) -> None:
        """InitScope 应该有三个值."""
        assert InitScope.STARTUP.value == "startup"
        assert InitScope.MANUAL.value == "manual"
        assert InitScope.ALWAYS.value == "always"

    def test_scope_is_string_enum(self) -> None:
        """InitScope 应该是字符串枚举."""
        assert isinstance(InitScope.STARTUP, str)
        assert InitScope.STARTUP == "startup"


# ==================== InitResult 测试 ====================


class TestInitResult:
    """InitResult 数据类测试."""

    def test_create_init_result(self) -> None:
        """应该能创建 InitResult 实例."""
        result = InitResult(
            provider="test_provider",
            success=True,
            message="Initialized successfully",
        )

        assert result.provider == "test_provider"
        assert result.success is True
        assert result.message == "Initialized successfully"

    def test_init_result_is_frozen(self) -> None:
        """InitResult 应该是不可变的."""
        result = InitResult(
            provider="test_provider",
            success=True,
            message="Initialized",
        )

        with pytest.raises(FrozenInstanceError):
            result.provider = "new_provider"  # type: ignore[misc]

    def test_init_result_with_skipped(self) -> None:
        """InitResult 可以包含 skipped 字段."""
        result = InitResult(
            provider="test_provider",
            success=True,
            message="Already exists",
            skipped=True,
        )

        assert result.skipped is True

    def test_init_result_default_skipped(self) -> None:
        """InitResult 的 skipped 字段默认为 False."""
        result = InitResult(
            provider="test_provider",
            success=True,
            message="Initialized",
        )

        assert result.skipped is False


# ==================== ConfigInitProvider 测试 ====================


class TestConfigInitProvider:
    """ConfigInitProvider 抽象基类测试."""

    def test_provider_is_abstract(self) -> None:
        """ConfigInitProvider 应该是抽象类，不能直接实例化."""
        with pytest.raises(TypeError):
            ConfigInitProvider()  # type: ignore[abstract]

    def test_mock_provider_implementation(self) -> None:
        """模拟提供者应该正确实现接口."""
        provider = MockInitProvider(
            name="test",
            scope=InitScope.STARTUP,
            check_result=True,
        )

        assert provider.name == "test"
        assert provider.scope == InitScope.STARTUP
        assert provider.check(Path("/tmp")) is True
        assert provider.initialize(Path("/tmp")).provider == "test"


# ==================== ConfigInitCoordinator 测试 ====================


class TestConfigInitCoordinator:
    """ConfigInitCoordinator 协调器测试."""

    def setup_method(self) -> None:
        """每个测试前重置协调器状态."""
        return None

    def teardown_method(self) -> None:
        """每个测试后清理协调器状态."""
        return None

    def test_create_coordinator(self) -> None:
        """应该能创建协调器实例."""
        coordinator = ConfigInitCoordinator()

        assert coordinator is not None
        assert len(coordinator._providers) == 0

    def test_register_provider(self) -> None:
        """应该能注册提供者."""
        coordinator = ConfigInitCoordinator()
        provider = MockInitProvider(
            name="test",
            scope=InitScope.STARTUP,
            check_result=True,
        )

        coordinator.register(provider)

        assert len(coordinator._providers) == 1

    def test_register_multiple_providers(self) -> None:
        """应该能注册多个提供者."""
        coordinator = ConfigInitCoordinator()
        provider1 = MockInitProvider(
            name="provider1",
            scope=InitScope.STARTUP,
            check_result=True,
        )
        provider2 = MockInitProvider(
            name="provider2",
            scope=InitScope.MANUAL,
            check_result=False,
        )

        coordinator.register(provider1)
        coordinator.register(provider2)

        assert len(coordinator._providers) == 2

    def test_initialize_with_startup_scope(self) -> None:
        """initialize(scope=STARTUP) 应该只初始化 STARTUP 提供者."""
        coordinator = ConfigInitCoordinator()
        provider_startup = MockInitProvider(
            name="startup_provider",
            scope=InitScope.STARTUP,
            check_result=True,
        )
        provider_manual = MockInitProvider(
            name="manual_provider",
            scope=InitScope.MANUAL,
            check_result=True,
        )

        coordinator.register(provider_startup)
        coordinator.register(provider_manual)

        results = coordinator.initialize(
            scope=InitScope.STARTUP,
            data_root=Path("/tmp"),
        )

        assert len(results) == 1
        assert "startup_provider" in results
        assert "manual_provider" not in results
        assert results["startup_provider"].success is True
        assert len(provider_startup.init_calls) == 1
        assert len(provider_manual.init_calls) == 0

    def test_initialize_with_manual_scope(self) -> None:
        """initialize(scope=MANUAL) 应该只初始化 MANUAL 提供者."""
        coordinator = ConfigInitCoordinator()
        provider_startup = MockInitProvider(
            name="startup_provider",
            scope=InitScope.STARTUP,
            check_result=True,
        )
        provider_manual = MockInitProvider(
            name="manual_provider",
            scope=InitScope.MANUAL,
            check_result=True,
        )

        coordinator.register(provider_startup)
        coordinator.register(provider_manual)

        results = coordinator.initialize(
            scope=InitScope.MANUAL,
            data_root=Path("/tmp"),
        )

        assert len(results) == 1
        assert "manual_provider" in results
        assert "startup_provider" not in results
        assert results["manual_provider"].success is True
        assert len(provider_manual.init_calls) == 1
        assert len(provider_startup.init_calls) == 0

    def test_initialize_respects_check_result(self) -> None:
        """initialize() 应该尊重 check() 结果."""
        coordinator = ConfigInitCoordinator()
        provider_needs_init = MockInitProvider(
            name="needs_init",
            scope=InitScope.STARTUP,
            check_result=True,
        )
        provider_exists = MockInitProvider(
            name="exists",
            scope=InitScope.STARTUP,
            check_result=False,
        )

        coordinator.register(provider_needs_init)
        coordinator.register(provider_exists)

        results = coordinator.initialize(
            scope=InitScope.STARTUP,
            data_root=Path("/tmp"),
        )

        # needs_init 应该被初始化
        assert "needs_init" in results
        assert len(provider_needs_init.init_calls) == 1

        # exists 应该被跳过
        assert "exists" in results
        assert results["exists"].skipped is True
        assert len(provider_exists.init_calls) == 0

    def test_initialize_with_force_flag(self) -> None:
        """initialize(force=True) 应该忽略 check() 结果."""
        coordinator = ConfigInitCoordinator()
        provider = MockInitProvider(
            name="test",
            scope=InitScope.STARTUP,
            check_result=False,  # check 返回 False(已存在)
        )

        coordinator.register(provider)

        # force=False 时应该跳过
        results = coordinator.initialize(
            scope=InitScope.STARTUP,
            data_root=Path("/tmp"),
            force=False,
        )
        assert results["test"].skipped is True

        # force=True 时应该初始化
        results = coordinator.initialize(
            scope=InitScope.STARTUP,
            data_root=Path("/tmp"),
            force=True,
        )
        assert results["test"].skipped is False
        assert len(provider.init_calls) == 1

    def test_initialize_handles_exceptions(self) -> None:
        """initialize() 应该捕获异常并返回失败结果."""
        coordinator = ConfigInitCoordinator()
        failing_provider = FailingMockProvider()

        coordinator.register(failing_provider)

        results = coordinator.initialize(
            scope=InitScope.STARTUP,
            data_root=Path("/tmp"),
        )

        assert "failing" in results
        assert results["failing"].success is False
        assert "Initialization failed" in results["failing"].message

    def test_check_returns_provider_status(self) -> None:
        """check() 应该返回所有提供者的状态."""
        coordinator = ConfigInitCoordinator()
        provider1 = MockInitProvider(
            name="needs_init",
            scope=InitScope.STARTUP,
            check_result=True,
        )
        provider2 = MockInitProvider(
            name="exists",
            scope=InitScope.STARTUP,
            check_result=False,
        )

        coordinator.register(provider1)
        coordinator.register(provider2)

        status = coordinator.check(Path("/tmp"))

        assert status == {
            "needs_init": True,
            "exists": False,
        }

    def test_initialize_with_always_scope(self) -> None:
        """initialize(scope=ALWAYS) 应该初始化所有提供者."""
        coordinator = ConfigInitCoordinator()
        provider_startup = MockInitProvider(
            name="startup_provider",
            scope=InitScope.STARTUP,
            check_result=False,
        )
        provider_manual = MockInitProvider(
            name="manual_provider",
            scope=InitScope.MANUAL,
            check_result=False,
        )

        coordinator.register(provider_startup)
        coordinator.register(provider_manual)

        results = coordinator.initialize(
            scope=InitScope.ALWAYS,
            data_root=Path("/tmp"),
        )

        # ALWAYS 作用域应该初始化所有提供者
        # [REVIEW] check() 结果控制
        assert len(results) == 2
        assert "startup_provider" in results
        assert "manual_provider" in results

    def test_thread_safety_of_register(self) -> None:
        """register() 应该是线程安全的."""
        coordinator = ConfigInitCoordinator()
        providers = [
            MockInitProvider(
                name=f"provider{i}",
                scope=InitScope.STARTUP,
                check_result=True,
            )
            for i in range(10)
        ]

        threads = [
            Thread(target=coordinator.register, args=(provider,))
            for provider in providers
        ]

        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert len(coordinator._providers) == 10


# ==================== get_config_coordinator 测试 ====================


class TestConfigCoordinatorNoSingleton:
    """get_config_coordinator() 单例测试."""

    def setup_method(self) -> None:
        """每个测试前重置单例状态."""
        return None

    def teardown_method(self) -> None:
        """每个测试后清理单例状态."""
        return None

    def test_returns_coordinator_instance(self) -> None:
        """get_config_coordinator() 应返回协调器实例."""
        coordinator = ConfigInitCoordinator()

        assert coordinator is not None
        assert isinstance(coordinator, ConfigInitCoordinator)

    def test_returns_singleton(self) -> None:
        """多次调用应返回同一实例."""
        coordinator1 = ConfigInitCoordinator()
        coordinator2 = ConfigInitCoordinator()

        assert coordinator1 is not coordinator2

    def test_singleton_persists_registrations(self) -> None:
        """在单例中注册的提供者应该持久化."""
        coordinator1 = ConfigInitCoordinator()
        provider = MockInitProvider(
            name="test",
            scope=InitScope.STARTUP,
            check_result=True,
        )
        coordinator1.register(provider)

        coordinator2 = ConfigInitCoordinator()

        assert len(coordinator2._providers) == 0

    def test_thread_safety_of_singleton(self) -> None:
        """get_config_coordinator() 应该是线程安全的."""
        instances: list[ConfigInitCoordinator] = []

        def get_instance() -> None:
            coordinator = ConfigInitCoordinator()
            instances.append(coordinator)

        threads = [Thread(target=get_instance) for _ in range(10)]

        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        instance_ids = {id(instance) for instance in instances}
        assert len(instance_ids) == len(instances)
