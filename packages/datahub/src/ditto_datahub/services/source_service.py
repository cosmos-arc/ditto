"""
SourceService - 外部数据源访问服务.

封装 DataSources，为 Port 层提供统一的外部数据源访问接口.
"""

from ditto_datahub.models.common import Source
from ditto_datahub.sources.base import DataSource
from ditto_datahub.sources.source import DataSources


class SourceService:
    """
    外部数据源访问服务.

    封装 DataSources accessor，提供统一的数据源访问接口。

    职责：
    - 提供数据源的统一访问入口
    - 支持依赖注入和测试替换
    - 管理不同数据源的获取
    """

    def __init__(self, sources: DataSources) -> None:
        """
        初始化 SourceService.

        Args:
            sources: DataSources accessor 实例

        """
        self._sources = sources

    def get_source(self, name: str | Source) -> DataSource:
        """
        获取数据源实例.

        Args:
            name: 数据源名称（枚举或字符串，如 "tushare"、Source.TUSHARE）

        Returns:
            DataSource 实例

        Raises:
            ValueError: 数据源名称未知

        """
        return self._sources.get(name)

    @property
    def tushare(self) -> DataSource:
        """
        获取 Tushare 数据源.

        Returns:
            TushareSource 实例

        """
        return self._sources.tushare
