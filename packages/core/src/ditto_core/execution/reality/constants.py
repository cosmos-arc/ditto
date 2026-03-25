"""执行层默认常量。"""

__all__ = [
    "DEFAULT_COMMISSION_RATE",
    "DEFAULT_LOT_SIZE",
    "DEFAULT_MIN_COMMISSION",
]

DEFAULT_COMMISSION_RATE: float = 0.0003
"""默认佣金费率(万分之三)。"""

DEFAULT_MIN_COMMISSION: float = 5.0
"""最低佣金(元)。"""

DEFAULT_LOT_SIZE: int = 100
"""默认最小交易单位(A股一手 = 100 股)。"""
