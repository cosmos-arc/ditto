"""
Ingestion Service 层 - 业务逻辑协调。

本层负责：
- IngestionCoordinator: 统一摄取协调器，处理单日/范围摄取
- MetadataManager: 元数据管理，处理 checksum、增量判断
- BackfillManager: 全量回补管理器
- RetryManager: 重试管理器

设计原则：
- Source 层保持轻量无状态（只负责数据获取）
- Ingestion Service 层负责业务逻辑（增量、回补、重试）
- 通过 DataHub 的 Store/Repository 层持久化数据
"""

from ditto_server.ingestion.services.backfill import BackfillManager
from ditto_server.ingestion.services.coordinator import IngestionCoordinator
from ditto_server.ingestion.services.metadata import MetadataManager
from ditto_server.ingestion.services.retry import RetryManager

__all__ = [
    "BackfillManager",
    "IngestionCoordinator",
    "MetadataManager",
    "RetryManager",
]
