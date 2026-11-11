"""
Assembly-grade factor resolution shared by processes and queries (R8).

This leaf module owns the single authority for which governed factors the
selection assembly can serve: the market-leaf vocabulary and the
dependency-closure resolver (with dependency-composed lookbacks). It lives
at the application package top level because both
``processes.selection.assemble_facts`` (the engine) and
``queries.selection_factor_catalog`` (the visual screener catalog) consume
it and the R8 isolation contract forbids ``queries`` from importing
``processes``.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass

from ditto_features.expression.compiler import ExpressionCompiler
from ditto_features.expression.contracts import CompiledDerivedExpression
from ditto_features.expression.diagnostics import ExpressionCompileError
from ditto_features.factors.spec import FactorSpec

from ditto_application.exceptions import AppProcessError
from ditto_application.factor_signal_spec import build_signal_spec

__all__ = [
    "MARKET_BAR_COLUMNS",
    "FactorAssemblyNode",
    "resolve_factor_nodes",
]

# 行情 read-model 的列词汇表：因子依赖闭包的合法叶集合。
MARKET_BAR_COLUMNS: Mapping[str, str] = {
    "market.open": "open",
    "market.high": "high",
    "market.low": "low",
    "market.close": "close",
    "market.volume": "volume",
    "market.amount": "amount",
}


@dataclass(frozen=True, slots=True)
class FactorAssemblyNode:
    """One governed factor materialized in dependency order."""

    factor_id: str
    compiled: CompiledDerivedExpression
    requested: bool
    leaves: frozenset[str]
    lookback: int


def _resolve_factor_spec(
    get_spec: Callable[[str], FactorSpec | None], factor_id: str
) -> FactorSpec:
    spec = get_spec(factor_id)
    if spec is None:
        raise AppProcessError(
            f"unknown registered factor: {factor_id}",
            details={"reason": "ASSEMBLY_FACTOR_UNKNOWN", "factor_id": factor_id},
        )
    if spec.computation_type != "expression":
        raise AppProcessError(
            f"research factor executor is unavailable: {factor_id}",
            details={
                "reason": "ASSEMBLY_FACTOR_EXECUTOR_UNAVAILABLE",
                "factor_id": factor_id,
            },
        )
    return spec


def _compiled_factor(
    compiler: ExpressionCompiler, factor_id: str, spec: FactorSpec
) -> CompiledDerivedExpression:
    """Compile one node; reject cross-sectional-nested-time-series recipes."""
    try:
        compiled = compiler.compile(
            build_signal_spec(spec.expression, 0, derived_id=factor_id, version=1)
        )
    except ExpressionCompileError as error:
        raise AppProcessError(
            f"registered factor failed to compile: {factor_id}",
            details={"reason": "ASSEMBLY_FACTOR_COMPILE", "factor_id": factor_id},
        ) from error
    operators = compiled.analysis.operator_names
    if any(op.startswith("cs_") for op in operators) and any(
        op.startswith("ts_") for op in operators
    ):
        raise AppProcessError(
            "factor nests a time-series operator under a "
            + "cross-sectional operator; the production recipe with "
            + "materialized intermediates is required",
            details={
                "reason": "ASSEMBLY_FACTOR_EXPRESSION_UNSUPPORTED",
                "factor_id": factor_id,
            },
        )
    return compiled


def _dependency_leaves(
    get_spec: Callable[[str], FactorSpec | None],
    dependency: str,
    factor_id: str,
    path: tuple[str, ...],
    visit: Callable[[str, tuple[str, ...]], frozenset[str]],
) -> frozenset[str]:
    """Classify one declared dependency as market leaf or nested factor."""
    if get_spec(dependency) is not None:
        return visit(dependency, (*path, factor_id))
    if dependency in MARKET_BAR_COLUMNS:
        return frozenset({dependency})
    raise AppProcessError(
        "factor dependency is not available for assembly: "
        + f"{factor_id} -> {dependency}",
        details={
            "reason": "ASSEMBLY_FACTOR_DEPENDENCY_UNSUPPORTED",
            "factor_id": factor_id,
            "dependency": dependency,
        },
    )


def resolve_factor_nodes(
    get_spec: Callable[[str], FactorSpec | None],
    compiler: ExpressionCompiler,
    requested: Iterable[str],
) -> tuple[FactorAssemblyNode, ...]:
    """
    Single authority for which governed factors assembly can serve.

    Resolves the transitive closure of ``requested`` factor ids in
    dependency order, rejecting (fail-closed, via :class:`AppProcessError`)
    unknown ids, python executors, unresolvable dependencies, cycles,
    compile failures, and cross-sectional-nested-time-series recipes. The
    eligible-factor catalog reuses this exact resolver, so it can never
    advertise a factor the engine would refuse.
    """
    order: list[str] = []
    leaves: dict[str, frozenset[str]] = {}
    compiled: dict[str, CompiledDerivedExpression] = {}
    lookbacks: dict[str, int] = {}

    def visit(factor_id: str, path: tuple[str, ...]) -> frozenset[str]:
        if factor_id in leaves:
            return leaves[factor_id]
        if factor_id in path:
            cycle = (*path, factor_id)
            raise AppProcessError(
                f"registered factor dependency cycle: {' -> '.join(cycle)}",
                details={
                    "reason": "ASSEMBLY_FACTOR_CYCLE",
                    "factor_id": factor_id,
                    "dependency_path": cycle,
                },
            )
        spec = _resolve_factor_spec(get_spec, factor_id)
        node_leaves: set[str] = set()
        for dependency in spec.dependencies:
            node_leaves |= _dependency_leaves(
                get_spec, dependency, factor_id, path, visit
            )
        leaves[factor_id] = frozenset(node_leaves)
        compiled[factor_id] = _compiled_factor(compiler, factor_id, spec)
        # Time-series windows compose across registered dependencies, so
        # the required history is this node's window plus the deepest
        # dependency chain below it.
        lookbacks[factor_id] = compiled[factor_id].analysis.lookback + max(
            (
                lookbacks[dependency]
                for dependency in spec.dependencies
                if dependency in lookbacks
            ),
            default=0,
        )
        order.append(factor_id)
        return leaves[factor_id]

    requested_ids = set(requested)
    for factor_id in sorted(requested_ids):
        visit(factor_id, ())
    return tuple(
        FactorAssemblyNode(
            factor_id=factor_id,
            compiled=compiled[factor_id],
            requested=factor_id in requested_ids,
            leaves=leaves[factor_id],
            lookback=lookbacks[factor_id],
        )
        for factor_id in order
    )
