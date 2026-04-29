"""Unified expression compiler."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from hashlib import sha256

import orjson
import polars as pl
from ditto_kernel.strategy import DerivedSpec
from ditto_kernel.tracing import traced

from ditto_analytics.expression.analyzer import analyze_expression
from ditto_analytics.expression.ast import (
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
from ditto_analytics.expression.codegen import compile_expression
from ditto_analytics.expression.contracts import (
    Analysis,
    CompiledDerivedExpression,
    CompileIdentity,
)
from ditto_analytics.expression.diagnostics import make_compile_error
from ditto_analytics.expression.lexer import tokenize
from ditto_analytics.expression.parser import ExpressionParser
from ditto_analytics.expression.registry import P0_OPERATOR_VERSIONS
from ditto_analytics.validation import validate_derived_spec

__all__ = [
    "ExpressionCompiler",
    "compute_compile_cache_key",
    "detect_dependency_cycles",
]

_ANALYSIS_VERSION = "analysis-v1"
_CODEGEN_VERSION = "expr-v1"
_EXPR_SERIALIZATION_FORMAT = "polars-expr-v1"
_MAX_EXPRESSION_LENGTH = 500
_MAX_EXPRESSION_DEPTH = 10
_MAX_EXPRESSION_NODES = 100
_MAX_LOOKBACK = 252


def compute_compile_cache_key(
    spec: DerivedSpec,
) -> tuple[str, Analysis, CompileIdentity, ExpressionNode]:
    """
    Compute the cache key for a spec without performing codegen.

    Returns a ``(cache_key, analysis, compile_identity, ast)`` tuple.
    The expression is parsed and analysed so that operator versions can be
    resolved, but no Polars expression is generated.  The parsed AST is
    returned so callers can avoid double-parsing on cache hits.
    """
    validate_derived_spec(spec)
    tokens = tokenize(spec.expression)
    ast = ExpressionParser(tokens, spec.expression).parse()
    analysis = analyze_expression(ast)

    operator_versions = tuple(
        sorted(
            (
                name,
                spec.operator_versions.get(
                    name, P0_OPERATOR_VERSIONS.get(name, "unknown")
                ),
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
    return cache_key, analysis, compile_identity, ast


class ExpressionCompiler:
    """Compile a derived expression into executable Polars state."""

    @traced("analytics.expression.compile")
    def compile(
        self,
        spec: DerivedSpec,
        *,
        ast: ExpressionNode | None = None,
    ) -> CompiledDerivedExpression:
        """Compile one spec into a Polars expression and compile identity."""
        _cache_key, analysis, compile_identity, parsed_ast = compute_compile_cache_key(
            spec
        )

        ast_to_use = ast if ast is not None else parsed_ast
        self._enforce_limits(spec.expression, ast_to_use, analysis.lookback)
        expr = compile_expression(ast_to_use, spec, source=spec.expression)

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


def detect_dependency_cycles(
    graph: dict[str, tuple[str, ...]],
) -> None:
    """
    Detect cycles in a dependency graph using Kahn's algorithm.

    Parameters
    ----------
    graph:
        Mapping of node name to its dependency list.  The key is the node
        identifier and the value is a tuple of nodes it depends on.

    Raises
    ------
    ValueError
        If a cycle is detected.  The message includes the names of the
        nodes involved in the cycle.

    """
    in_degree: dict[str, int] = dict.fromkeys(graph, 0)
    # Build adjacency list (node -> dependents) and compute in-degrees.
    dependents: dict[str, list[str]] = {node: [] for node in graph}
    for node, deps in graph.items():
        for dep in deps:
            if dep not in graph:
                # External dependency (e.g. market.close), skip.
                continue
            in_degree[node] = in_degree.get(node, 0) + 1
            dependents.setdefault(dep, []).append(node)

    # Start with nodes that have zero in-degree (no internal dependencies).
    queue: list[str] = [n for n, d in in_degree.items() if d == 0]
    visited = 0

    while queue:
        node = queue.pop(0)
        visited += 1
        for dependent in dependents.get(node, []):
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                queue.append(dependent)

    if visited != len(graph):
        cycle_nodes = [n for n, d in in_degree.items() if d > 0]
        raise ValueError(f"dependency cycle detected involving nodes: {cycle_nodes}")
