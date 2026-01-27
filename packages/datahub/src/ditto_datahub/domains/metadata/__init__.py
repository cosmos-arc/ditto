"""Metadata 域 - 元数据访问."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # 类型检查时的导入（将在后续任务实现）
    MetadataQueryService = object
else:
    # 运行时导入（将在后续任务实现）
    try:
        from ditto_datahub.domains.metadata.metadata_query_service import (  # type: ignore[import-not-found]
            MetadataQueryService,
        )
    except ImportError:
        MetadataQueryService = None  # type: ignore[misc,assignment]

__all__ = ["MetadataQueryService"]
