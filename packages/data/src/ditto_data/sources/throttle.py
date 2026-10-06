"""
最小间隔节流器 — 数据源 client 共享的请求起点间隔下限实现（#516）.

FRED（官方 2 req/s）与 fuyao（限流后自适应降频）共用的唯一权威实现；
``min_interval`` 为可变属性，供限流退避路径运行时上调（fuyao），0 表示禁用.
"""

from __future__ import annotations

import time


class MinIntervalThrottle:
    """把相邻请求起点间隔压到 ``min_interval`` 以上（monotonic 时钟）."""

    def __init__(self, min_interval: float) -> None:
        self.min_interval = max(0.0, min_interval)
        self._last_request_monotonic: float | None = None

    def wait(self) -> None:
        """阻塞到距上次请求起点满 ``min_interval``；记录本次起点."""
        if self.min_interval <= 0:
            return
        now = time.monotonic()
        if self._last_request_monotonic is not None:
            remaining = self.min_interval - (now - self._last_request_monotonic)
            if remaining > 0:
                time.sleep(remaining)
        # 起点=请求发起时刻：即使请求随后失败也计入间隔（失败重试同样限频）
        self._last_request_monotonic = time.monotonic()
