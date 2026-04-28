"""
数据源异常 re-export.

DataSource ABC 已被 5 个域级 Fetcher Protocol 替代（ISP 合规）。
本模块仅保留异常类的便捷 re-export，权威定义见 ``ditto_data.errors``。
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
