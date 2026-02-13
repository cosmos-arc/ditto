"""ConfigLoader 单元测试."""

from __future__ import annotations

from ditto_infra.foundation.config.environment import Environment
from ditto_infra.foundation.config.loader import ConfigLoader


class TestConfigLoader:
    """ConfigLoader 测试."""

    def test_init_development(self) -> None:
        """ConfigLoader 应该正确初始化开发环境."""
        loader = ConfigLoader(Environment.DEVELOPMENT)
        assert loader.environment == Environment.DEVELOPMENT
        assert loader.config_dir.as_posix() == "config/development"

    def test_init_testing(self) -> None:
        """ConfigLoader 应该正确初始化测试环境."""
        loader = ConfigLoader(Environment.TESTING)
        assert loader.environment == Environment.TESTING
        assert loader.config_dir.as_posix() == "config/testing"

    def test_init_production(self) -> None:
        """ConfigLoader 应该正确初始化生产环境."""
        loader = ConfigLoader(Environment.PRODUCTION)
        assert loader.environment == Environment.PRODUCTION
        assert loader.config_dir.as_posix() == "config/production"

    def test_get_env_file_development(self) -> None:
        """get_env_file() 应该返回正确的开发环境配置文件路径."""
        loader = ConfigLoader(Environment.DEVELOPMENT)

        assert loader.get_env_file("observability") == (
            "config/development/observability.env"
        )
        assert loader.get_env_file("database") == "config/development/database.env"
        assert loader.get_env_file("data_store") == (
            "config/development/data_store.env"
        )
        assert loader.get_env_file("data_source") == (
            "config/development/data_source.env"
        )
        assert loader.get_env_file("system") == "config/development/system.env"

    def test_get_env_file_testing(self) -> None:
        """get_env_file() 应该返回正确的测试环境配置文件路径."""
        loader = ConfigLoader(Environment.TESTING)

        assert loader.get_env_file("observability") == (
            "config/testing/observability.env"
        )
        assert loader.get_env_file("data_store") == "config/testing/data_store.env"
        assert loader.get_env_file("database") == "config/testing/database.env"

    def test_get_env_file_production(self) -> None:
        """get_env_file() 应该返回正确的生产环境配置文件路径."""
        loader = ConfigLoader(Environment.PRODUCTION)

        assert loader.get_env_file("observability") == (
            "config/production/observability.env"
        )
        assert loader.get_env_file("data_store") == "config/production/data_store.env"
        assert loader.get_env_file("database") == "config/production/database.env"

    def test_config_dir_is_path(self) -> None:
        """config_dir 应该是 Path 类型."""
        loader = ConfigLoader(Environment.DEVELOPMENT)
        from pathlib import Path

        assert isinstance(loader.config_dir, Path)
