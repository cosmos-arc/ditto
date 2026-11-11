"""
Eligible factor catalog for the visual screener (#740).

The catalog is the single server-side statement of which governed factors
can enter selection conditions and weights. Eligibility mirrors what
``AssembleSelectionFacts`` can actually assemble on the live read model:
expression factors whose dependency closure resolves entirely onto market
bar columns. A factor the assembly engine would reject fail-closed
(financial-statement leaves, python executors, unknown ids) never appears
as a choosable field, so the visual builder cannot author a run that the
server must refuse.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from ditto_features.expression.compiler import ExpressionCompiler
from ditto_features.expression.diagnostics import ExpressionCompileError
from ditto_features.factors.factor_registry import FACTOR_GROUP_LABELS, FACTOR_GROUPS
from ditto_features.factors.spec import FactorSpec

from ditto_application.exceptions import AppQueryError
from ditto_application.processes.execution._factor_signal_spec import (
    build_signal_spec,
)
from ditto_application.processes.selection.assemble_facts import (
    MARKET_BAR_COLUMNS,
)

__all__ = [
    "SelectionFactorCatalogEntry",
    "SelectionFactorCatalogQuery",
]

# 截面值口径：所有合格因子在装配边界统一归一为 (0,1] 分数秩（高=排名
# 靠前），条件与权重都在这个无量纲口径上表达。
VALUE_UNIT_LABEL = "截面分数秩 (0,1]; 秩越高截面排名越靠前"


@dataclass(frozen=True, slots=True)
class SelectionFactorCatalogEntry:
    """One choosable factor with the metadata a readable condition needs."""

    factor_id: str
    group: str
    group_label: str
    description: str
    lookback_trading_days: int
    dependencies: tuple[str, ...]
    value_unit: str


def _closure_leaves(
    specs: Mapping[str, FactorSpec], factor_id: str, path: frozenset[str]
) -> frozenset[str] | None:
    """Resolve one factor's market leaves; None when not assembly-eligible."""
    spec = specs.get(factor_id)
    if spec is None or spec.computation_type != "expression":
        return None
    if factor_id in path:
        return None
    leaves: set[str] = set()
    for dependency in spec.dependencies:
        if dependency in specs:
            nested = _closure_leaves(specs, dependency, path | {factor_id})
            if nested is None:
                return None
            leaves |= nested
        elif dependency in MARKET_BAR_COLUMNS:
            leaves.add(dependency)
        else:
            return None
    return frozenset(leaves)


class SelectionFactorCatalogQuery:
    """List the factors the visual screener may reference."""

    def __init__(self, factors: Mapping[str, FactorSpec]) -> None:
        self._factors = factors
        self._compiler = ExpressionCompiler()

    def list_entries(self) -> tuple[SelectionFactorCatalogEntry, ...]:
        """Return every assembly-eligible factor, ordered by id."""
        # Group attribution follows the registry merge order: a factor id
        # defined by several sub-tables belongs to the last one merged into
        # ALL_FACTOR_SPECS, exactly like the effective definition.
        group_by_id: dict[str, str] = {}
        for group, table in FACTOR_GROUPS:
            for factor_id in table:
                if factor_id in self._factors:
                    group_by_id[factor_id] = group

        entries: list[SelectionFactorCatalogEntry] = []
        for factor_id, spec in self._factors.items():
            group = group_by_id.get(factor_id)
            if group is None:
                continue
            leaves = _closure_leaves(self._factors, factor_id, frozenset())
            if leaves is None:
                continue
            try:
                compiled = self._compiler.compile(
                    build_signal_spec(
                        spec.expression, 0, derived_id=factor_id, version=1
                    )
                )
            except ExpressionCompileError:
                continue
            entries.append(
                SelectionFactorCatalogEntry(
                    factor_id=factor_id,
                    group=group,
                    group_label=FACTOR_GROUP_LABELS.get(group, group),
                    description=spec.description,
                    lookback_trading_days=max(1, compiled.analysis.lookback),
                    dependencies=tuple(sorted(leaves)),
                    value_unit=VALUE_UNIT_LABEL,
                )
            )
        entries.sort(key=lambda entry: entry.factor_id)
        if not entries:
            raise AppQueryError(
                "selection factor catalog resolved to an empty eligible set",
                details={"reason": "SELECTION_FACTOR_CATALOG_EMPTY"},
            )
        return tuple(entries)
