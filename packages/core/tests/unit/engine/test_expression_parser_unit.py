"""Parser-level tests for the Pratt expression parser."""

from __future__ import annotations

from ditto_core.engine.expression.ast import (
    BinaryOpNode,
    CallNode,
    ColumnRefNode,
    FeatureRefNode,
    NumberNode,
    StringNode,
    UnaryOpNode,
)
from ditto_core.engine.expression.lexer import tokenize
from ditto_core.engine.expression.parser import ExpressionParser


class TestExpressionParser:
    """Tests for the Pratt parser structure and AST output."""

    def test_parser_keeps_explicit_pratt_parselet_tables(self) -> None:
        """Parser should expose dedicated prefix/infix parselet registries."""
        source = 'abs(market.close) + "x"'
        parser = ExpressionParser(tokenize(source), source)

        assert "NUMBER" in parser._prefix_parselets
        assert "IDENT" in parser._prefix_parselets
        assert "STRING" in parser._prefix_parselets
        assert "(" in parser._prefix_parselets
        assert "@" in parser._prefix_parselets
        assert "-" in parser._prefix_parselets
        assert "not" in parser._prefix_parselets
        assert "(" in parser._infix_parselets
        assert "." in parser._infix_parselets
        assert "and" in parser._infix_parselets
        assert "or" in parser._infix_parselets
        assert "+" in parser._infix_parselets
        assert "*" in parser._infix_parselets

    def test_parse_respects_precedence_and_left_associativity(self) -> None:
        """Higher-precedence infix operators should bind on the right subtree."""
        source = "market.close + market.volume * 2"
        ast = ExpressionParser(tokenize(source), source).parse()

        assert isinstance(ast, BinaryOpNode)
        assert ast.operator == "+"
        assert isinstance(ast.left, ColumnRefNode)
        assert ast.left.dataset == "market"
        assert ast.left.column == "close"
        assert isinstance(ast.right, BinaryOpNode)
        assert ast.right.operator == "*"
        assert isinstance(ast.right.left, ColumnRefNode)
        assert ast.right.left.dataset == "market"
        assert ast.right.left.column == "volume"
        assert isinstance(ast.right.right, NumberNode)
        assert ast.right.right.value == 2.0

    def test_parse_treats_function_call_as_postfix_parselet(self) -> None:
        """Function calls should be parsed through the Pratt infix/postfix path."""
        source = "-abs(market.close)"
        ast = ExpressionParser(tokenize(source), source).parse()

        assert isinstance(ast, UnaryOpNode)
        assert ast.operator == "-"
        assert isinstance(ast.operand, CallNode)
        assert ast.operand.name == "abs"
        assert len(ast.operand.arguments) == 1
        assert isinstance(ast.operand.arguments[0], ColumnRefNode)
        assert ast.operand.arguments[0].dataset == "market"
        assert ast.operand.arguments[0].column == "close"

    def test_parse_supports_feature_refs_string_literals_and_logical_ops(self) -> None:
        """Parser should support feature refs, strings, and boolean precedence."""
        source = 'if_else(@alpha_state == "halt" or not market.close > 10, 1, 0)'
        ast = ExpressionParser(tokenize(source), source).parse()

        assert isinstance(ast, CallNode)
        assert ast.name == "if_else"
        assert len(ast.arguments) == 3

        condition = ast.arguments[0]
        assert isinstance(condition, BinaryOpNode)
        assert condition.operator == "or"

        left = condition.left
        assert isinstance(left, BinaryOpNode)
        assert left.operator == "=="
        assert isinstance(left.left, FeatureRefNode)
        assert left.left.name == "alpha_state"
        assert isinstance(left.right, StringNode)
        assert left.right.value == "halt"

        right = condition.right
        assert isinstance(right, UnaryOpNode)
        assert right.operator == "not"
        assert isinstance(right.operand, BinaryOpNode)
        assert right.operand.operator == ">"
        assert isinstance(right.operand.left, ColumnRefNode)
        assert right.operand.left.dataset == "market"
        assert right.operand.left.column == "close"
        assert isinstance(right.operand.right, NumberNode)
        assert right.operand.right.value == 10.0

    def test_parse_supports_dotted_feature_refs(self) -> None:
        """Derived ids containing dots should remain valid after the @ prefix."""
        source = "@factor.alpha_upstream"
        ast = ExpressionParser(tokenize(source), source).parse()

        assert isinstance(ast, FeatureRefNode)
        assert ast.name == "factor.alpha_upstream"
