"""
数据源客户端工厂。.

用于创建和管理不同类型的数据源客户端实例。
"""

from enum import Enum
from typing import Any

from .akshare_client import AkShareClient
from .base_client import BaseClient
from .tushare_client import TushareClient


class DataSourceType(Enum):
    """数据源类型枚举。."""

    TUSHARE = "tushare"
    AKSHARE = "akshare"


class DataSourceFactory:
    """数据源客户端工厂类。."""

    _client_registry: dict[DataSourceType, type[BaseClient]] = {
        DataSourceType.TUSHARE: TushareClient,
        DataSourceType.AKSHARE: AkShareClient,
    }

    @classmethod
    def create_client(
        cls, source_type: DataSourceType, config: dict[str, Any]
    ) -> BaseClient:
        """
        创建数据源客户端实例。.

        Args:
            source_type: 数据源类型
            config: 配置字典

        Returns:
            数据源客户端实例

        Raises:
            ValueError: 如果不支持的数据源类型

        """
        if source_type not in cls._client_registry:
            raise ValueError(f"Unsupported data source type: {source_type}")

        client_class = cls._client_registry[source_type]
        return client_class(config)

    @classmethod
    def register_client(
        cls, source_type: DataSourceType, client_class: type[BaseClient]
    ) -> None:
        """
        注册新的数据源客户端类型。.

        Args:
            source_type: 数据源类型
            client_class: 客户端类

        """
        cls._client_registry[source_type] = client_class

    @classmethod
    def get_available_sources(cls) -> list[DataSourceType]:
        """
        获取所有可用的数据源类型。.

        Returns:
            数据源类型列表

        """
        return list(cls._client_registry.keys())

    @classmethod
    def create_tushare_client(cls, token: str, **kwargs) -> TushareClient:
        """
        创建 Tushare 客户端的便捷方法。.

        Args:
            token: Tushare API token
            **kwargs: 其他配置参数

        Returns:
            Tushare 客户端实例

        """
        config = {"token": token, **kwargs}
        return cls.create_client(DataSourceType.TUSHARE, config)

    @classmethod
    def create_akshare_client(cls, **kwargs) -> AkShareClient:
        """
        创建 AkShare 客户端的便捷方法。.

        Args:
            **kwargs: 配置参数

        Returns:
            AkShare 客户端实例

        """
        return cls.create_client(DataSourceType.AKSHARE, kwargs)
