"""配置初始化 fail-fast 行为测试."""

from __future__ import annotations

from pathlib import Path

import pytest
from ditto_infra.foundation.config.initializer import (
    ConfigInitCoordinator,
    ConfigInitProvider,
    InitResult,
    InitScope,
)


class FailingProvider(ConfigInitProvider):
    """测试用的失败提供者."""

    @property
    def name(self) -> str:
        """返回提供者名称."""
        return "failing_provider"

    @property
    def scope(self) -> InitScope:
        """返回初始化作用域."""
        return InitScope.STARTUP

    def check(self, data_root: Path) -> bool:
        """检查是否需要初始化."""
        return True

    def initialize(self, data_root: Path) -> InitResult:
        """执行初始化，返回失败结果."""
        return InitResult(
            provider=self.name,
            success=False,
            message="Intentional failure for testing",
        )


class ExceptionProvider(ConfigInitProvider):
    """测试用的抛出异常的提供者."""

    @property
    def name(self) -> str:
        """返回提供者名称."""
        return "exception_provider"

    @property
    def scope(self) -> InitScope:
        """返回初始化作用域."""
        return InitScope.STARTUP

    def check(self, data_root: Path) -> bool:
        """检查是否需要初始化."""
        return True

    def initialize(self, data_root: Path) -> InitResult:
        """执行初始化，抛出异常."""
        raise RuntimeError("Unexpected error during initialization")


class SuccessProvider(ConfigInitProvider):
    """测试用的成功提供者."""

    @property
    def name(self) -> str:
        """返回提供者名称."""
        return "success_provider"

    @property
    def scope(self) -> InitScope:
        """返回初始化作用域."""
        return InitScope.STARTUP

    def check(self, data_root: Path) -> bool:
        """检查是否需要初始化."""
        return True

    def initialize(self, data_root: Path) -> InitResult:
        """执行初始化，返回成功结果."""
        return InitResult(
            provider=self.name,
            success=True,
            message="Initialized successfully",
        )


class ManualScopeFailingProvider(ConfigInitProvider):
    """测试用的 MANUAL 作用域失败提供者."""

    @property
    def name(self) -> str:
        """返回提供者名称."""
        return "manual_failing_provider"

    @property
    def scope(self) -> InitScope:
        """返回初始化作用域."""
        return InitScope.MANUAL

    def check(self, data_root: Path) -> bool:
        """检查是否需要初始化."""
        return True

    def initialize(self, data_root: Path) -> InitResult:
        """执行初始化，返回失败结果."""
        return InitResult(
            provider=self.name,
            success=False,
            message="Manual scope failure",
        )


class TestFailFastBehavior:
    """fail-fast 行为测试."""

    def test_startup_fail_fast_on_provider_failure(self) -> None:
        """STARTUP 场景下 provider 失败应抛出 ConfigInitError."""
        # 延迟导入，因为此时 errors.py 可能还不存在
        from ditto_infra.foundation.config.errors import ConfigInitError

        coordinator = ConfigInitCoordinator()
        coordinator.register(FailingProvider())

        with pytest.raises(ConfigInitError) as exc_info:
            coordinator.initialize(
                scope=InitScope.STARTUP,
                data_root=Path("/tmp"),
                fail_fast=True,
            )

        assert "failing_provider" in exc_info.value.failed_providers
        assert "failing_provider" in exc_info.value.details
        assert (
            "Intentional failure for testing"
            in exc_info.value.details["failing_provider"]
        )

    def test_startup_fail_fast_on_exception(self) -> None:
        """STARTUP 场景下 provider 抛出异常应抛出 ConfigInitError."""
        from ditto_infra.foundation.config.errors import ConfigInitError

        coordinator = ConfigInitCoordinator()
        coordinator.register(ExceptionProvider())

        with pytest.raises(ConfigInitError) as exc_info:
            coordinator.initialize(
                scope=InitScope.STARTUP,
                data_root=Path("/tmp"),
                fail_fast=True,
            )

        assert "exception_provider" in exc_info.value.failed_providers
        assert "RuntimeError" in exc_info.value.details["exception_provider"]

    def test_startup_no_fail_fast_when_all_succeed(self) -> None:
        """STARTUP 场景下所有 provider 成功不应抛出异常."""
        coordinator = ConfigInitCoordinator()
        coordinator.register(SuccessProvider())

        results = coordinator.initialize(
            scope=InitScope.STARTUP,
            data_root=Path("/tmp"),
            fail_fast=True,
        )

        assert len(results) == 1
        assert results["success_provider"].success is True

    def test_manual_scope_does_not_fail_fast(self) -> None:
        """MANUAL 场景下不应 fail-fast，即使 provider 失败."""
        coordinator = ConfigInitCoordinator()
        coordinator.register(ManualScopeFailingProvider())

        results = coordinator.initialize(
            scope=InitScope.MANUAL,
            data_root=Path("/tmp"),
            fail_fast=True,
        )

        assert len(results) == 1
        assert results["manual_failing_provider"].success is False

    def test_always_scope_does_not_fail_fast(self) -> None:
        """ALWAYS 场景下不应 fail-fast，即使有 provider 失败."""
        coordinator = ConfigInitCoordinator()
        coordinator.register(FailingProvider())

        results = coordinator.initialize(
            scope=InitScope.ALWAYS,
            data_root=Path("/tmp"),
            fail_fast=True,
        )

        assert len(results) == 1
        assert results["failing_provider"].success is False

    def test_startup_fail_fast_false_does_not_raise(self) -> None:
        """fail_fast=False 时 STARTUP 场景不应抛出异常."""
        coordinator = ConfigInitCoordinator()
        coordinator.register(FailingProvider())

        results = coordinator.initialize(
            scope=InitScope.STARTUP,
            data_root=Path("/tmp"),
            fail_fast=False,
        )

        assert len(results) == 1
        assert results["failing_provider"].success is False

    def test_fail_fast_default_is_true(self) -> None:
        """fail_fast 默认值应为 True."""
        from ditto_infra.foundation.config.errors import ConfigInitError

        coordinator = ConfigInitCoordinator()
        coordinator.register(FailingProvider())

        # 不传 fail_fast 参数时，默认应为 True
        with pytest.raises(ConfigInitError):
            coordinator.initialize(
                scope=InitScope.STARTUP,
                data_root=Path("/tmp"),
            )

    def test_multiple_failures_all_recorded(self) -> None:
        """多个 provider 失败时，应记录所有失败."""
        from ditto_infra.foundation.config.errors import ConfigInitError

        coordinator = ConfigInitCoordinator()
        coordinator.register(FailingProvider())
        coordinator.register(ExceptionProvider())

        with pytest.raises(ConfigInitError) as exc_info:
            coordinator.initialize(
                scope=InitScope.STARTUP,
                data_root=Path("/tmp"),
                fail_fast=True,
            )

        assert len(exc_info.value.failed_providers) == 2
        assert "failing_provider" in exc_info.value.failed_providers
        assert "exception_provider" in exc_info.value.failed_providers

    def test_mixed_success_and_failure(self) -> None:
        """混合成功和失败时，只应记录失败的 provider."""
        from ditto_infra.foundation.config.errors import ConfigInitError

        coordinator = ConfigInitCoordinator()
        coordinator.register(SuccessProvider())
        coordinator.register(FailingProvider())

        with pytest.raises(ConfigInitError) as exc_info:
            coordinator.initialize(
                scope=InitScope.STARTUP,
                data_root=Path("/tmp"),
                fail_fast=True,
            )

        # 只有 failing_provider 应该在失败列表中
        assert len(exc_info.value.failed_providers) == 1
        assert "failing_provider" in exc_info.value.failed_providers
        assert "success_provider" not in exc_info.value.failed_providers


class TestConfigInitError:
    """ConfigInitError 异常类测试."""

    def test_error_message_format(self) -> None:
        """ConfigInitError 应包含格式化的错误消息."""
        from ditto_infra.foundation.config.errors import ConfigInitError

        error = ConfigInitError(
            failed_providers=["provider1", "provider2"],
            details={
                "provider1": "Connection failed",
                "provider2": "Schema mismatch",
            },
        )

        assert "provider1" in str(error)
        assert "provider2" in str(error)
        assert error.failed_providers == ["provider1", "provider2"]
        assert error.details == {
            "provider1": "Connection failed",
            "provider2": "Schema mismatch",
        }

    def test_error_with_single_provider(self) -> None:
        """ConfigInitError 应正确处理单个失败 provider."""
        from ditto_infra.foundation.config.errors import ConfigInitError

        error = ConfigInitError(
            failed_providers=["only_one"],
            details={"only_one": "Some error"},
        )

        assert error.failed_providers == ["only_one"]
        assert "only_one" in str(error)
