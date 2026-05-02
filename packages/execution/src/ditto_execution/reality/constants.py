"""执行层默认常量（从 kernel re-export）。"""

from ditto_kernel.trading import (
    DEFAULT_COMMISSION_RATE,
    DEFAULT_LOT_SIZE,
    DEFAULT_MIN_COMMISSION,
)

__all__ = [
    "DEFAULT_COMMISSION_RATE",
    "DEFAULT_LOT_SIZE",
    "DEFAULT_MIN_COMMISSION",
]
