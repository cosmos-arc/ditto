"""DataHub 文件存储配置."""

from pathlib import Path

from ditto_foundation.config.paths import get_paths
from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class FileStorageSettings(BaseSettings):
    """文件存储配置（遵循 XDG Base Directory 规范）."""

    model_config = SettingsConfigDict(
        env_prefix="",
        extra="ignore",
        populate_by_name=True,
    )

    @computed_field
    @property
    def data_root(self) -> Path:
        """数据存储根目录."""
        return get_paths().data_home

    @computed_field
    @property
    def log_root(self) -> Path:
        """日志存储根目录."""
        return get_paths().state_subdir("logs")

    @computed_field
    @property
    def backup_root(self) -> Path:
        """备份存储根目录."""
        return get_paths().state_subdir("backups")

    @computed_field
    @property
    def temp_root(self) -> Path:
        """临时文件存储根目录."""
        return get_paths().cache_subdir("temp")


__all__ = ["FileStorageSettings"]
