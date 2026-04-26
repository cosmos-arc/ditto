"""
Services module - 域服务统一入口.

消费方应直接从叶子模块导入特定服务类，
仅通过本模块导入跨域聚合的服务。
"""

from ditto_data.services.derived import (
    DerivedArtifactReader,
    DerivedQueryService,
    DerivedSourceScope,
)
from ditto_data.services.derived_catalog_service import DerivedCatalogService
from ditto_data.services.derived_shadow_slot_service import (
    DerivedShadowSlotService,
)
from ditto_data.services.research_catalog_service import ResearchCatalogService

__all__ = [
    "DerivedArtifactReader",
    "DerivedCatalogService",
    "DerivedQueryService",
    "DerivedShadowSlotService",
    "DerivedSourceScope",
    "ResearchCatalogService",
]
