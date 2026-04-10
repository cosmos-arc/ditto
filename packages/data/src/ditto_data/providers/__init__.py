"""
Data Provider 实现 — ServiceBackedDataProvider.

Engine DataProvider Protocol 的实现层，组合 Domain Services
提供统一数据访问接口。
"""

from ditto_data.providers.provider import ServiceBackedDataProvider

__all__ = [
    "ServiceBackedDataProvider",
]
