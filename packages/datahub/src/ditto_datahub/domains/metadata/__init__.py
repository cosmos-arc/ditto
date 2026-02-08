"""Metadata 域 - 元数据访问."""

from ditto_datahub.domains.metadata.metadata_service import (
    MetadataQuery,
    MetadataService,
    MetadataWriteCommand,
    MetadataWriteResult,
)

__all__ = [
    "MetadataQuery",
    "MetadataService",
    "MetadataWriteCommand",
    "MetadataWriteResult",
]
