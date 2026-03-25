"""
Ditto 共享内核 — 跨层领域原语.

提供跨层共享的纯类型定义（枚举、NewType、值对象）。
零业务行为、零外部依赖、零 I/O。

准入标准（5 条，全部满足才可进入）：
1. 跨层使用：至少被 2 个业务包直接导入
2. 零业务行为：纯值对象 / 枚举 / NewType
3. 稳定性高：不会随某个子域的迭代频繁变更
4. 无外部依赖：只依赖 Python 标准库
5. 纯值语义：不含序列化、持久化关注点
"""

__version__ = "0.1.0"

from ditto_kernel.enums import AssetClass, Exchange, OrderSide, RunStatus
from ditto_kernel.identity import InstrumentId

__all__ = [
    "AssetClass",
    "Exchange",
    "InstrumentId",
    "OrderSide",
    "RunStatus",
]
