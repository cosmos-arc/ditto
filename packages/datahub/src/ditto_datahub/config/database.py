"""DataHub 数据库配置."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from ditto_datahub.config.data_root import DataRootConfig


class DatabaseSettings(BaseSettings):
    """
    数据库配置.

    支持通过环境变量覆盖路径：
    - DB_SQLITE_PATH: SQLite 数据库文件路径
    - DB_DUCKDB_PATH: DuckDB 数据库文件路径

    如果未设置环境变量，则使用 DATA_ROOT 下的默认路径。
    """

    model_config = SettingsConfigDict(
        env_prefix="DB_",
        extra="ignore",
    )

    # 使用 Field(default_factory=...) 而非 computed_field
    # 这样既支持环境变量覆盖，又有合理的默认值
    sqlite_path: Path = Field(default_factory=lambda: DataRootConfig().metadata_db_path)
    """SQLite 数据库文件路径。可通过 DB_SQLITE_PATH 环境变量覆盖。"""

    duckdb_path: Path = Field(
        default_factory=lambda: DataRootConfig().db_path / "duckdb/ditto.duckdb"
    )
    """DuckDB 数据库文件路径。可通过 DB_DUCKDB_PATH 环境变量覆盖。"""


__all__ = ["DatabaseSettings"]
