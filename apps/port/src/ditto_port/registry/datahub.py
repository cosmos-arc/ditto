"""
DataHub 组件注册.

Root 注入模式：在 Provider 中集中注册所有 DataHub 组件。
Store/Repository 层代码不修改，只在 Registry 中注册。
"""

from collections.abc import Iterator

from dishka import Provider, Scope, provide
from ditto_datahub import DataHub
from ditto_foundation.config.paths import get_paths
from ditto_foundation.db.sqlite_pool import SQLitePool

__all__ = ["DataHubProvider"]


class DataHubProvider(Provider):
    """DataHub 组件 Provider."""

    scope = Scope.APP

    @provide
    def sqlite_pool(self) -> Iterator[SQLitePool]:
        """
        SQLite 连接池（应用级单例）.

        生命周期：容器启动时创建并初始化，容器关闭时关闭.
        """
        data_root = get_paths().data_home
        db_path = data_root / "meta" / "hub.sqlite"
        pool = SQLitePool(str(db_path))
        pool.init_schema()
        yield pool
        pool.close()

    @provide
    def datahub(self, sqlite_pool: SQLitePool) -> DataHub:
        """
        DataHub 主入口（应用级单例）.

        注意：当前阶段使用 data_root 参数初始化，
        DataHub 内部继续使用 @cached_property 懒加载组件。

        未来改进：完全通过 Provider 注入所有依赖.
        """
        data_root = get_paths().data_home
        return DataHub(data_root=data_root)
