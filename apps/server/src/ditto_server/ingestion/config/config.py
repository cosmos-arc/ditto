"""Ingestion configuration."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class IngestionConfig(BaseSettings):
    """
    Data ingestion configuration.

    Loads configuration from environment variables with DITTO_ prefix.
    """

    model_config = SettingsConfigDict(
        env_prefix="DITTO_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    data_root: Path = Path("data")
    """Root directory for DataHub storage."""

    default_source: str = "tushare"
    """Default data source to use."""

    auto_register_securities: bool = True
    """Automatically register new securities when encountered."""
