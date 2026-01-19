"""配置加载器 - 自动根据环境加载配置文件."""

from pathlib import Path

from ditto_foundation.config.environment import Environment


class ConfigLoader:
    """
    配置加载器.

    根据运行环境自动定位配置文件路径，支持 config/{environment}/ 目录结构.
    """

    def __init__(self, environment: Environment) -> None:
        """
        初始化配置加载器.

        Args:
            environment: 系统运行环境

        """
        self.environment = environment
        self.config_dir = Path("config") / environment.value

    def get_env_file(self, name: str) -> str:
        """
        获取特定配置文件的路径.

        Args:
            name: 配置文件名称（不含 .env 后缀）

        Returns:
            配置文件的完整路径（使用正斜杠，跨平台兼容）

        Examples:
            >>> loader = ConfigLoader(Environment.DEVELOPMENT)
            >>> loader.get_env_file("observability")
            'config/development/observability.env'

        """
        return (self.config_dir / f"{name}.env").as_posix()


__all__ = ["ConfigLoader"]
