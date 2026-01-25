"""DataSource accessor and factory for external data sources."""

from __future__ import annotations

from ditto_foundation import logger

from ditto_datahub.models.common import Source
from ditto_datahub.sources.base import DataSource


class DataSources:
    """
    Accessor for external data sources.

    所有数据源通过构造函数注入，支持依赖倒置和测试替换。

    """

    def __init__(self, tushare: DataSource) -> None:
        """
        初始化 DataSources。

        Args:
            tushare: Tushare 数据源实例

        """
        self._tushare = tushare
        logger.debug("DataSources initialized", event="sources_init")

    @property
    def tushare(self) -> DataSource:
        """
        Get Tushare data source.

        Returns:
            TushareSource instance.

        """
        return self._tushare

    def get(self, name: str | Source) -> DataSource:
        """
        Get data source by name.

        Args:
            name: Source name (enum or string, e.g., "tushare", Source.TUSHARE).

        Returns:
            DataSource instance.

        Raises:
            ValueError: If source name is unknown.

        """
        # 支持 Source 枚举和字符串
        if isinstance(name, Source):
            source_key = name
        else:
            normalized_name = name.lower().strip()
            try:
                source_key = Source(normalized_name)
            except ValueError as e:
                supported = [s.value for s in Source]
                raise ValueError(
                    f"Unknown source: '{name}'. Supported sources: {supported}"
                ) from e

        if source_key == Source.TUSHARE:
            return self._tushare

        supported = [s.value for s in Source]
        raise ValueError(f"Unknown source: '{name}'. Supported sources: {supported}")
