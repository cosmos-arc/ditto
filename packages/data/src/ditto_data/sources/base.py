"""
数据源异常公共 facade.

DataSource ABC 已被 5 个域级 Fetcher Protocol 替代（ISP 合规）。
本模块聚合 sources 子包常用的数据源异常，定义位于 ``ditto_data.errors``。
"""

from ditto_data.errors import (
    DataSourceError,
    SourceAuthenticationError,
    SourceConfigurationError,
    SourceFetchError,
    SourceRateLimitError,
    SourceTransformationError,
)

__all__ = [
    "DataSourceError",
    "SourceAuthenticationError",
    "SourceConfigurationError",
    "SourceFetchError",
    "SourceRateLimitError",
    "SourceTransformationError",
]
