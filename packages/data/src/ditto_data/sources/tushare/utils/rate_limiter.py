"""Tushare rate limiting using limits library."""

import time
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
    """
    Tushare 限流配置.

    档位按 transport 权益区分（#431，官方积分频次表 doc_id=290）：

    - ``free``/``paid`` 是代理 transport（t.xiaodefa.top）承诺的档位
      （200/1000 每分钟），不是官方账号积分档，不得冒充；代理 paid 的
      1000/分高于官方任何积分档（15000 积分为 500/分）。
    - 官方直连账号用 ``official_120``（120 积分 50/分）或
      ``official_15000``（15000 积分 500/分）；官方表只给每分钟总额，
      未核实的接口级细分不虚构，分组限流等于全局值。
    - 实际账号权益以实测为准；已知文档冲突（index_dailybasic 专页 2000
      积分与积分总目录 4000 积分不一致）如实记录，不择一宣称。

    Attributes:
        global_rate: 全局每窗口请求数（所有请求）.
        global_window: 全局窗口秒数.
        daily_rate: 日线接口组每窗口请求数.
        daily_window: 日线接口组窗口秒数.
        derived_rate: 衍生接口组每窗口请求数.
        derived_window: 衍生接口组窗口秒数.
        special_rate: 特殊接口组每窗口请求数.
        special_window: 特殊接口组窗口秒数.

    """

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

    # 预设配置（代理 transport 档位）
    @classmethod
    def free(cls) -> "TushareRateLimitConfig":
        """代理 transport 免费档（200/分，保守）."""
        return cls(
            global_rate=200,
            daily_rate=100,
            derived_rate=50,
            special_rate=20,
        )

    @classmethod
    def paid(cls) -> "TushareRateLimitConfig":
        """
        代理 transport 付费档（1000/分，宽松）.

        注意：高于官方 15000 积分档的 500/分；账号实际积分档为 15000 时
        应选 ``official_15000`` 或显式覆盖 global_rate。
        """
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

    # 预设配置（官方直连账号积分档）
    @classmethod
    def official_120(cls) -> "TushareRateLimitConfig":
        """官方 120 积分档（50/分）."""
        return cls(
            global_rate=50,
            daily_rate=50,
            derived_rate=50,
            special_rate=50,
        )

    @classmethod
    def official_15000(cls) -> "TushareRateLimitConfig":
        """官方 15000 积分档（500/分）."""
        return cls(
            global_rate=500,
            daily_rate=500,
            derived_rate=500,
            special_rate=500,
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
        while True:
            # 同时检查全局限流和分组限流
            global_ok = self._limiter.test(self._global_rate, "tushare", "global")
            group_ok = self._limiter.test(rate, "tushare", group.value)

            if global_ok and group_ok:
                break

            time.sleep(0.1)  # 短暂等待后重试

        # 消费全局限流额度
        self._limiter.hit(self._global_rate, "tushare", "global")
        # 消费分组限流额度
        self._limiter.hit(rate, "tushare", group.value)
