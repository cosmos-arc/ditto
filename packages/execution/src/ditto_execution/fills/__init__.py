"""
Fills — 成交处理与结果模型。

管理成交结果（Filled / NoFill / PartialFill）的定义与分发，
包括成交确认、成交匹配和成交事件发布。
通过 outcomes.py 定义标准成交结果类型。

此模块为占位符，定义了未来能力扩展的目标结构。
当前不应删除 — 由能力包架构计划保留。
"""

from ditto_execution.fills.outcomes import Filled, FillOutcome, NoFill

__all__ = [
    "FillOutcome",
    "Filled",
    "NoFill",
]
