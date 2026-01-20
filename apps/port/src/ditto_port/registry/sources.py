"""
外部数据源组件注册.

注册 TushareSource 等外部数据源组件。
"""

from dishka import Provider, Scope, provide
from ditto_datahub.sources.source import DataSources
from ditto_datahub.sources.tushare.tushare_source import TushareSource

__all__ = ["DataSourcesProvider"]


class DataSourcesProvider(Provider):
    """外部数据源组件 Provider."""

    scope = Scope.APP

    @provide
    def tushare_source(self) -> TushareSource:
        """
        Tushare 数据源（应用级单例）.

        Token 自动从 keyring 或配置文件读取.
        """
        return TushareSource()

    @provide
    def data_sources(self, tushare_source: TushareSource) -> DataSources:
        """
        DataSources 组合器（应用级单例）.

        Args:
            tushare_source: Tushare 数据源实例

        """
        return DataSources(tushare=tushare_source)
