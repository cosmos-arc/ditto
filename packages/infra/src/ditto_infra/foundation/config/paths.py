r"""
Ditto 路径管理 - 遵循 XDG Base Directory 规范.

支持：
- Linux: 完整XDG规范
- macOS: XDG或 ~/Library/Application Support
- Windows: 默认使用 D:\\data\\ditto（避免系统盘空间不足）
- Docker: 通过环境变量完全可配置

优先级：
1. DITTO_*_DIR 环境变量（最高优先级，特定目录覆盖）
2. XDG_*_HOME 环境变量（标准 XDG 变量）
3. DITTO_BASE_DIR 环境变量（统一基础目录）
4. 平台默认值（Windows: D:\\data\\ditto）
"""

import os
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class EnvVarConfig:
    """环境变量配置."""

    ditto_env: str
    """Ditto 特定环境变量名(如 "DITTO_CONFIG_DIR")"""

    xdg_env: str
    """XDG 标准环境变量名(如 "XDG_CONFIG_HOME")"""


@dataclass(frozen=True)
class PlatformConfig:
    """平台相关配置."""

    platform: str
    """平台标识(linux/darwin/win32)"""

    unix_default: str
    """Unix 平台默认路径(如 "~/.config")"""

    default_windows_base: str = "D:\\data\\ditto"
    """Windows 默认基础目录"""


@dataclass(frozen=True)
class AppConfig:
    """应用配置."""

    app_name: str
    """应用名称(如 "ditto")"""

    subdir: str
    """子目录名称(如 "config")"""


@dataclass(frozen=True)
class PathResolverConfig:
    """
    路径解析器配置对象.

    通过组合内聚的小配置对象，避免单一配置类参数过多（PLR0913）.
    """

    env: EnvVarConfig
    """环境变量配置"""

    platform: PlatformConfig
    """平台配置"""

    app: AppConfig
    """应用配置"""

    base_override: Path | None = None
    """测试模式的基础目录(可选)"""


class PathResolver:
    """
    路径解析器 - 使用责任链模式处理路径解析优先级.

    优先级：
    1. DITTO_*_DIR 环境变量（最高优先级）
    2. XDG_*_HOME 环境变量
    3. DITTO_BASE_DIR 环境变量
    4. base_override（测试模式）
    5. 平台默认值
    """

    DEFAULT_WINDOWS_BASE: str = "D:\\data\\ditto"

    def __init__(self, config: PathResolverConfig) -> None:
        """
        初始化路径解析器.

        Args:
            config: 路径解析器配置对象

        """
        self.ditto_env = config.env.ditto_env
        self.xdg_env = config.env.xdg_env
        self.subdir = config.app.subdir
        self.unix_default = config.platform.unix_default
        self.app_name = config.app.app_name
        self.platform = config.platform.platform
        self.base_override = config.base_override
        self.default_windows_base = config.platform.default_windows_base

    def resolve(self) -> Path:
        """
        解析路径，按优先级查找.

        Returns:
            解析后的路径.

        """
        # 1. 最高优先级：DITTO_*_DIR 环境变量
        if path := self._resolve_ditto_env():
            return path

        # 2. XDG 环境变量
        if path := self._resolve_xdg_env():
            return path

        # 3. DITTO_BASE_DIR 环境变量
        if path := self._resolve_base_dir():
            return path

        # 4. base_override（测试模式）
        if path := self._resolve_base_override():
            return path

        # 5. 平台默认值
        return self._get_platform_default()

    def _resolve_ditto_env(self) -> Path | None:
        """
        解析 DITTO_*_DIR 环境变量.

        Returns:
            解析后的路径，如果环境变量不存在则返回 None.

        """
        if ditto_override := os.environ.get(self.ditto_env):
            return Path(ditto_override).expanduser()
        return None

    def _resolve_xdg_env(self) -> Path | None:
        """
        解析 XDG_*_HOME 环境变量.

        Returns:
            解析后的路径，如果环境变量不存在则返回 None.

        """
        if xdg_value := os.environ.get(self.xdg_env):
            return Path(xdg_value).expanduser() / self.app_name
        return None

    def _resolve_base_dir(self) -> Path | None:
        """
        解析 DITTO_BASE_DIR 环境变量.

        Returns:
            解析后的路径，如果环境变量不存在则返回 None.

        """
        if base_override := os.environ.get("DITTO_BASE_DIR"):
            return Path(base_override).expanduser() / self.subdir
        return None

    def _resolve_base_override(self) -> Path | None:
        """
        解析 base_override（测试模式）.

        Returns:
            解析后的路径，如果 base_override 为 None 则返回 None.

        """
        if self.base_override is not None:
            return self.base_override / self.subdir
        return None

    def _get_platform_default(self) -> Path:
        """
        获取平台默认路径.

        Returns:
            平台默认路径.

        """
        if self.platform == "win32":
            return self._get_windows_default()
        elif self.platform == "darwin":
            return self._get_macos_default()
        else:
            return self._get_unix_default()

    def _get_windows_default(self) -> Path:
        """
        获取 Windows 默认路径.

        Returns:
            Windows 默认路径.

        """
        base = Path(self.default_windows_base)

        # 如果 D 盘不可用，尝试降级到 LOCALAPPDATA
        if not base.exists():
            try:
                base.mkdir(parents=True, exist_ok=True)
            except OSError:
                # 降级到用户目录
                localappdata = os.environ.get("LOCALAPPDATA", "~")
                base = Path(localappdata).expanduser() / self.app_name

        return base / self.subdir

    def _get_macos_default(self) -> Path:
        """
        获取 macOS 默认路径.

        Returns:
            macOS 默认路径.

        """
        app_support = Path("~/Library/Application Support").expanduser()
        return app_support / self.app_name / self.subdir

    def _get_unix_default(self) -> Path:
        """
        获取 Unix/Linux 默认路径.

        Returns:
            Unix/Linux 默认路径.

        """
        return Path(self.unix_default).expanduser() / self.app_name


class XDGPaths:
    """XDG Base Directory 规范实现."""

    APP_NAME = "ditto"

    # Windows 默认基础目录（D 盘，避免系统盘空间不足）
    DEFAULT_WINDOWS_BASE: str = "D:\\data\\ditto"

    def __init__(self, base_dir: str | Path | None = None) -> None:
        """
        初始化路径管理器.

        Args:
            base_dir: 可选的基础目录（用于测试或自定义）.

        """
        self._platform = sys.platform
        self._base_override: Path | None
        if base_dir is not None:
            self._base_override = Path(base_dir).expanduser()
        else:
            self._base_override = None

        # 懒加载缓存（替代 @cached_property）
        self._config_home: Path | None = None
        self._data_home: Path | None = None
        self._state_home: Path | None = None
        self._cache_home: Path | None = None
        self._runtime_dir: Path | None = None

    # ==================== 核心目录 ====================

    @property
    def config_home(self) -> Path:
        """配置目录 - 用户配置文件."""
        if self._config_home is None:
            self._config_home = self._get_path(
                ditto_env="DITTO_CONFIG_DIR",
                xdg_env="XDG_CONFIG_HOME",
                subdir="config",
                unix_default="~/.config",
            )
        return self._config_home

    @property
    def data_home(self) -> Path:
        """数据目录 - 持久化数据."""
        if self._data_home is None:
            self._data_home = self._get_path(
                ditto_env="DITTO_DATA_DIR",
                xdg_env="XDG_DATA_HOME",
                subdir="data",
                unix_default="~/.local/share",
            )
        return self._data_home

    @property
    def state_home(self) -> Path:
        """状态目录 - 日志、历史记录."""
        if self._state_home is None:
            self._state_home = self._get_path(
                ditto_env="DITTO_STATE_DIR",
                xdg_env="XDG_STATE_HOME",
                subdir="state",
                unix_default="~/.local/state",
            )
        return self._state_home

    @property
    def cache_home(self) -> Path:
        """缓存目录 - 可删除的缓存."""
        if self._cache_home is None:
            self._cache_home = self._get_path(
                ditto_env="DITTO_CACHE_DIR",
                xdg_env="XDG_CACHE_HOME",
                subdir="cache",
                unix_default="~/.cache",
            )
        return self._cache_home

    @property
    def runtime_dir(self) -> Path:
        """运行时目录 - PID、Socket等."""
        if self._runtime_dir is None:
            # 先检查 DITTO_RUNTIME_DIR
            if override := os.environ.get("DITTO_RUNTIME_DIR"):
                self._runtime_dir = Path(override).expanduser()
                return self._runtime_dir

            # 检查 XDG_RUNTIME_DIR
            if xdg_runtime := os.environ.get("XDG_RUNTIME_DIR"):
                self._runtime_dir = Path(xdg_runtime) / self.APP_NAME
                return self._runtime_dir

            # 降级方案
            if self._platform == "win32":
                # Windows: 使用 TEMP/ditto 或回退到用户目录
                temp = os.environ.get("TEMP")
                if not temp:
                    # 回退到用户目录下的应用子目录
                    temp = str(Path("~").expanduser() / self.APP_NAME / "temp")
                self._runtime_dir = Path(temp) / self.APP_NAME
            else:
                # Unix: 使用 XDG_RUNTIME_DIR 或 /tmp 降级方案
                xdg_runtime = os.environ.get("XDG_RUNTIME_DIR")
                if xdg_runtime:
                    self._runtime_dir = Path(xdg_runtime) / self.APP_NAME
                else:
                    # 回退方案：使用 /tmp（符合测试期望）
                    uid = os.getuid() if hasattr(os, "getuid") else os.getpid()
                    runtime_dir = Path(f"/tmp/{self.APP_NAME}-{uid}").expanduser()  # noqa: S108
                    runtime_dir.mkdir(parents=True, exist_ok=True)
                    self._runtime_dir = runtime_dir
        return self._runtime_dir

    # ==================== 子目录访问器 ====================

    def data_subdir(self, name: str) -> Path:
        """
        获取 data_home 下的子目录.

        Args:
            name: 子目录名称（支持嵌套，如 "db/duckdb"）

        Returns:
            子目录的完整路径.

        """
        path = self.data_home / name
        path.mkdir(parents=True, exist_ok=True)
        return path

    def state_subdir(self, name: str) -> Path:
        """
        获取 state_home 下的子目录.

        Args:
            name: 子目录名称（支持嵌套）

        Returns:
            子目录的完整路径.

        """
        path = self.state_home / name
        path.mkdir(parents=True, exist_ok=True)
        return path

    def cache_subdir(self, name: str) -> Path:
        """
        获取 cache_home 下的子目录.

        Args:
            name: 子目录名称（支持嵌套）

        Returns:
            子目录的完整路径.

        """
        path = self.cache_home / name
        path.mkdir(parents=True, exist_ok=True)
        return path

    # ==================== 辅助方法 ====================

    def _get_path(
        self,
        ditto_env: str,
        xdg_env: str,
        subdir: str,
        unix_default: str,
    ) -> Path:
        """
        获取路径，按优先级查找.

        优先级：
        1. DITTO_*_DIR 环境变量（特定目录覆盖）
        2. XDG_*_HOME 环境变量（标准 XDG）
        3. DITTO_BASE_DIR 环境变量（统一基础目录）
        4. base_override（测试模式）
        5. 平台默认值

        Args:
            ditto_env: Ditto 特定环境变量名（如 "DITTO_CONFIG_DIR"）
            xdg_env: XDG 标准环境变量名（如 "XDG_CONFIG_HOME"）
            subdir: 子目录名称（如 "config"）
            unix_default: Unix 平台默认路径（如 "~/.config"）

        Returns:
            解析后的路径.

        """
        env = EnvVarConfig(ditto_env=ditto_env, xdg_env=xdg_env)
        platform = PlatformConfig(
            platform=self._platform,
            unix_default=unix_default,
            default_windows_base=self.DEFAULT_WINDOWS_BASE,
        )
        app = AppConfig(app_name=self.APP_NAME, subdir=subdir)

        config = PathResolverConfig(
            env=env,
            platform=platform,
            app=app,
            base_override=self._base_override,
        )
        resolver = PathResolver(config)
        return resolver.resolve()

    # ==================== 工具方法 ====================

    def ensure_all(self) -> None:
        """确保所有目录存在."""
        dirs = [
            self.config_home,
            self.data_home,
            self.state_home,
            self.cache_home,
            self.runtime_dir,
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)

    def as_dict(self) -> dict[str, str]:
        """
        返回所有路径的字典表示（用于调试）.

        Returns:
            字典，键为目录名称，值为路径字符串.

        """
        return {
            "config_home": str(self.config_home),
            "data_home": str(self.data_home),
            "state_home": str(self.state_home),
            "cache_home": str(self.cache_home),
            "runtime_dir": str(self.runtime_dir),
        }

    def __repr__(self) -> str:
        """返回路径管理器的字符串表示."""
        return f"XDGPaths(data={self.data_home})"


def get_paths() -> XDGPaths:
    """
    获取全局路径管理器实例.

    使用单例模式，避免重复创建.

    Returns:
        XDGPaths: 路径管理器实例.

    """
    msg = "get_paths() 已移除, 全局单例不再支持, 请通过 DI 注入 XDGPaths."
    raise RuntimeError(msg)


def reload_paths() -> XDGPaths:
    """
    重新加载路径管理器（主要用于测试）.

    Returns:
        XDGPaths: 新的路径管理器实例.

    """
    msg = "reload_paths() 已移除, 全局单例不再支持, 请通过 DI 注入 XDGPaths."
    raise RuntimeError(msg)


def reset_paths_for_testing() -> None:
    """
    Reset the singleton paths (for testing purposes only).

    This function allows tests to reset the global state between test runs.
    """
    msg = "reset_paths_for_testing() 已移除, 全局单例不再支持, 请通过 DI 注入 XDGPaths."
    raise RuntimeError(msg)
