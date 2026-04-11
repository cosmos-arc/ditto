"""
人工执行闭环 — App 层 DTO + 跨层映射函数.

DTO 和映射函数已迁移到 ditto_app.types（包根目录），
以规避 R8 互斥规则（query 禁止导入 process）。
本模块保留 re-export 以保持向后兼容。
"""

from __future__ import annotations

from ditto_app.types import (
    ActualPositionSnapshot,
    ManualExecutionFill,
    TradeIntent,
    fill_to_record,
    intent_to_record,
    record_to_fill,
    record_to_intent,
    record_to_snapshot,
    snapshot_to_record,
)

__all__ = [
    "ActualPositionSnapshot",
    "ManualExecutionFill",
    "TradeIntent",
    "fill_to_record",
    "intent_to_record",
    "record_to_fill",
    "record_to_intent",
    "record_to_snapshot",
    "snapshot_to_record",
]
