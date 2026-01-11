"""Tests for PathResolver class - 遵循 TDD 流程."""

import os
from pathlib import Path
from typing import Any

from ditto_foundation.config.paths import PathResolver, XDGPaths


class TestPathResolver:
    """测试 PathResolver 类."""

    def test_resolve_ditto_env_highest_priority(self, tmp_path: Any) -> None:
        """测试 DITTO_*_DIR 环境变量优先级最高."""
        # 设置测试环境变量
        ditto_config = str(tmp_path / "ditto_config")
        os.environ["DITTO_CONFIG_DIR"] = ditto_config

        try:
            # 同时设置 XDG 环境变量（应该被忽略）
            os.environ["XDG_CONFIG_HOME"] = str(tmp_path / "xdg_config")

            resolver = PathResolver(
                ditto_env="DITTO_CONFIG_DIR",
                xdg_env="XDG_CONFIG_HOME",
                subdir="config",
                unix_default="~/.config",
                app_name="ditto",
                platform="linux",
                base_override=None,
            )

            result = resolver.resolve()

            # 应该使用 DITTO_CONFIG_DIR
            assert result == Path(ditto_config).expanduser()

        finally:
            # 清理环境变量
            os.environ.pop("DITTO_CONFIG_DIR", None)
            os.environ.pop("XDG_CONFIG_HOME", None)

    def test_resolve_xdg_env_second_priority(self, tmp_path: Any) -> None:
        """测试 XDG_*_HOME 环境变量第二优先级."""
        # 设置 XDG 环境变量
        xdg_config = str(tmp_path / "xdg_config")
        os.environ["XDG_CONFIG_HOME"] = xdg_config

        try:
            resolver = PathResolver(
                ditto_env="DITTO_CONFIG_DIR",
                xdg_env="XDG_CONFIG_HOME",
                subdir="config",
                unix_default="~/.config",
                app_name="ditto",
                platform="linux",
                base_override=None,
            )

            result = resolver.resolve()

            # 应该使用 XDG_CONFIG_HOME/ditto
            expected = Path(xdg_config).expanduser() / "ditto"
            assert result == expected

        finally:
            os.environ.pop("XDG_CONFIG_HOME", None)

    def test_resolve_base_dir_third_priority(self, tmp_path: Any) -> None:
        """测试 DITTO_BASE_DIR 环境变量第三优先级."""
        base_dir = str(tmp_path / "ditto_base")
        os.environ["DITTO_BASE_DIR"] = base_dir

        try:
            resolver = PathResolver(
                ditto_env="DITTO_CONFIG_DIR",
                xdg_env="XDG_CONFIG_HOME",
                subdir="config",
                unix_default="~/.config",
                app_name="ditto",
                platform="linux",
                base_override=None,
            )

            result = resolver.resolve()

            # 应该使用 DITTO_BASE_DIR/config
            expected = Path(base_dir).expanduser() / "config"
            assert result == expected

        finally:
            os.environ.pop("DITTO_BASE_DIR", None)

    def test_base_override_fallback(self, tmp_path: Any) -> None:
        """测试 base_override 降级（测试模式）."""
        base_override = tmp_path / "test_base"

        resolver = PathResolver(
            ditto_env="DITTO_CONFIG_DIR",
            xdg_env="XDG_CONFIG_HOME",
            subdir="config",
            unix_default="~/.config",
            app_name="ditto",
            platform="linux",
            base_override=base_override,
        )

        result = resolver.resolve()

        # 应该使用 base_override/config
        assert result == base_override / "config"

    def test_linux_platform_default(self) -> None:
        """测试 Linux 平台默认路径."""
        resolver = PathResolver(
            ditto_env="DITTO_CONFIG_DIR",
            xdg_env="XDG_CONFIG_HOME",
            subdir="config",
            unix_default="~/.config",
            app_name="ditto",
            platform="linux",
            base_override=None,
        )

        result = resolver.resolve()

        # 应该使用 ~/.config/ditto
        expected = Path("~/.config").expanduser() / "ditto"
        assert result == expected

    def test_macos_platform_default(self) -> None:
        """测试 macOS 平台默认路径."""
        resolver = PathResolver(
            ditto_env="DITTO_CONFIG_DIR",
            xdg_env="XDG_CONFIG_HOME",
            subdir="data",
            unix_default="~/.local/share",
            app_name="ditto",
            platform="darwin",
            base_override=None,
        )

        result = resolver.resolve()

        # macOS 应该使用 ~/Library/Application Support/ditto/data
        expected = Path("~/Library/Application Support").expanduser() / "ditto" / "data"
        assert result == expected

    def test_windows_platform_default_with_d_drive(
        self, tmp_path: Any, monkeypatch: Any
    ) -> None:
        """测试 Windows 平台默认路径（D 盘可用）."""
        # 模拟 D 盘存在
        d_drive = tmp_path / "d_drive"
        d_drive.mkdir(parents=True, exist_ok=True)

        resolver = PathResolver(
            ditto_env="DITTO_CONFIG_DIR",
            xdg_env="XDG_CONFIG_HOME",
            subdir="config",
            unix_default="~/.config",
            app_name="ditto",
            platform="win32",
            base_override=None,
            default_windows_base=str(d_drive),
        )

        result = resolver.resolve()

        # Windows 应该使用 D 盘 /config
        assert result == d_drive / "config"

    def test_windows_platform_default_fallback_to_localappdata(
        self, monkeypatch: Any
    ) -> None:
        """测试 Windows 降级到 LOCALAPPDATA."""
        # 模拟 D 盘不存在
        non_existent_d = Path("Z:\\non_existent_d_drive")

        # 设置 LOCALAPPDATA
        localappdata = Path("C:\\Users\\test\\AppData\\Local")
        monkeypatch.setenv("LOCALAPPDATA", str(localappdata))

        resolver = PathResolver(
            ditto_env="DITTO_CONFIG_DIR",
            xdg_env="XDG_CONFIG_HOME",
            subdir="config",
            unix_default="~/.config",
            app_name="ditto",
            platform="win32",
            base_override=None,
            default_windows_base=str(non_existent_d),
        )

        result = resolver.resolve()

        # 应该降级到 LOCALAPPDATA/ditto/config
        expected = localappdata / "ditto" / "config"
        assert result == expected


class TestPathResolverIntegration:
    """测试 PathResolver 与 XDGPaths 的集成."""

    def test_xdg_paths_uses_path_resolver(self, tmp_path: Any) -> None:
        """测试 XDGPaths 使用 PathResolver 解析路径."""
        # 设置测试基础目录
        base_dir = tmp_path / "test_base"
        paths = XDGPaths(base_dir=base_dir)

        # 访问 config_home 应该使用 PathResolver
        config = paths.config_home
        assert config == base_dir / "config"

        # 访问 data_home
        data = paths.data_home
        assert data == base_dir / "data"

        # 访问 state_home
        state = paths.state_home
        assert state == base_dir / "state"

        # 访问 cache_home
        cache = paths.cache_home
        assert cache == base_dir / "cache"

    def test_xdg_paths_environment_priority(self, tmp_path: Any) -> None:
        """测试 XDGPaths 环境变量优先级."""
        # 设置 DITTO_CONFIG_DIR
        ditto_config = tmp_path / "custom_config"
        os.environ["DITTO_CONFIG_DIR"] = str(ditto_config)

        try:
            # 即使设置了 base_dir，DITTO_CONFIG_DIR 优先级更高
            paths = XDGPaths(base_dir=tmp_path / "ignored_base")
            config = paths.config_home

            assert config == ditto_config

        finally:
            os.environ.pop("DITTO_CONFIG_DIR", None)
