"""
Data integrity error classes.

数据完整性类错误：数据存在性/覆盖度不满足计算契约时的 fail-closed
异常（区别于 network 的获取失败与 persistence 的写入失败）。
"""

from ditto_kernel.exceptions import DataError as _DataError


class AdjustmentFactorMissingError(_DataError):
    """
    复权因子缺失——复权计算拒绝产出失真值（fail closed，#514）.

    行级缺失 = (instrument_id, trade_date) 行关联不到因子；baseline
    缺失（仅 qfq）= 标的在 baseline 窗口内完全没有因子。消费方需要
    未复权价格时应显式请求 raw / adj=none。
    """
