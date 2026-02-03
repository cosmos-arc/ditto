"""DataHub 数据库配置。"""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class DatabaseSettings(BaseModel):
    """数据库配置（仅模型，不读取环境/文件）。"""

    model_config = ConfigDict(extra="ignore")

    sqlite_path: Path | None = Field(
        default=None,
        description="SQLite 数据库路径(未设置时由 data_root 计算)",
    )
    duckdb_path: Path | None = Field(
        default=None,
        description="DuckDB 数据库路径(未设置时由 data_root 计算)",
    )


__all__ = ["DatabaseSettings"]
