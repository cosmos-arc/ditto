"""
共享身份类型.

Ditto 内部 canonical 主键的类型安全包装。
"""

from typing import NewType

__all__ = ["InstrumentId"]

InstrumentId = NewType("InstrumentId", int)
