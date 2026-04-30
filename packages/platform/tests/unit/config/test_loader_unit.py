"""ConfigLoader 单元测试."""

from __future__ import annotations

from pathlib import Path

from ditto_platform.foundation.config.environment import Environment
from ditto_platform.foundation.config.loader import ConfigLoader


class TestConfigLoader:
    """ConfigLoader 测试."""

    def test_init_with_explicit_config_root(self, tmp_path: Path) -> None:
        """显式 config_root 应正确设置 config_root 和 config_dir."""
        loader = ConfigLoader(Environment.DEVELOPMENT, config_root=tmp_path)
        assert loader.config_root == tmp_path
        assert loader.config_dir == tmp_path / "config" / "development"

    def test_init_testing_with_config_root(self, tmp_path: Path) -> None:
        loader = ConfigLoader(Environment.TESTING, config_root=tmp_path)
        assert loader.config_dir == tmp_path / "config" / "testing"

    def test_init_production_with_config_root(self, tmp_path: Path) -> None:
        loader = ConfigLoader(Environment.PRODUCTION, config_root=tmp_path)
        assert loader.config_dir == tmp_path / "config" / "production"

    def test_get_env_file_with_config_root(self, tmp_path: Path) -> None:
        """get_env_file() 应基于 config_root 返回绝对路径."""
        loader = ConfigLoader(Environment.DEVELOPMENT, config_root=tmp_path)

        assert loader.get_env_file("observability") == (
            (tmp_path / "config" / "development" / "observability.env").as_posix()
        )
        assert loader.get_env_file("database") == (
            (tmp_path / "config" / "development" / "database.env").as_posix()
        )

    def test_get_env_file_testing_with_config_root(self, tmp_path: Path) -> None:
        loader = ConfigLoader(Environment.TESTING, config_root=tmp_path)

        assert loader.get_env_file("observability") == (
            (tmp_path / "config" / "testing" / "observability.env").as_posix()
        )

    def test_get_env_file_production_with_config_root(self, tmp_path: Path) -> None:
        loader = ConfigLoader(Environment.PRODUCTION, config_root=tmp_path)

        assert loader.get_env_file("data_store") == (
            (tmp_path / "config" / "production" / "data_store.env").as_posix()
        )

    def test_default_config_root_uses_project_root(self) -> None:
        """不传 config_root 时应自动检测项目根目录."""
        loader = ConfigLoader(Environment.DEVELOPMENT)
        assert (loader.config_root / "pixi.toml").exists()

    def test_config_dir_is_path(self, tmp_path: Path) -> None:
        """config_dir 应该是 Path 类型."""
        loader = ConfigLoader(Environment.DEVELOPMENT, config_root=tmp_path)
        assert isinstance(loader.config_dir, Path)
