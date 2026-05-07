"""配置加载器 - 自动根据环境加载配置文件."""

from __future__ import annotations

from pathlib import Path

from ditto_platform.foundation.config.environment import Environment
from ditto_platform.foundation.config.project_root import find_project_root


class ConfigLoader:
    """
    配置加载器.

    根据运行环境自动定位配置文件路径，支持 config/{environment}/ 目录结构.
    路径解析基于 config_root，默认通过 find_project_root() 确定项目根目录，
    不再依赖进程 CWD.
    """

    def __init__(
        self,
        environment: Environment,
        config_root: Path | None = None,
    ) -> None:
        """
        初始化配置加载器.

        Args:
            environment: 系统运行环境
            config_root: 项目根目录，默认通过 find_project_root() 自动检测

        """
        self.environment = environment
        self.config_root = config_root or find_project_root()
        self.config_dir = self.config_root / "config" / environment.value

    def get_env_file(self, name: str) -> str:
        """
        获取特定配置文件的路径.

        Args:
            name: 配置文件名称（不含 .env 后缀）

        Returns:
            配置文件的完整路径（使用正斜杠，跨平台兼容）

        Examples:
            >>> from pathlib import Path
            >>> loader = ConfigLoader(
            ...     Environment.DEVELOPMENT, config_root=Path("/project")
            ... )
            >>> loader.get_env_file("observability")
            '/project/config/development/observability.env'

        """
        return (self.config_dir / f"{name}.env").as_posix()


__all__ = ["ConfigLoader"]
