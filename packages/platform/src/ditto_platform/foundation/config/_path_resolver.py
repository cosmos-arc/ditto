r"""路径解析器 - 使用责任链模式处理路径解析优先级."""

import os
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
