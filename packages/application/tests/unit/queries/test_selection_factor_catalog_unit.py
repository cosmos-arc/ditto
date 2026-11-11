"""Server-side eligible factor catalog for visual screening (#740)."""

from __future__ import annotations

from ditto_application.processes.selection.assemble_facts import AssembleSelectionFacts
from ditto_application.queries.selection_factor_catalog import (
    SelectionFactorCatalogQuery,
)
from ditto_features.factors.factor_specs import ALL_FACTOR_SPECS


def _query() -> SelectionFactorCatalogQuery:
    return SelectionFactorCatalogQuery(ALL_FACTOR_SPECS)


def test_lists_only_assembly_eligible_factors() -> None:
    entries = _query().list_entries()
    ids = [entry.factor_id for entry in entries]

    # 行情 bar 因子：可装配、可入条件与权重。
    assert "momentum_1m" in ids
    assert "reversal_1w" in ids
    # PIT 不合格列不进入目录：财务因子依赖 fundamentals.*（组装引擎
    # fail closed），python 执行器因子没有 expression 面包。
    assert "ep_ttm" not in ids
    assert "relative_strength_60d" not in ids
    # 每个因子恰好一个条目，稳定排序。
    assert ids == sorted(ids)
    assert len(ids) == len(set(ids))


def test_entry_carries_readable_metadata() -> None:
    entries = {entry.factor_id: entry for entry in _query().list_entries()}

    # momentum_1m 的唯一定义在 Alpha 子表，归组跟随定义归属。
    momentum = entries["momentum_1m"]
    assert momentum.group == "alpha"
    assert momentum.description  # 非空人类可读说明
    assert momentum.lookback_trading_days >= 20
    assert momentum.dependencies == ("market.close",)
    assert momentum.value_unit  # 单位说明（截面分数秩口径）

    # momentum_3m 定义于动量子表：分组标签带中文显示名。
    assert entries["momentum_3m"].group == "momentum"
    assert entries["momentum_3m"].group_label == "动量与反转"


def test_eligibility_matches_the_real_assembly_path() -> None:
    # 行为级单一权威锁定：目录声称合格的每个因子都必须通过真实
    # AssembleSelectionFacts 的因子解析路径（unknown/python/依赖不可解）。
    process = AssembleSelectionFacts(
        provider=None,  # type: ignore[arg-type]
        history=None,  # type: ignore[arg-type]
        discover_sources=None,  # type: ignore[arg-type]
        identities=None,  # type: ignore[arg-type]
        factors=ALL_FACTOR_SPECS,  # type: ignore[arg-type]
        snapshots=None,  # type: ignore[arg-type]
    )
    visit: dict[str, frozenset[str]] = {}

    def walk(factor_id: str, path: tuple[str, ...]) -> frozenset[str]:
        if factor_id in visit:
            return visit[factor_id]
        assert factor_id not in path
        spec = process._factor_spec(factor_id)
        leaves: set[str] = set()
        for dependency in spec.dependencies:
            leaves |= process._dependency_leaves(dependency, factor_id, path, walk)
        visit[factor_id] = frozenset(leaves)
        return visit[factor_id]

    for entry in _query().list_entries():
        process._factor_spec(entry.factor_id)  # unknown/python 拒绝
        walk(entry.factor_id, ())


def test_lookback_comes_from_the_compiled_expression() -> None:
    entries = {entry.factor_id: entry for entry in _query().list_entries()}
    # momentum_3m 是 60 交易日窗口的表达式因子。
    assert entries["momentum_3m"].lookback_trading_days >= 60
