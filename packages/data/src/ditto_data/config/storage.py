"""Data 文件存储配置。"""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class FileStorageSettings(BaseModel):
    """文件存储配置（仅模型，不读取环境/文件）。"""

    model_config = ConfigDict(extra="ignore")

    data_root: Path = Field(description="数据根目录")
    log_root: Path = Field(description="日志目录")
    backup_root: Path = Field(description="备份目录")
    temp_root: Path = Field(description="临时目录")


__all__ = ["FileStorageSettings"]
