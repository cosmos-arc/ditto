"""Ingestion configuration."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class IngestionConfig(BaseModel):
    """Data ingestion configuration (pure model)."""

    model_config = ConfigDict(extra="ignore")

    data_root: Path = Field(
        default=Path("data"),
        description="Root directory for DataHub storage.",
    )
    default_source: str = "tushare"
    auto_register_securities: bool = True


__all__ = ["IngestionConfig"]
