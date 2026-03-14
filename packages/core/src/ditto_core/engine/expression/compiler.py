"""Unified expression compiler."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from hashlib import sha256

import orjson
import polars as pl

from ditto_core.engine.expression.analyzer import analyze_expression
from ditto_core.engine.expression.ast import (
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
from ditto_core.engine.expression.codegen import compile_expression
from ditto_core.engine.expression.diagnostics import make_compile_error
from ditto_core.engine.expression.lexer import tokenize
from ditto_core.engine.expression.parser import ExpressionParser
from ditto_core.engine.expression.registry import P0_OPERATOR_VERSIONS
from ditto_core.engine.materialization.contracts import (
    CompiledDerivedExpression,
    CompileIdentity,
)
from ditto_core.engine.specs import DerivedSpec

__all__ = ["ExpressionCompiler"]

_ANALYSIS_VERSION = "analysis-v1"
_CODEGEN_VERSION = "expr-v1"
_EXPR_SERIALIZATION_FORMAT = "polars-expr-v1"
_MAX_EXPRESSION_LENGTH = 500
_MAX_EXPRESSION_DEPTH = 10
_MAX_EXPRESSION_NODES = 100
_MAX_LOOKBACK = 252


class ExpressionCompiler:
    """Compile a derived expression into executable Polars state."""

    def compile(self, spec: DerivedSpec) -> CompiledDerivedExpression:
        """Compile one spec into a Polars expression and compile identity."""
        spec.validate_spec()
        tokens = tokenize(spec.expression)
        ast = ExpressionParser(tokens, spec.expression).parse()
        analysis = analyze_expression(ast)
        self._enforce_limits(spec.expression, ast, analysis.lookback)
        expr = compile_expression(ast, spec, source=spec.expression)

        operator_versions = tuple(
            sorted(
                (
                    name,
                    spec.operator_versions.get(name, P0_OPERATOR_VERSIONS[name]),
                )
                for name in analysis.operator_names
            )
        )
        operator_fingerprint = _hash_payload(operator_versions)
        compile_input_hash = _hash_payload(
            {
                "id": spec.id,
                "version": spec.version,
                "expression": spec.expression,
                "entity_keys": spec.entity_keys,
                "time_keys": spec.effective_time_keys,
                "profile": spec.materialization_profile.value,
                "pit_required": spec.pit_required,
                "normalization_preset": spec.normalization_preset,
                "operator_versions": operator_versions,
            }
        )
        compiler_fingerprint = _hash_payload(
            {
                "engine_codegen_version": _CODEGEN_VERSION,
                "analysis_version": _ANALYSIS_VERSION,
                "polars_version": pl.__version__,
                "expr_serialization_format": _EXPR_SERIALIZATION_FORMAT,
                "operator_fingerprint": operator_fingerprint,
                "global_compile_flags": ("grain=1d", "entity_key=instrument_id"),
            }
        )
        cache_key = _hash_payload((compile_input_hash, compiler_fingerprint))
        compile_identity = CompileIdentity(
            compile_input_hash=compile_input_hash,
            operator_fingerprint=operator_fingerprint,
            compiler_fingerprint=compiler_fingerprint,
            cache_key=cache_key,
            engine_codegen_version=_CODEGEN_VERSION,
            analysis_version=_ANALYSIS_VERSION,
            polars_version=pl.__version__,
            expr_serialization_format=_EXPR_SERIALIZATION_FORMAT,
            operator_versions=operator_versions,
            global_compile_flags=("grain=1d", "entity_key=instrument_id"),
        )
        return CompiledDerivedExpression(
            derived_id=spec.id,
            version=spec.version,
            expr=expr,
            analysis=analysis,
            compile_identity=compile_identity,
        )

    def _enforce_limits(
        self,
        source: str,
        expression: ExpressionNode,
        lookback: int,
    ) -> None:
        if len(source) > _MAX_EXPRESSION_LENGTH:
            raise make_compile_error(
                source=source,
                message=f"expression exceeds max_length={_MAX_EXPRESSION_LENGTH}",
                error_code="E041_EXPRESSION_TOO_LONG",
                span=expression.span,
            )
        depth, nodes = _measure_expression(expression)
        if depth > _MAX_EXPRESSION_DEPTH:
            raise make_compile_error(
                source=source,
                message=f"expression exceeds max_depth={_MAX_EXPRESSION_DEPTH}",
                error_code="E042_EXPRESSION_TOO_DEEP",
                span=expression.span,
            )
        if nodes > _MAX_EXPRESSION_NODES:
            raise make_compile_error(
                source=source,
                message=f"expression exceeds max_nodes={_MAX_EXPRESSION_NODES}",
                error_code="E043_EXPRESSION_TOO_LARGE",
                span=expression.span,
            )
        if lookback > _MAX_LOOKBACK:
            raise make_compile_error(
                source=source,
                message=f"expression exceeds max_lookback={_MAX_LOOKBACK}",
                error_code="E044_LOOKBACK_TOO_LARGE",
                span=expression.span,
            )


def _hash_payload(payload: object) -> str:
    """Hash a deterministic ORJSON payload."""
    encoded = orjson.dumps(
        payload,
        option=orjson.OPT_SORT_KEYS,
        default=_serialize_hash_value,
    )
    return sha256(encoded).hexdigest()


def _serialize_hash_value(value: object) -> object:
    """Serialize dataclasses while hashing compile metadata."""
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    return value


def _measure_expression(expression: ExpressionNode) -> tuple[int, int]:
    match expression:
        case (
            IdentifierNode()
            | ColumnRefNode()
            | FeatureRefNode()
            | NumberNode()
            | StringNode()
        ):
            return (1, 1)
        case UnaryOpNode(operand=operand):
            depth, nodes = _measure_expression(operand)
            return (depth + 1, nodes + 1)
        case BinaryOpNode(left=left, right=right):
            left_depth, left_nodes = _measure_expression(left)
            right_depth, right_nodes = _measure_expression(right)
            return (max(left_depth, right_depth) + 1, left_nodes + right_nodes + 1)
        case CallNode(arguments=arguments):
            max_depth = 0
            total_nodes = 1
            for argument in arguments:
                depth, nodes = _measure_expression(argument)
                max_depth = max(max_depth, depth)
                total_nodes += nodes
            return (max_depth + 1, total_nodes)
    raise ValueError(f"unsupported expression node: {expression!r}")
