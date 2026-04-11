"""数据摄取配置 — 纯模型定义."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from ditto_data.services import (
    FreezeService,
    IngestionCursorService,
    IngestionLogService,
)
from ditto_data.sources.base import DataSource
from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from ditto_app.process.ingestion.ports import QualityCheckerProtocol


class IngestionConfig(BaseModel):
    """Data ingestion configuration (pure model)."""

    model_config = ConfigDict(extra="ignore")

    data_root: Path = Field(
        default=Path("data"),
        description="Root directory for Data storage.",
    )
    default_source: str = "tushare"
    auto_register_securities: bool = True


@dataclass
class IngestionCoordinatorConfig:
    """IngestionCoordinator 可选依赖配置."""

    source_name: str = "tushare"
    ingestion_log_service: IngestionLogService | None = None
    ingestion_cursor_service: IngestionCursorService | None = None
    quality_checker: QualityCheckerProtocol | None = None
    freeze_service: FreezeService | None = None
    fred_source: DataSource | None = None
