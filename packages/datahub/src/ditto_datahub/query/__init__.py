"""
DataHub 查询门面.

消费者端查询入口，组合现有 Domain Services 提供简化接口。
不重复实现逻辑，仅做参数转换和委托。
"""

from ditto_datahub.query.market import MarketQuerist
from ditto_datahub.query.metadata import MetadataQuerist
from ditto_datahub.query.provider import ServiceBackedDataProvider

__all__ = [
    "MarketQuerist",
    "MetadataQuerist",
    "ServiceBackedDataProvider",
]
