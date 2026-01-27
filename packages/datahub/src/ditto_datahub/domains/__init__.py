"""DataHub 域级组织."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ditto_datahub.domains.metadata import MetadataQueryService
else:
    # 运行时导入（将在后续任务实现）
    try:
        from ditto_datahub.domains.metadata import MetadataQueryService
    except ImportError:
        # MetadataQueryService 将在后续任务中实现
        MetadataQueryService = None  # type: ignore[misc,assignment]

__all__ = ["MetadataQueryService"]
