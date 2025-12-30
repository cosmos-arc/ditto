"""
统一数据缓存层，基于 cachebox 实现.

本模块提供基于 cachebox.VTTLCache 的统一缓存封装，支持：
- TTL 过期和 LRU 淘汰（由 cachebox 提供）
- 单条目 TTL 和全局默认 TTL
- OpenTelemetry 指标集成
- 模式失效（fnmatch 风格）
- 缓存统计信息
"""

import fnmatch
from dataclasses import dataclass
from typing import Any

import cachebox
from ditto_foundation.observability import M


@dataclass
class CacheStats:
    """缓存统计信息."""

    total_entries: int
    hit_count: int
    miss_count: int
    hit_rate: float
    invalidation_count: int
    evict_count: int


class DataCache:
    """
    基于 cachebox 的统一缓存封装层.

    特性：
    - TTL 过期和 LRU 淘汰（由 cachebox.VTTLCache 提供）
    - 支持单条目 TTL 和全局默认 TTL
    - OpenTelemetry 指标记录
    - 模式失效（fnmatch 风格）
    - 线程安全（cachebox 内置锁）

    注意：
    - 使用 cachebox.VTTLCache 支持单条目 TTL
    - 线程安全由 cachebox 保证，无需额外处理
    """

    def __init__(
        self,
        ttl_seconds: int = 300,
        max_size: int = 10000,
        enable_metrics: bool = True,
    ) -> None:
        """
        初始化缓存.

        Args:
        ----
            ttl_seconds: 默认 TTL（秒），默认 5 分钟
            max_size: 最大缓存条目数，默认 10000
            enable_metrics: 是否启用指标记录

        """
        # cachebox.VTTLCache: (maxsize,)
        # 注意：VTTLCache 构造函数的 ttl 参数仅用于初始化 iterable，
        # 不是新条目的默认 TTL。我们在 set() 方法中手动传递 ttl。
        self._cache: cachebox.VTTLCache[str, Any] = cachebox.VTTLCache(maxsize=max_size)
        self._default_ttl = ttl_seconds  # 保存默认 TTL 供 set() 使用
        self._enable_metrics = enable_metrics

        # 统计计数器（用于非指标模式）
        self._hit_count = 0
        self._miss_count = 0
        self._invalidation_count = 0
        self._evict_count = 0

    def get(self, key: str, default: Any = None) -> Any:
        """
        获取缓存值（记录指标）.

        Args:
        ----
            key: 缓存键（应遵循 category:key 格式）
            default: 未命中时的默认值

        Returns:
        -------
            缓存值或默认值

        """
        try:
            value = self._cache[key]
            if self._enable_metrics:
                M.cache_hit.add(1, {"type": "data_cache"})
            self._hit_count += 1  # 同步维护本地计数器
            return value
        except KeyError:
            if self._enable_metrics:
                M.cache_miss.add(1, {"type": "data_cache"})
            self._miss_count += 1  # 同步维护本地计数器
            return default

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """
        设置缓存值.

        Args:
        ----
            key: 缓存键（应遵循 category:key 格式）
            value: 缓存值
            ttl: TTL 秒数，None 时使用默认 TTL

        Note:
        ----
            VTTLCache 需要显式传递 TTL 参数，ttl=None 表示不设置过期时间。
            我们使用 `_default_ttl` 作为默认值。

        """
        # 必须使用 insert() 方法并显式传递 TTL
        # ttl=None 时使用默认 TTL，ttl=0 时表示不设置过期时间
        if ttl is None:
            self._cache.insert(key, value, ttl=self._default_ttl)
        elif ttl == 0:
            # ttl=0 表示永不过期（不设置 TTL）
            self._cache.insert(key, value)
        else:
            self._cache.insert(key, value, ttl=ttl)

    def invalidate(self, key: str) -> bool:
        """
        失效单个缓存键.

        Args:
        ----
            key: 缓存键

        Returns:
        -------
            是否成功失效（键存在返回 True）

        """
        try:
            del self._cache[key]
            if self._enable_metrics:
                M.cache_invalidations.add(1)
            self._invalidation_count += 1  # 同步维护本地计数器
            return True
        except KeyError:
            return False

    def invalidate_pattern(self, pattern: str) -> int:
        """
        按模式批量失效缓存键.

        Args:
        ----
            pattern: fnmatch 风格模式（如 "sid:*" 或 "trading_days:*"）

        Returns:
        -------
            失效的键数量

        """
        keys_to_delete = [k for k in self._cache if fnmatch.fnmatch(k, pattern)]
        for key in keys_to_delete:
            del self._cache[key]
            if self._enable_metrics:
                M.cache_invalidations.add(1)
            self._invalidation_count += 1  # 同步维护本地计数器
        return len(keys_to_delete)

    def clear(self) -> None:
        """清空所有缓存."""
        self._cache.clear()

    def get_stats(self) -> CacheStats:
        """
        获取缓存统计信息.

        Returns
        -------
            CacheStats: 包含命中率等统计信息

        """
        total_entries = len(self._cache)

        # 始终使用本地计数器（同步维护）
        hit_count = self._hit_count
        miss_count = self._miss_count
        invalidation_count = self._invalidation_count
        evict_count = self._evict_count

        total_requests = hit_count + miss_count
        hit_rate = hit_count / total_requests if total_requests > 0 else 0.0

        return CacheStats(
            total_entries=total_entries,
            hit_count=hit_count,
            miss_count=miss_count,
            hit_rate=hit_rate,
            invalidation_count=invalidation_count,
            evict_count=evict_count,
        )

    def __len__(self) -> int:
        """返回当前缓存条目数."""
        return len(self._cache)

    def __contains__(self, key: str) -> bool:
        """检查键是否存在于缓存中."""
        return key in self._cache
