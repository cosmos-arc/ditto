"""DataHub 数据库配置."""

from pathlib import Path

from ditto_foundation.config.paths import get_paths
from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """数据库配置（遵循 XDG Base Directory 规范）."""

    model_config = SettingsConfigDict(
        env_prefix="DB_",
        extra="ignore",
    )

    @computed_field
    @property
    def duckdb_path(self) -> Path:
        """DuckDB 数据库文件路径."""
        return get_paths().data_subdir("db/duckdb/ditto.duckdb")

    @computed_field
    @property
    def sqlite_path(self) -> Path:
        """SQLite 数据库文件路径."""
        return get_paths().data_subdir("db/sqlite/hub.sqlite")


__all__ = ["DatabaseSettings"]
