"""ConfigValidationProvider 单元测试 — 启动配置校验."""

from __future__ import annotations

from pathlib import Path

import pytest
from ditto_platform.foundation.config.initializer import InitResult, InitScope
from ditto_platform.foundation.config.providers.config_validation import (
    ConfigValidationProvider,
)

# ==================== 构造 & 属性 ====================


class TestConfigValidationProviderConstruction:
    """构造与基本属性测试."""

    def test_name_returns_config_validation(self) -> None:
        """name 属性应返回 'config_validation'."""
        provider = ConfigValidationProvider()
        assert provider.name == "config_validation"

    def test_scope_returns_startup(self) -> None:
        """scope 属性应返回 STARTUP."""
        provider = ConfigValidationProvider()
        assert provider.scope is InitScope.STARTUP

    def test_check_always_returns_true(self) -> None:
        """check() 应始终返回 True（始终需要校验）."""
        provider = ConfigValidationProvider()
        assert provider.check(Path("/tmp")) is True


# ==================== DATA_DIR 校验 ====================


class TestDataDirValidation:
    """DATA_DIR 校验测试."""

    def test_existing_directory_passes(self, tmp_path: Path) -> None:
        """data_root 为已存在的目录时应通过校验."""
        provider = ConfigValidationProvider()
        result = provider.initialize(tmp_path)
        assert result.success is True

    def test_nonexistent_directory_returns_failure(self, tmp_path: Path) -> None:
        """data_root 不存在时应返回失败."""
        provider = ConfigValidationProvider()
        nonexistent = tmp_path / "does_not_exist"
        result = provider.initialize(nonexistent)

        assert result.success is False
        assert result.message != ""

    def test_file_instead_of_directory_returns_failure(self, tmp_path: Path) -> None:
        """data_root 是文件而非目录时应返回失败."""
        provider = ConfigValidationProvider()
        file_path = tmp_path / "not_a_dir.txt"
        file_path.touch()
        result = provider.initialize(file_path)

        assert result.success is False


# ==================== 与 Coordinator 集成 ====================


class TestCoordinatorIntegration:
    """ConfigValidationProvider 与 Coordinator 集成测试."""

    def test_registered_provider_runs_on_startup(self, tmp_path: Path) -> None:
        """注册后的 provider 在 STARTUP 作用域下应被执行."""
        from ditto_platform.foundation.config.initializer import ConfigInitCoordinator

        coordinator = ConfigInitCoordinator()
        provider = ConfigValidationProvider()
        coordinator.register(provider)

        results = coordinator.initialize(
            scope=InitScope.STARTUP,
            data_root=tmp_path,
        )

        assert "config_validation" in results
        assert results["config_validation"].success is True

    def test_startup_fail_fast_on_invalid_config(self, tmp_path: Path) -> None:
        """STARTUP + fail_fast 时，配置校验失败应抛出 ConfigInitError."""
        from ditto_platform.foundation.config.errors import ConfigInitError
        from ditto_platform.foundation.config.initializer import ConfigInitCoordinator

        coordinator = ConfigInitCoordinator()
        provider = ConfigValidationProvider()
        coordinator.register(provider)

        nonexistent = tmp_path / "missing"
        with pytest.raises(ConfigInitError) as exc_info:
            coordinator.initialize(
                scope=InitScope.STARTUP,
                data_root=nonexistent,
                fail_fast=True,
            )

        assert "config_validation" in exc_info.value.failed_providers

    def test_check_method_returns_true(self, tmp_path: Path) -> None:
        """coordinator.check() 对 config_validation 应始终返回 True."""
        from ditto_platform.foundation.config.initializer import ConfigInitCoordinator

        coordinator = ConfigInitCoordinator()
        provider = ConfigValidationProvider()
        coordinator.register(provider)

        status = coordinator.check(tmp_path)
        assert status["config_validation"] is True

    def test_initialize_returns_init_result(self, tmp_path: Path) -> None:
        """initialize() 应返回 InitResult 实例."""
        provider = ConfigValidationProvider()
        result = provider.initialize(tmp_path)

        assert isinstance(result, InitResult)
        assert result.skipped is False
