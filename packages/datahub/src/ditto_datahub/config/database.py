"""DataHub 数据库配置."""

from pathlib import Path

from ditto_foundation.config.paths import get_paths
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """
    数据库配置（遵循 XDG Base Directory 规范）.

    支持通过环境变量覆盖路径：
    - DB_SQLITE_PATH: SQLite 数据库文件路径
    - DB_DUCKDB_PATH: DuckDB 数据库文件路径

    如果未设置环境变量，则使用 XDG 规范的默认路径。
    """

    model_config = SettingsConfigDict(
        env_prefix="DB_",
        extra="ignore",
    )

    # 使用 Field(default_factory=...) 而非 computed_field
    # 这样既支持环境变量覆盖，又有合理的默认值
    sqlite_path: Path = Field(
        default_factory=lambda: get_paths().data_subdir("db/sqlite/hub.sqlite")
    )
    """SQLite 数据库文件路径。可通过 DB_SQLITE_PATH 环境变量覆盖。"""

    duckdb_path: Path = Field(
        default_factory=lambda: get_paths().data_subdir("db/duckdb/ditto.duckdb")
    )
    """DuckDB 数据库文件路径。可通过 DB_DUCKDB_PATH 环境变量覆盖。"""


__all__ = ["DatabaseSettings"]
