"""配置加载器 - 自动根据环境加载配置文件."""

from __future__ import annotations

from pathlib import Path

from ditto_platform.foundation.config.environment import Environment


class ConfigLoader:
    """
    配置加载器.

    根据运行环境定位配置文件路径，支持 config/{environment}/ 目录结构。
    ``config_root`` 由调用方显式注入；本工具不发现部署或仓库布局。
    """

    def __init__(
        self,
        environment: Environment,
        *,
        config_root: Path,
    ) -> None:
        """
        初始化配置加载器.

        Args:
            environment: 系统运行环境
            config_root: 包含 ``config/`` 的显式配置根目录

        """
        self.environment = environment
        self.config_root = config_root
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
