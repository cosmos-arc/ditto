"""
AI 假设 → Expression 桥接点。

提供 Hypothesis 数据模型与 hypothesis_to_expression 占位实现，
使 AI 生成的投资假设可进入 Features 表达式编译管线。
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = [
    "Hypothesis",
    "hypothesis_to_expression",
]


@dataclass(frozen=True)
class Hypothesis:
    """
    AI 生成的投资假设，可转化为表达式。

    Attributes:
        natural_language: 自然语言描述的投资假设。
        expression_draft: 对应的表达式草稿字符串。
        metadata: 来源、置信度等附加信息。

    """

    natural_language: str
    expression_draft: str
    metadata: dict[str, str] = field(default_factory=dict)


def hypothesis_to_expression(hypothesis: Hypothesis) -> str:
    """
    将假设转化为可编译的表达式。

    当前为占位实现，直接透传 expression_draft。

    Args:
        hypothesis: AI 生成的投资假设。

    Returns:
        可被 ExpressionCompiler 编译的表达式字符串。

    """
    return hypothesis.expression_draft
