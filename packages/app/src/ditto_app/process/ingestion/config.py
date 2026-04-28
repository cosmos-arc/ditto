"""数据摄取配置 — 纯模型定义."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ditto_data.ingestion.freeze_service import FreezeService
from ditto_data.ingestion.ingestion_cursor_service import IngestionCursorService
from ditto_data.ingestion.ingestion_log_service import IngestionLogService
from pydantic import BaseModel, ConfigDict, Field

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


@dataclass(frozen=True)
class IngestionCoordinatorConfig:
    """IngestionCoordinator 可选依赖配置."""

    source_name: str = "tushare"
    ingestion_log_service: IngestionLogService | None = None
    ingestion_cursor_service: IngestionCursorService | None = None
    quality_checker: QualityCheckerProtocol | None = None
    freeze_service: FreezeService | None = None
