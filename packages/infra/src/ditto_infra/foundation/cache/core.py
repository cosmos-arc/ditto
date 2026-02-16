"""
通用缓存组件，基于 cachebox 实现.

本模块提供基于 cachebox.VTTLCache 的通用缓存封装，支持：
- TTL 过期和 LRU 淘汰（由 cachebox 提供）
- 单条目 TTL 和全局默认 TTL
- OpenTelemetry 指标集成
- 模式失效（fnmatch 风格）
- 缓存统计信息
- 可选的自定义时间源（用于确定性测试）

这是一个通用的技术组件，不包含任何领域特定逻辑，可被所有层使用。
"""

import fnmatch
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import cachebox

from ditto_infra.foundation.observability import Metrics


@dataclass(frozen=True)
class _TTLEntry:
    """TTL 条目元数据（用于自定义时间源模式）."""

    value: Any
    expire_at: float  # 过期时间戳（基于 time_source）


@dataclass(frozen=True)
class CacheStats:
    """缓存统计信息."""

    total_entries: int
    hit_count: int
    miss_count: int
    hit_rate: float
    invalidation_count: int
    evict_count: int


class DataCache[T]:
    """
    基于 cachebox 的通用缓存封装层（泛型版本）.

    类型参数:
        T: 缓存值的类型

    特性：
    - TTL 过期和 LRU 淘汰（由 cachebox.VTTLCache 提供）
    - 支持单条目 TTL 和全局默认 TTL
    - OpenTelemetry 指标记录
    - 模式失效（fnmatch 风格）
    - 线程安全（cachebox 内置锁）
    - 可选的自定义时间源（用于确定性测试）

    注意：
    - 使用 cachebox.VTTLCache 支持单条目 TTL
    - 线程安全由 cachebox 保证，无需额外处理
    - 当提供 time_source 时，TTL 由 Python 层管理（用于测试）
    """

    def __init__(
        self,
        ttl_seconds: int = 300,
        max_size: int = 10000,
        enable_metrics: bool = True,
        time_source: Callable[[], float] | None = None,
    ) -> None:
        """
        初始化缓存.

        Args:
        ----
            ttl_seconds: 默认 TTL（秒），默认 5 分钟
            max_size: 最大缓存条目数，默认 10000
            enable_metrics: 是否启用指标记录
            time_source: 可选的自定义时间源函数，返回当前时间戳（秒）。
                         用于测试场景，提供确定性时间控制。
                         注意：使用自定义时间源时，TTL 由 Python 层管理，
                         cachebox 的内置 TTL 会被禁用。

        """
        # cachebox.VTTLCache: (maxsize,)
        # 注意：VTTLCache 构造函数的 ttl 参数仅用于初始化 iterable，
        # 不是新条目的默认 TTL。我们在 set() 方法中手动传递 ttl。
        self._cache: cachebox.VTTLCache[str, Any] = cachebox.VTTLCache(maxsize=max_size)
        self._default_ttl = ttl_seconds  # 保存默认 TTL 供 set() 使用
        self._enable_metrics = enable_metrics
        self._time_source = time_source

        # 当使用自定义时间源时，需要在 Python 层跟踪 TTL
        # 因为 cachebox 使用 C 级别的系统时间，无法被 Python mock
        self._ttl_entries: dict[str, _TTLEntry] | None = {} if time_source else None

        # 统计计数器（用于非指标模式）
        self._hit_count = 0
        self._miss_count = 0
        self._invalidation_count = 0
        self._evict_count = 0

    def get(self, key: str, default: T | None = None) -> T | None:
        """
        获取缓存值（记录指标）.

        Args:
        ----
            key: 缓存键（应遵循 category:key 格式）
            default: 未命中时的默认值

        Returns:
        -------
            缓存值或默认值（类型为 T | None）

        """
        # 使用自定义时间源模式：在 Python 层检查 TTL
        if self._ttl_entries is not None and self._time_source is not None:
            return self._get_with_custom_time(key, default)

        # 默认模式：依赖 cachebox 的内置 TTL
        try:
            value: T = self._cache[key]
            if self._enable_metrics:
                Metrics.cache_hit.add(1, {"type": "data_cache"})
            self._hit_count += 1  # 同步维护本地计数器
            return value
        except KeyError:
            if self._enable_metrics:
                Metrics.cache_miss.add(1, {"type": "data_cache"})
            self._miss_count += 1  # 同步维护本地计数器
            return default

    def _get_with_custom_time(self, key: str, default: T | None) -> T | None:
        """使用自定义时间源获取缓存值（确定性 TTL 检查）."""
        # 类型缩窄：这些断言确保类型检查器知道变量不为 None
        assert self._ttl_entries is not None  # noqa: S101
        assert self._time_source is not None  # noqa: S101

        entry = self._ttl_entries.get(key)
        if entry is None:
            if self._enable_metrics:
                Metrics.cache_miss.add(1, {"type": "data_cache"})
            self._miss_count += 1
            return default

        # 检查是否过期
        current_time = self._time_source()
        if current_time >= entry.expire_at:
            # 过期，删除条目
            del self._ttl_entries[key]
            try:
                del self._cache[key]
            except KeyError:
                pass
            if self._enable_metrics:
                Metrics.cache_miss.add(1, {"type": "data_cache"})
            self._miss_count += 1
            return default

        # 未过期，返回值
        if self._enable_metrics:
            Metrics.cache_hit.add(1, {"type": "data_cache"})
        self._hit_count += 1
        return entry.value

    def set(self, key: str, value: T, ttl: int | None = None) -> None:
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
        # 使用自定义时间源模式：在 Python 层管理 TTL
        if self._ttl_entries is not None and self._time_source is not None:
            self._set_with_custom_time(key, value, ttl)
            return

        # 默认模式：使用 cachebox 的内置 TTL
        # 必须使用 insert() 方法并显式传递 TTL
        # ttl=None 时使用默认 TTL，ttl=0 时表示不设置过期时间
        if ttl is None:
            self._cache.insert(key, value, ttl=self._default_ttl)
        elif ttl == 0:
            # ttl=0 表示永不过期（不设置 TTL）
            self._cache.insert(key, value)
        else:
            self._cache.insert(key, value, ttl=ttl)

    def _set_with_custom_time(self, key: str, value: T, ttl: int | None) -> None:
        """使用自定义时间源设置缓存值."""
        # 类型缩窄：这些断言确保类型检查器知道变量不为 None
        assert self._ttl_entries is not None  # noqa: S101
        assert self._time_source is not None  # noqa: S101

        # 计算过期时间
        effective_ttl = self._default_ttl if ttl is None else ttl
        current_time = self._time_source()
        # ttl=0 表示永不过期，设置一个极大值
        expire_at = float("inf") if effective_ttl == 0 else current_time + effective_ttl

        # 存储 TTL 元数据
        self._ttl_entries[key] = _TTLEntry(value=value, expire_at=expire_at)

        # 同时存储到 cachebox（但禁用其 TTL，使用极大的值）
        # 这样可以保持 LRU 淘汰功能
        self._cache.insert(key, value, ttl=86400 * 365 * 10)  # 10 年

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
        # 清理 TTL 元数据
        if self._ttl_entries is not None and key in self._ttl_entries:
            del self._ttl_entries[key]

        try:
            del self._cache[key]
            if self._enable_metrics:
                Metrics.cache_invalidations.add(1)
            self._invalidation_count += 1  # 同步维护本地计数器
            return True
        except KeyError:
            return False

    def invalidate_pattern(self, pattern: str) -> int:
        """
        按模式批量失效缓存键.

        Args:
        ----
            pattern: fnmatch 风格模式（如 "instrument_id:*" 或 "trading_days:*"）

        Returns:
        -------
            失效的键数量

        """
        keys_to_delete = [k for k in self._cache if fnmatch.fnmatch(k, pattern)]
        for key in keys_to_delete:
            # 清理 TTL 元数据
            if self._ttl_entries is not None and key in self._ttl_entries:
                del self._ttl_entries[key]

            del self._cache[key]
            if self._enable_metrics:
                Metrics.cache_invalidations.add(1)
            self._invalidation_count += 1  # 同步维护本地计数器
        return len(keys_to_delete)

    def clear(self) -> None:
        """清空所有缓存."""
        self._cache.clear()
        if self._ttl_entries is not None:
            self._ttl_entries.clear()

    def get_stats(self) -> CacheStats:
        """
        获取缓存统计信息.

        Returns
        -------
            CacheStats: 包含命中率等统计信息

        """
        if self._ttl_entries is not None:
            total_entries = len(self._ttl_entries)
        else:
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
        if self._ttl_entries is not None:
            return len(self._ttl_entries)
        return len(self._cache)

    def __contains__(self, key: str) -> bool:
        """检查键是否存在于缓存中."""
        if self._ttl_entries is not None and self._time_source is not None:
            # 使用自定义时间源时，需要检查是否过期
            entry = self._ttl_entries.get(key)
            if entry is None:
                return False
            current_time = self._time_source()
            return current_time < entry.expire_at
        return key in self._cache
