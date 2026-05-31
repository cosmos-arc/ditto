r"""XDG Base Directory 规范实现."""

import os
import sys
from pathlib import Path

from ._path_resolver import (
    AppConfig,
    EnvVarConfig,
    PathResolver,
    PathResolverConfig,
    PlatformConfig,
)


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
                # Unix: /tmp 降级方案（XDG_RUNTIME_DIR 已在上方处理）
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
