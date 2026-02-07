"""Tests for PathResolver class - 遵循 TDD 流程."""

import os
from pathlib import Path
from typing import Any

from ditto_foundation.config.paths import (
    AppConfig,
    EnvVarConfig,
    PathResolver,
    PathResolverConfig,
    PlatformConfig,
    XDGPaths,
)
from pytest_mock import MockerFixture


class TestPathResolver:
    """测试 PathResolver 类."""

    def test_resolve_ditto_env_highest_priority(self, tmp_path: Any) -> None:
        """测试 DITTO_*_DIR 环境变量优先级最高."""
        # [REVIEW]
        ditto_config = str(tmp_path / "ditto_config")
        os.environ["DITTO_CONFIG_DIR"] = ditto_config

        try:
            # [REVIEW] XDG 环境变量(应该被忽略)
            os.environ["XDG_CONFIG_HOME"] = str(tmp_path / "xdg_config")

            env = EnvVarConfig(ditto_env="DITTO_CONFIG_DIR", xdg_env="XDG_CONFIG_HOME")
            platform = PlatformConfig(platform="linux", unix_default="~/.config")
            app = AppConfig(app_name="ditto", subdir="config")
            config = PathResolverConfig(
                env=env, platform=platform, app=app, base_override=None
            )
            resolver = PathResolver(config)

            result = resolver.resolve()

            # [REVIEW] DITTO_CONFIG_DIR
            assert result == Path(ditto_config).expanduser()

        finally:
            # [REVIEW]
            os.environ.pop("DITTO_CONFIG_DIR", None)
            os.environ.pop("XDG_CONFIG_HOME", None)

    def test_resolve_xdg_env_second_priority(self, tmp_path: Any) -> None:
        """测试 XDG_*_HOME 环境变量第二优先级."""
        # [REVIEW] XDG 环境变量
        xdg_config = str(tmp_path / "xdg_config")
        os.environ["XDG_CONFIG_HOME"] = xdg_config

        try:
            env = EnvVarConfig(ditto_env="DITTO_CONFIG_DIR", xdg_env="XDG_CONFIG_HOME")
            platform = PlatformConfig(platform="linux", unix_default="~/.config")
            app = AppConfig(app_name="ditto", subdir="config")
            config = PathResolverConfig(
                env=env, platform=platform, app=app, base_override=None
            )
            resolver = PathResolver(config)

            result = resolver.resolve()

            # [REVIEW] XDG_CONFIG_HOME/ditto
            expected = Path(xdg_config).expanduser() / "ditto"
            assert result == expected

        finally:
            os.environ.pop("XDG_CONFIG_HOME", None)

    def test_resolve_base_dir_third_priority(self, tmp_path: Any) -> None:
        """测试 DITTO_BASE_DIR 环境变量第三优先级."""
        base_dir = str(tmp_path / "ditto_base")
        os.environ["DITTO_BASE_DIR"] = base_dir

        try:
            env = EnvVarConfig(ditto_env="DITTO_CONFIG_DIR", xdg_env="XDG_CONFIG_HOME")
            platform = PlatformConfig(platform="linux", unix_default="~/.config")
            app = AppConfig(app_name="ditto", subdir="config")
            config = PathResolverConfig(
                env=env, platform=platform, app=app, base_override=None
            )
            resolver = PathResolver(config)

            result = resolver.resolve()

            # [REVIEW] DITTO_BASE_DIR/config
            expected = Path(base_dir).expanduser() / "config"
            assert result == expected

        finally:
            os.environ.pop("DITTO_BASE_DIR", None)

    def test_base_override_fallback(self, tmp_path: Any) -> None:
        """测试 base_override 降级(测试模式)."""
        base_override = tmp_path / "test_base"

        env = EnvVarConfig(ditto_env="DITTO_CONFIG_DIR", xdg_env="XDG_CONFIG_HOME")
        platform = PlatformConfig(platform="linux", unix_default="~/.config")
        app = AppConfig(app_name="ditto", subdir="config")
        config = PathResolverConfig(
            env=env, platform=platform, app=app, base_override=base_override
        )
        resolver = PathResolver(config)

        result = resolver.resolve()

        # [REVIEW] base_override/config
        assert result == base_override / "config"

    def test_linux_platform_default(self) -> None:
        """测试 Linux 平台默认路径."""
        env = EnvVarConfig(ditto_env="DITTO_CONFIG_DIR", xdg_env="XDG_CONFIG_HOME")
        platform = PlatformConfig(platform="linux", unix_default="~/.config")
        app = AppConfig(app_name="ditto", subdir="config")
        config = PathResolverConfig(
            env=env, platform=platform, app=app, base_override=None
        )
        resolver = PathResolver(config)

        result = resolver.resolve()

        # [REVIEW] ~/.config/ditto
        expected = Path("~/.config").expanduser() / "ditto"
        assert result == expected

    def test_macos_platform_default(self) -> None:
        """测试 macOS 平台默认路径."""
        env = EnvVarConfig(ditto_env="DITTO_CONFIG_DIR", xdg_env="XDG_CONFIG_HOME")
        platform = PlatformConfig(platform="darwin", unix_default="~/.local/share")
        app = AppConfig(app_name="ditto", subdir="data")
        config = PathResolverConfig(
            env=env, platform=platform, app=app, base_override=None
        )
        resolver = PathResolver(config)

        result = resolver.resolve()

        # macOS 应该使用 ~/Library/Application Support/ditto/data
        expected = Path("~/Library/Application Support").expanduser() / "ditto" / "data"
        assert result == expected

    def test_windows_platform_default_with_d_drive(
        self, tmp_path: Any, monkeypatch: Any
    ) -> None:
        """测试 Windows 平台默认路径(D 盘可用)."""
        # [REVIEW] D 盘存在
        d_drive = tmp_path / "d_drive"
        d_drive.mkdir(parents=True, exist_ok=True)

        env = EnvVarConfig(ditto_env="DITTO_CONFIG_DIR", xdg_env="XDG_CONFIG_HOME")
        platform = PlatformConfig(
            platform="win32",
            unix_default="~/.config",
            default_windows_base=str(d_drive),
        )
        app = AppConfig(app_name="ditto", subdir="config")
        config = PathResolverConfig(
            env=env, platform=platform, app=app, base_override=None
        )
        resolver = PathResolver(config)

        result = resolver.resolve()

        # Windows 应该使用 D 盘 /config
        assert result == d_drive / "config"

    def test_windows_platform_default_fallback_to_localappdata(
        self, monkeypatch: Any, mocker: MockerFixture
    ) -> None:
        """测试 Windows 降级到 LOCALAPPDATA."""
        # [REVIEW] D 盘不存在
        non_existent_d = Path("Z:\\non_existent_d_drive")

        # Mock Path.mkdir to raise OSError for non_existent path
        original_mkdir = Path.mkdir

        def mock_mkdir(path_obj, *args, **kwargs):
            if "non_existent" in str(path_obj):
                raise OSError("[Errno 13] Permission denied")
            return original_mkdir(path_obj, *args, **kwargs)

        # Apply mock before creating resolver
        mocker.patch("pathlib.Path.mkdir", mock_mkdir)

        # [REVIEW] LOCALAPPDATA
        localappdata = Path("C:\\Users\\test\\AppData\\Local")
        monkeypatch.setenv("LOCALAPPDATA", str(localappdata))

        env = EnvVarConfig(ditto_env="DITTO_CONFIG_DIR", xdg_env="XDG_CONFIG_HOME")
        platform = PlatformConfig(
            platform="win32",
            unix_default="~/.config",
            default_windows_base=str(non_existent_d),
        )
        app = AppConfig(app_name="ditto", subdir="config")
        config = PathResolverConfig(
            env=env, platform=platform, app=app, base_override=None
        )
        resolver = PathResolver(config)

        result = resolver.resolve()

        # [REVIEW] LOCALAPPDATA/ditto/config
        expected = localappdata / "ditto" / "config"
        assert result == expected


class TestPathResolverIntegration:
    """测试 PathResolver 与 XDGPaths 的集成."""

    def test_xdg_paths_uses_path_resolver(self, tmp_path: Any) -> None:
        """测试 XDGPaths 使用 PathResolver 解析路径."""
        # [REVIEW]
        base_dir = tmp_path / "test_base"
        paths = XDGPaths(base_dir=base_dir)

        # [REVIEW] config_home 应该使用 PathResolver
        config = paths.config_home
        assert config == base_dir / "config"

        # [REVIEW] data_home
        data = paths.data_home
        assert data == base_dir / "data"

        # [REVIEW] state_home
        state = paths.state_home
        assert state == base_dir / "state"

        # [REVIEW] cache_home
        cache = paths.cache_home
        assert cache == base_dir / "cache"

    def test_xdg_paths_environment_priority(self, tmp_path: Any) -> None:
        """测试 XDGPaths 环境变量优先级."""
        # [REVIEW] DITTO_CONFIG_DIR
        ditto_config = tmp_path / "custom_config"
        os.environ["DITTO_CONFIG_DIR"] = str(ditto_config)

        try:
            # [REVIEW] base_dir，DITTO_CONFIG_DIR 优先级更高
            paths = XDGPaths(base_dir=tmp_path / "ignored_base")
            config = paths.config_home

            assert config == ditto_config

        finally:
            os.environ.pop("DITTO_CONFIG_DIR", None)


class TestXDGPathsRuntime:
    """测试 XDGPaths.runtime_dir 属性."""

    def test_runtime_dir_with_ditto_env(self, tmp_path: Any) -> None:
        """测试 DITTO_RUNTIME_DIR 环境变量优先级."""
        # [REVIEW] DITTO_RUNTIME_DIR
        ditto_runtime = tmp_path / "ditto_runtime"
        os.environ["DITTO_RUNTIME_DIR"] = str(ditto_runtime)

        try:
            paths = XDGPaths(base_dir=tmp_path / "base")
            runtime = paths.runtime_dir

            assert runtime == ditto_runtime

        finally:
            os.environ.pop("DITTO_RUNTIME_DIR", None)

    def test_runtime_dir_with_xdg_env(self, tmp_path: Any) -> None:
        """测试 XDG_RUNTIME_DIR 环境变量."""
        # [REVIEW] XDG_RUNTIME_DIR
        xdg_runtime = tmp_path / "xdg_runtime"
        os.environ["XDG_RUNTIME_DIR"] = str(xdg_runtime)

        try:
            paths = XDGPaths(base_dir=tmp_path / "base")
            runtime = paths.runtime_dir

            # [REVIEW] XDG_RUNTIME_DIR/ditto
            assert runtime == xdg_runtime / "ditto"

        finally:
            os.environ.pop("XDG_RUNTIME_DIR", None)

    def test_runtime_dir_fallback_win32(self, tmp_path: Any) -> None:
        """测试 Windows 平台降级方案."""
        # [REVIEW] TEMP 环境变量
        temp_dir = tmp_path / "temp"
        os.environ["TEMP"] = str(temp_dir)

        try:
            # [REVIEW] Windows 平台
            paths = XDGPaths(base_dir=tmp_path / "base")
            paths._platform = "win32"

            runtime = paths.runtime_dir

            # [REVIEW] TEMP/ditto
            assert runtime == temp_dir / "ditto"

        finally:
            os.environ.pop("TEMP", None)

    def test_runtime_dir_fallback_unix(self, tmp_path: Any) -> None:
        """测试 Unix 平台降级方案."""
        # [REVIEW]
        paths = XDGPaths(base_dir=tmp_path / "base")
        paths._platform = "linux"

        runtime = paths.runtime_dir

        # [REVIEW] /tmp/ditto-{uid} 或 /tmp/ditto-{pid}
        # [REVIEW] Windows 上运行测试时，路径会被转换为 Windows 格式
        # [REVIEW]
        runtime_str = str(runtime)
        assert "tmp" in runtime_str
        assert "ditto" in runtime_str.lower()


class TestXDGPathsSubdirs:
    """测试 XDGPaths 子目录方法."""

    def test_data_subdir_creates_directory(self, tmp_path: Any) -> None:
        """测试 data_subdir 创建目录."""
        paths = XDGPaths(base_dir=tmp_path / "base")

        # [REVIEW]
        subdir = paths.data_subdir("db/duckdb")

        # Verify路径正确
        assert subdir == tmp_path / "base" / "data" / "db" / "duckdb"
        # Verify目录已创建
        assert subdir.exists()
        assert subdir.is_dir()

    def test_state_subdir_creates_directory(self, tmp_path: Any) -> None:
        """测试 state_subdir 创建目录."""
        paths = XDGPaths(base_dir=tmp_path / "base")

        # [REVIEW]
        subdir = paths.state_subdir("logs/app")

        # Verify路径正确
        assert subdir == tmp_path / "base" / "state" / "logs" / "app"
        # Verify目录已创建
        assert subdir.exists()
        assert subdir.is_dir()

    def test_cache_subdir_creates_directory(self, tmp_path: Any) -> None:
        """测试 cache_subdir 创建目录."""
        paths = XDGPaths(base_dir=tmp_path / "base")

        # [REVIEW]
        subdir = paths.cache_subdir("http")

        # Verify路径正确
        assert subdir == tmp_path / "base" / "cache" / "http"
        # Verify目录已创建
        assert subdir.exists()
        assert subdir.is_dir()


class TestXDGPathsUtilities:
    """测试 XDGPaths 工具方法."""

    def test_ensure_all_creates_directories(self, tmp_path: Any) -> None:
        """测试 ensure_all 创建所有目录."""
        paths = XDGPaths(base_dir=tmp_path / "base")

        # [REVIEW] ensure_all
        paths.ensure_all()

        # Verify所有目录都已创建
        assert paths.config_home.exists()
        assert paths.data_home.exists()
        assert paths.state_home.exists()
        assert paths.cache_home.exists()
        assert paths.runtime_dir.exists()

    def test_as_dict_returns_all_paths(self, tmp_path: Any) -> None:
        """测试 as_dict 返回所有路径."""
        paths = XDGPaths(base_dir=tmp_path / "base")

        # [REVIEW] cached_property
        _ = paths.config_home
        _ = paths.data_home
        _ = paths.state_home
        _ = paths.cache_home
        _ = paths.runtime_dir

        # [REVIEW]
        result = paths.as_dict()

        # Verify字典包含所有键
        assert "config_home" in result
        assert "data_home" in result
        assert "state_home" in result
        assert "cache_home" in result
        assert "runtime_dir" in result

        # Verify值都是字符串
        for key, value in result.items():
            assert isinstance(value, str)
            assert value == str(getattr(paths, key))

    def test_repr_returns_string(self, tmp_path: Any) -> None:
        """测试 __repr__ 返回字符串."""
        paths = XDGPaths(base_dir=tmp_path / "base")

        # [REVIEW]
        result = repr(paths)

        # Verify返回字符串
        assert isinstance(result, str)
        assert "XDGPaths" in result
        assert "data=" in result


class TestGlobalSingleton:
    """测试全局单例函数."""

    def test_get_paths_returns_singleton(self) -> None:
        """测试 get_paths 返回单例."""
        # [REVIEW]
        instance1 = XDGPaths()

        # [REVIEW]
        instance2 = XDGPaths()
        assert instance1 is not instance2

    def test_get_paths_creates_directories(self, tmp_path: Any) -> None:
        """测试 get_paths 创建所有目录."""
        # [REVIEW] base_dir
        paths = XDGPaths(base_dir=tmp_path / "base")

        # [REVIEW] ensure_all
        paths.ensure_all()

        # Verify所有目录都已创建
        assert paths.config_home.exists()
        assert paths.data_home.exists()
        assert paths.state_home.exists()
        assert paths.cache_home.exists()
        assert paths.runtime_dir.exists()

    def test_reload_paths_returns_new_instance(self, tmp_path: Any) -> None:
        """测试 reload_paths 返回新实例."""
        # [REVIEW]
        instance1 = XDGPaths(base_dir=tmp_path / "base1")

        # [REVIEW]
        instance2 = XDGPaths(base_dir=tmp_path / "base2")

        # Verify返回新实例
        assert instance1 is not instance2

        # [REVIEW]
