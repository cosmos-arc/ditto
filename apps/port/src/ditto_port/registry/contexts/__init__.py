"""上下文组合包模块。"""

from ditto_port.registry.contexts.bundle import IngestionBundle
from ditto_port.registry.contexts.ingestion import create_ingestion_bundle

__all__ = ["IngestionBundle", "create_ingestion_bundle"]
