"""宏观指标枚举与模型定义。"""

from __future__ import annotations

from dataclasses import dataclass

from ditto_kernel.market import MacroCategory, MacroFrequency


@dataclass(frozen=True)
class IndicatorMetadataSpec:
    """宏观指标元数据写入规格。"""

    code: str
    name: str
    category: MacroCategory
    frequency: MacroFrequency
    need_pit: bool
    source: str | None = None
    unit: str | None = None
    description: str | None = None


__all__ = ["IndicatorMetadataSpec", "MacroCategory", "MacroFrequency"]
