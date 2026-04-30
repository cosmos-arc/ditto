"""Pratt parser for the derived expression language."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ditto_features.expression.ast import (
    BinaryOpNode,
    CallNode,
    ColumnRefNode,
    ExpressionNode,
    FeatureRefNode,
    IdentifierNode,
    NumberNode,
    StringNode,
    UnaryOpNode,
)
from ditto_features.expression.diagnostics import (
    Span,
    make_compile_error,
    merge_spans,
)
from ditto_features.expression.lexer import Token

__all__ = ["ExpressionParser"]


class PrefixParselet(Protocol):
    """Parse a prefix token in Pratt form."""

    def parse(self, parser: ExpressionParser, token: Token) -> ExpressionNode:
        """Parse one prefix expression."""
        ...


class InfixParselet(Protocol):
    """Parse an infix or postfix token in Pratt form."""

    @property
    def left_binding_power(self) -> int:
        """Return the left binding power for Pratt dispatch."""
        ...

    def parse(
        self,
        parser: ExpressionParser,
        left: ExpressionNode,
        token: Token,
    ) -> ExpressionNode:
        """Parse one infix or postfix continuation."""
        ...


@dataclass(frozen=True)
class NumberParselet:
    """Parse numeric literals."""

    def parse(self, parser: ExpressionParser, token: Token) -> ExpressionNode:
        del parser
        return NumberNode(value=float(token.value), span=token.span)


@dataclass(frozen=True)
class StringParselet:
    """Parse string literals."""

    def parse(self, parser: ExpressionParser, token: Token) -> ExpressionNode:
        del parser
        return StringNode(value=token.value, span=token.span)


@dataclass(frozen=True)
class IdentifierParselet:
    """Parse identifiers before postfix parselets extend them."""

    def parse(self, parser: ExpressionParser, token: Token) -> ExpressionNode:
        del parser
        return IdentifierNode(name=token.value, span=token.span)


@dataclass(frozen=True)
class GroupingParselet:
    """Parse parenthesized subexpressions."""

    def parse(self, parser: ExpressionParser, token: Token) -> ExpressionNode:
        del token
        expression = parser.parse_subexpression(0)
        parser.expect_token("OP", ")")
        return expression


@dataclass(frozen=True)
class FeatureRefParselet:
    """Parse feature refs prefixed with @."""

    def parse(self, parser: ExpressionParser, token: Token) -> ExpressionNode:
        identifier = parser.expect_token("IDENT")
        name_parts = [identifier.value]
        end_span = identifier.span
        while parser.peek_token().value == ".":
            parser.advance_token()
            identifier = parser.expect_token("IDENT")
            name_parts.append(identifier.value)
            end_span = identifier.span
        return FeatureRefNode(
            name=".".join(name_parts),
            span=merge_spans(token.span, end_span),
        )


@dataclass(frozen=True)
class PrefixOperatorParselet:
    """Parse unary prefix operators."""

    operator: str
    binding_power: int

    def parse(self, parser: ExpressionParser, token: Token) -> ExpressionNode:
        operand = parser.parse_subexpression(self.binding_power)
        return UnaryOpNode(
            operator=self.operator,
            operand=operand,
            span=merge_spans(token.span, operand.span),
        )


@dataclass(frozen=True)
class BinaryOperatorParselet:
    """Parse left- or right-associative binary operators."""

    operator: str
    binding_power: int
    right_associative: bool = False

    @property
    def left_binding_power(self) -> int:
        return self.binding_power

    def parse(
        self,
        parser: ExpressionParser,
        left: ExpressionNode,
        token: Token,
    ) -> ExpressionNode:
        del token
        right_binding_power = (
            self.binding_power - 1 if self.right_associative else self.binding_power
        )
        right = parser.parse_subexpression(right_binding_power)
        return BinaryOpNode(
            operator=self.operator,
            left=left,
            right=right,
            span=merge_spans(left.span, right.span),
        )


@dataclass(frozen=True)
class CallParselet:
    """Parse postfix function calls."""

    binding_power: int = 70

    @property
    def left_binding_power(self) -> int:
        return self.binding_power

    def parse(
        self,
        parser: ExpressionParser,
        left: ExpressionNode,
        token: Token,
    ) -> ExpressionNode:
        if not isinstance(left, IdentifierNode):
            parser.raise_syntax_error(
                message="function call target must be an identifier",
                error_code="E013_INVALID_CALL_TARGET",
                span=merge_spans(left.span, token.span),
            )
            raise AssertionError("unreachable")
        identifier = left
        arguments: list[ExpressionNode] = []
        closing = parser.peek_token()
        if closing.value != ")":
            while True:
                arguments.append(parser.parse_subexpression(0))
                if parser.peek_token().value == ",":
                    parser.advance_token()
                    continue
                break
        closing = parser.expect_token("OP", ")")
        return CallNode(
            name=identifier.name,
            arguments=tuple(arguments),
            span=merge_spans(identifier.span, closing.span),
        )


@dataclass(frozen=True)
class ColumnRefParselet:
    """Parse dataset.column references."""

    binding_power: int = 70

    @property
    def left_binding_power(self) -> int:
        return self.binding_power

    def parse(
        self,
        parser: ExpressionParser,
        left: ExpressionNode,
        token: Token,
    ) -> ExpressionNode:
        if not isinstance(left, IdentifierNode):
            parser.raise_syntax_error(
                message="left side of '.' must be an identifier",
                error_code="E014_INVALID_MEMBER_ACCESS",
                span=merge_spans(left.span, token.span),
            )
            raise AssertionError("unreachable")
        identifier = left
        column = parser.expect_token("IDENT")
        return ColumnRefNode(
            dataset=identifier.name,
            column=column.value,
            span=merge_spans(identifier.span, column.span),
        )


_PREFIX_PARSELETS: dict[str, PrefixParselet] = {
    "NUMBER": NumberParselet(),
    "STRING": StringParselet(),
    "IDENT": IdentifierParselet(),
    "(": GroupingParselet(),
    "@": FeatureRefParselet(),
    "-": PrefixOperatorParselet(operator="-", binding_power=50),
    "not": PrefixOperatorParselet(operator="not", binding_power=15),
}

_INFIX_PARSELETS: dict[str, InfixParselet] = {
    "(": CallParselet(),
    ".": ColumnRefParselet(),
    "or": BinaryOperatorParselet(operator="or", binding_power=5),
    "and": BinaryOperatorParselet(operator="and", binding_power=10),
    "==": BinaryOperatorParselet(operator="==", binding_power=20),
    "!=": BinaryOperatorParselet(operator="!=", binding_power=20),
    "<": BinaryOperatorParselet(operator="<", binding_power=20),
    "<=": BinaryOperatorParselet(operator="<=", binding_power=20),
    ">": BinaryOperatorParselet(operator=">", binding_power=20),
    ">=": BinaryOperatorParselet(operator=">=", binding_power=20),
    "+": BinaryOperatorParselet(operator="+", binding_power=30),
    "-": BinaryOperatorParselet(operator="-", binding_power=30),
    "*": BinaryOperatorParselet(operator="*", binding_power=40),
    "/": BinaryOperatorParselet(operator="/", binding_power=40),
}


class ExpressionParser:
    """Parse tokens into an expression AST."""

    def __init__(self, tokens: tuple[Token, ...], source: str) -> None:
        self._tokens = tokens
        self._source = source
        self._index = 0
        self._prefix_parselets = dict(_PREFIX_PARSELETS)
        self._infix_parselets = dict(_INFIX_PARSELETS)

    def parse(self) -> ExpressionNode:
        """Parse the full expression."""
        expression = self._parse_expression(0)
        self.expect_token("EOF")
        return expression

    def parse_subexpression(self, min_binding_power: int) -> ExpressionNode:
        """Public Pratt helper used by parselets for recursive descent."""
        return self._parse_expression(min_binding_power)

    def peek_token(self) -> Token:
        """Public Pratt helper used by parselets for lookahead."""
        return self._peek()

    def advance_token(self) -> Token:
        """Public Pratt helper used by parselets for token consumption."""
        return self._advance()

    def expect_token(self, kind: str, value: str | None = None) -> Token:
        """Public Pratt helper used by parselets for delimiter checks."""
        return self._expect(kind, value)

    def raise_syntax_error(
        self,
        *,
        message: str,
        error_code: str,
        span: Span,
    ) -> None:
        """Raise a structured parser error."""
        raise make_compile_error(
            source=self._source,
            message=message,
            error_code=error_code,
            span=span,
        )

    def _parse_expression(self, min_binding_power: int) -> ExpressionNode:
        token = self._advance()
        prefix_parselet = self._get_prefix_parselet(token)
        left = prefix_parselet.parse(self, token)
        while True:
            next_token = self._peek()
            infix_parselet = self._infix_parselets.get(next_token.value)
            if infix_parselet is None:
                break
            if min_binding_power >= infix_parselet.left_binding_power:
                break
            left = infix_parselet.parse(self, left, self._advance())
        return left

    def _get_prefix_parselet(self, token: Token) -> PrefixParselet:
        parselet = self._prefix_parselets.get(token.kind)
        if parselet is not None:
            return parselet
        parselet = self._prefix_parselets.get(token.value)
        if parselet is not None:
            return parselet
        self.raise_syntax_error(
            message=(
                f"unexpected token while parsing expression: {token.value or 'EOF'}"
            ),
            error_code="E011_UNEXPECTED_TOKEN",
            span=token.span,
        )
        raise AssertionError("unreachable")

    def _peek(self) -> Token:
        return self._tokens[self._index]

    def _advance(self) -> Token:
        token = self._tokens[self._index]
        self._index += 1
        return token

    def _expect(self, kind: str, value: str | None = None) -> Token:
        token = self._advance()
        if token.kind != kind or (value is not None and token.value != value):
            expected = f"{kind}:{value}" if value is not None else kind
            self.raise_syntax_error(
                message=f"expected {expected}, got {token.kind}:{token.value or 'EOF'}",
                error_code="E012_EXPECTED_TOKEN",
                span=token.span,
            )
        return token
