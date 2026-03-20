"""AST nodes for the derived expression language."""

from __future__ import annotations

from dataclasses import dataclass

from ditto_core.engine.expression.diagnostics import Span

__all__ = [
    "BinaryOpNode",
    "CallNode",
    "ColumnRefNode",
    "ExpressionNode",
    "FeatureRefNode",
    "IdentifierNode",
    "NumberNode",
    "StringNode",
    "UnaryOpNode",
]


@dataclass(frozen=True)
class IdentifierNode:
    """Identifier or dependency reference."""

    name: str
    span: Span


@dataclass(frozen=True)
class ColumnRefNode:
    """Qualified dataset column reference."""

    dataset: str
    column: str
    span: Span


@dataclass(frozen=True)
class FeatureRefNode:
    """Derived dependency reference using the @ prefix."""

    name: str
    span: Span


@dataclass(frozen=True)
class NumberNode:
    """Numeric literal."""

    value: float
    span: Span


@dataclass(frozen=True)
class StringNode:
    """String literal."""

    value: str
    span: Span


@dataclass(frozen=True)
class UnaryOpNode:
    """Unary operator node."""

    operator: str
    operand: ExpressionNode
    span: Span


@dataclass(frozen=True)
class BinaryOpNode:
    """Binary operator node."""

    operator: str
    left: ExpressionNode
    right: ExpressionNode
    span: Span


@dataclass(frozen=True)
class CallNode:
    """Function call node."""

    name: str
    arguments: tuple[ExpressionNode, ...]
    span: Span


type ExpressionNode = (
    IdentifierNode
    | ColumnRefNode
    | FeatureRefNode
    | NumberNode
    | StringNode
    | UnaryOpNode
    | BinaryOpNode
    | CallNode
)
