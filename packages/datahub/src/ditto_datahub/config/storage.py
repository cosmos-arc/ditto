"""DataHub 文件存储配置."""

from pathlib import Path

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

from ditto_datahub.config.data_root import DataRootConfig


class FileStorageSettings(BaseSettings):
    """文件存储配置."""

    model_config = SettingsConfigDict(
        env_prefix="",
        extra="ignore",
        populate_by_name=True,
    )

    @computed_field
    @property
    def data_root(self) -> Path:
        """数据存储根目录."""
        return DataRootConfig().data_root

    @computed_field
    @property
    def log_root(self) -> Path:
        """日志存储根目录."""
        return DataRootConfig().logs_path

    @computed_field
    @property
    def backup_root(self) -> Path:
        """备份存储根目录."""
        return DataRootConfig().backups_path

    @computed_field
    @property
    def temp_root(self) -> Path:
        """临时文件存储根目录."""
        return DataRootConfig().temp_path


__all__ = ["FileStorageSettings"]
