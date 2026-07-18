"""数据摄取配置 — 纯模型定义."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ditto_data.catalog import DataCatalogReader, DataCatalogWriter
from ditto_data.ingestion.freeze_store import FreezeStore
from ditto_data.ingestion.ingestion_cursor_store import (
    IngestionCursorStore,
)
from ditto_data.ingestion.ingestion_log_store import (
    IngestionLogStore,
)
from ditto_data.lineage import DataLineageRecorder
from pydantic import BaseModel, ConfigDict, Field

from ditto_application.processes.ingestion.evidence_commit import (
    IngestionEvidenceCommitter,
)
from ditto_application.processes.ingestion.ports import QualityCheckerProtocol


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
    ingestion_log_store: IngestionLogStore | None = None
    ingestion_cursor_store: IngestionCursorStore | None = None
    quality_checker: QualityCheckerProtocol | None = None
    freeze_store: FreezeStore | None = None
    lineage_recorder: DataLineageRecorder | None = None
    catalog_reader: DataCatalogReader | None = None
    catalog_writer: DataCatalogWriter | None = None
    evidence_committer: IngestionEvidenceCommitter | None = None
    license_record_id: str | None = None
