"""Server-side eligible factor catalog for visual screening (#740)."""

from __future__ import annotations

import pytest
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.selection.assemble_facts import resolve_factor_nodes
from ditto_application.queries.selection_factor_catalog import (
    SelectionFactorCatalogQuery,
)
from ditto_features.expression.compiler import ExpressionCompiler
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
    # 装配引擎必拒的配方同样不得出现（#740 F1）：cs_rank 嵌套 ts 算子
    # 需要 materialized intermediates，引擎按 ASSEMBLY_FACTOR_EXPRESSION_
    # UNSUPPORTED 拒绝——目录若收录即用户可选中、提交即 422。
    assert "liquidity" not in ids
    assert "alpha_001" not in ids
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
    # 行为级单一权威锁定（#740 F1）：目录声称合格的每个因子都必须通过
    # 装配引擎真实运行的同一条规划路径（_plan_factors 委托的共享
    # resolver），杜绝目录收录引擎必拒因子。
    compiler = ExpressionCompiler()
    for entry in _query().list_entries():
        resolve_factor_nodes(ALL_FACTOR_SPECS.get, compiler, (entry.factor_id,))

    # 引擎必拒的两个代表（cs/ts 嵌套）在 resolver 上如实失败。
    for rejected in ("liquidity", "alpha_001"):
        with pytest.raises(AppProcessError) as error:
            resolve_factor_nodes(ALL_FACTOR_SPECS.get, compiler, (rejected,))
        assert error.value.details["reason"] == "ASSEMBLY_FACTOR_EXPRESSION_UNSUPPORTED"


def test_lookback_composes_across_the_dependency_chain() -> None:
    entries = {entry.factor_id: entry for entry in _query().list_entries()}
    # momentum_3m 是 60 交易日窗口的表达式因子。
    assert entries["momentum_3m"].lookback_trading_days >= 60
    # 回看沿依赖闭包组合（#740 F3）：volatility_factor = -volatility_20，
    # volatility_20 = ts_std(returns_1, 20) 又依赖 1 日 returns——组合窗口
    # 必须计入依赖链，而不是只看自身表达式。
    assert entries["volatility_factor"].lookback_trading_days >= 21
