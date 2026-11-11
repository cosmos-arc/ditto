"""
Eligible factor catalog for the visual screener (#740).

The catalog is the single server-side statement of which governed factors
can enter selection conditions and weights. Eligibility is decided by the
exact resolver the assembly engine runs (:func:`resolve_factor_nodes`):
a factor the engine would reject fail-closed (financial-statement leaves,
python executors, unresolvable dependencies, cross-sectional-nested
time-series recipes) never appears as a choosable field, and the reported
lookback is the same dependency-composed window the planner uses.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from ditto_features.expression.compiler import ExpressionCompiler
from ditto_features.factors.factor_registry import FACTOR_GROUP_LABELS, FACTOR_GROUPS
from ditto_features.factors.spec import FactorSpec

from ditto_application.exceptions import AppProcessError, AppQueryError
from ditto_application.factor_assembly import resolve_factor_nodes

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
            # The same resolver the engine runs at assembly time decides
            # eligibility and the dependency-composed lookback; any
            # rejection (unknown/python/dependency/compile/recipe) drops
            # the factor from the choosable set instead of surfacing a
            # field the server would refuse (#740 F1/F3).
            try:
                nodes = resolve_factor_nodes(
                    self._factors.get, self._compiler, (factor_id,)
                )
            except AppProcessError:
                continue
            requested_nodes = [node for node in nodes if node.requested]
            if len(requested_nodes) != 1:
                continue
            node = requested_nodes[0]
            entries.append(
                SelectionFactorCatalogEntry(
                    factor_id=factor_id,
                    group=group,
                    group_label=FACTOR_GROUP_LABELS.get(group, group),
                    description=spec.description,
                    lookback_trading_days=max(1, node.lookback),
                    dependencies=tuple(sorted(node.leaves)),
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
