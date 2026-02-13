"""
Caching module.

Provides general-purpose caching capabilities based on cachebox.
"""

from ditto_infra.foundation.cache.core import CacheStats, DataCache

__all__ = [
    "CacheStats",
    "DataCache",
]
