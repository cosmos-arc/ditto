"""Tushare rate limiting using limits library."""

from dataclasses import dataclass
from enum import Enum

from limits import parse, storage, strategies


# ============ API 端点分组 ============
class TushareAPIGroup(Enum):
    """Tushare API 分组（用于不同限流策略）."""

    BASIC = "basic"  # 基础接口（trade_cal, pro_bar等）
    DAILY = "daily"  # 日线数据接口
    DERIVED = "derived"  # 衍生数据接口
    SPECIAL = "special"  # 特殊接口（限流更严格）


# ============ 限流配置预设 ============
@dataclass(frozen=True)
class TushareRateLimitConfig:
    """Tushare 限流配置."""

    # 全局限流（所有请求）
    global_rate: int = 200  # 请求/分钟
    global_window: int = 60  # 秒

    # 分组限流
    daily_rate: int = 100  # 日线接口限制
    daily_window: int = 60

    derived_rate: int = 50  # 衍生接口限制
    derived_window: int = 60

    special_rate: int = 20  # 特殊接口限制
    special_window: int = 60

    # 预设配置
    @classmethod
    def free(cls) -> "TushareRateLimitConfig":
        """免费账户配置（保守）."""
        return cls(
            global_rate=200,
            daily_rate=100,
            derived_rate=50,
            special_rate=20,
        )

    @classmethod
    def paid(cls) -> "TushareRateLimitConfig":
        """付费账户配置（宽松）."""
        return cls(
            global_rate=1000,
            daily_rate=500,
            derived_rate=200,
            special_rate=100,
        )

    @classmethod
    def conservative(cls) -> "TushareRateLimitConfig":
        """超保守配置（避免触发限流）."""
        return cls(
            global_rate=150,
            daily_rate=80,
            derived_rate=30,
            special_rate=10,
        )


# ============ 限流器管理器 ============
class TushareRateLimiter:
    """Tushare 限流器（基于 limits 库）."""

    def __init__(self, config: TushareRateLimitConfig) -> None:
        """
        初始化限流器.

        Args:
            config: 限流配置

        """
        self._config = config

        # 初始化存储后端
        memory_storage = storage.MemoryStorage()

        # 初始化策略（使用滑动窗口）
        self._limiter = strategies.MovingWindowRateLimiter(memory_storage)

        # 解析速率限制规则（字符串表示法）
        self._global_rate = parse(f"{config.global_rate}/{config.global_window}seconds")
        self._daily_rate = parse(f"{config.daily_rate}/{config.daily_window}seconds")
        self._derived_rate = parse(
            f"{config.derived_rate}/{config.derived_window}seconds"
        )
        self._special_rate = parse(
            f"{config.special_rate}/{config.special_window}seconds"
        )

    def check_limit(self, group: TushareAPIGroup) -> bool:
        """
        检查是否超过限流.

        Args:
            group: API 分组

        Returns:
            True if under limit, False otherwise

        """
        # 检查全局限流
        if not self._limiter.hit(self._global_rate, "tushare", "global"):
            return False

        # 检查分组限流
        rate = {
            TushareAPIGroup.BASIC: self._global_rate,
            TushareAPIGroup.DAILY: self._daily_rate,
            TushareAPIGroup.DERIVED: self._derived_rate,
            TushareAPIGroup.SPECIAL: self._special_rate,
        }[group]

        return self._limiter.hit(rate, "tushare", group.value)

    def wait_if_needed(self, group: TushareAPIGroup) -> None:
        """等待直到可以请求."""
        rate = {
            TushareAPIGroup.BASIC: self._global_rate,
            TushareAPIGroup.DAILY: self._daily_rate,
            TushareAPIGroup.DERIVED: self._derived_rate,
            TushareAPIGroup.SPECIAL: self._special_rate,
        }[group]

        # 使用 test() 检查但不消耗，等待直到可以请求
        import time

        while not self._limiter.test(rate, "tushare", group.value):
            time.sleep(0.1)  # 短暂等待后重试

        # 消耗一次额度
        self._limiter.hit(rate, "tushare", group.value)
