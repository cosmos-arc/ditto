"""Impact-fact layer tests: closure, test usage, scope plan, conservative failure.

Pins the #338 decision on a synthetic workspace (small, deterministic) and
against the real repository where the decision itself recorded facts (the
declared-dependency closure table and the four known test-usage edge
families). Real-repo scans cost a few seconds and run in the harness lane.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tooling.agent_harness import impact_scope
from tooling.agent_harness.impact_scope import (
    TestUsageFacts,
    backend_owner,
    load_workspace_graph,
    plan_backend_scope,
    production_closure,
)
from tooling.agent_harness.impact_scope import test_tree_owner as tree_owner
from tooling.agent_harness.impact_scope import test_usage_edges as usage_edges_of

_REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def real_usage() -> TestUsageFacts:
    """一次 AST 扫描供本模块所有真实仓断言复用（约 3 秒）。"""
    graph = load_workspace_graph(_REPO_ROOT)
    return usage_edges_of(_REPO_ROOT, graph)


def _write_manifest(root: Path, owner: str, name: str, deps: list[str]) -> None:
    lines = [
        "[project]",
        f'name = "{name}"',
        'version = "0.1.0"',
        "dependencies = [",
    ]
    lines.extend(f'  "{dep}",' for dep in deps)
    lines.append("]")
    target = root / owner / "pyproject.toml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_test(root: Path, owner: str, relative: str, content: str) -> None:
    target = root / owner / "tests" / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """kernel <- platform <- data <- application <- backend-style micro graph."""
    _write_manifest(tmp_path, "packages/kernel", "ditto-kernel", [])
    _write_manifest(tmp_path, "packages/platform", "ditto-platform", ["ditto-kernel"])
    _write_manifest(tmp_path, "packages/data", "ditto-data", ["ditto-kernel"])
    _write_manifest(
        tmp_path, "packages/application", "ditto-application", ["ditto-data"]
    )
    _write_manifest(
        tmp_path,
        "apps/backend",
        "ditto-apps",
        ["ditto-application", "ditto-platform>=0.1"],
    )
    return tmp_path


def test_owner_prefixes_ignore_nested_and_foreign_paths() -> None:
    assert backend_owner("packages/data/src/x.py") == "packages/data"
    assert backend_owner("apps/backend/src/y.py") == "apps/backend"
    assert backend_owner("packagesdata/x.py") is None
    assert backend_owner("docs/x.md") is None
    assert tree_owner("packages/data/tests/unit/test_x.py") == "packages/data"
    assert tree_owner("apps/backend/tests/integration/test_y.py") == ("apps/backend")
    assert tree_owner("packages/data/src/x.py") is None
    assert tree_owner("tests/test_ci.py") is None


def test_graph_reads_declared_workspace_dependencies_only(workspace: Path) -> None:
    graph = load_workspace_graph(workspace)
    assert graph.incomplete is False
    assert graph.owners == (
        "apps/backend",
        "packages/application",
        "packages/data",
        "packages/kernel",
        "packages/platform",
    )
    assert graph.deps["packages/kernel"] == ()
    assert graph.deps["packages/platform"] == ("packages/kernel",)
    assert graph.deps["apps/backend"] == (
        "packages/application",
        "packages/platform",
    )
    assert graph.module_root_to_owner["ditto_data"] == "packages/data"


def test_closure_propagates_to_direct_and_indirect_consumers(
    workspace: Path,
) -> None:
    graph = load_workspace_graph(workspace)
    kernel = production_closure(graph, frozenset({"packages/kernel"}))
    assert kernel == frozenset(graph.owners)
    data = production_closure(graph, frozenset({"packages/data"}))
    assert data == frozenset({"packages/data", "packages/application", "apps/backend"})
    backend = production_closure(graph, frozenset({"apps/backend"}))
    assert backend == frozenset({"apps/backend"})


def test_missing_or_broken_manifest_marks_graph_incomplete(
    workspace: Path,
) -> None:
    (workspace / "packages/platform" / "pyproject.toml").unlink()
    assert load_workspace_graph(workspace).incomplete is True

    (workspace / "packages/platform" / "pyproject.toml").write_text(
        "not [ valid toml", encoding="utf-8"
    )
    assert load_workspace_graph(workspace).incomplete is True

    (workspace / "packages/platform" / "pyproject.toml").write_text(
        '[project]\nname = "ditto-platform"\n', encoding="utf-8"
    )
    graph = load_workspace_graph(workspace)
    assert graph.incomplete is False  # PEP 621：dependencies 缺省即叶包
    assert graph.deps["packages/platform"] == ()


def test_usage_scan_collects_cross_package_imports(workspace: Path) -> None:
    _write_test(
        workspace,
        "packages/kernel",
        "unit/test_errors.py",
        "import ditto_application.processes\n",
    )
    _write_test(
        workspace,
        "packages/data",
        "unit/test_helpers.py",
        "from ditto_kernel import errors\nimport requests\n",
    )
    _write_test(
        workspace,
        "packages/platform",
        "unit/conftest.py",
        "from . import local\n",  # 相对导入不属于跨包使用
    )
    graph = load_workspace_graph(workspace)
    usage = usage_edges_of(workspace, graph)
    assert usage.incomplete is False
    assert usage.used_by_tests["packages/kernel"] == frozenset({"packages/application"})
    assert usage.used_by_tests["packages/data"] == frozenset({"packages/kernel"})
    assert "packages/platform" not in usage.used_by_tests


def test_usage_scan_fails_closed_on_unmapped_ditto_import(workspace: Path) -> None:
    _write_test(
        workspace,
        "packages/kernel",
        "unit/test_unknown.py",
        "import ditto_nonexistent\n",
    )
    usage = usage_edges_of(workspace, load_workspace_graph(workspace))
    assert usage.incomplete is True


def test_scope_plan_combines_relations_without_test_backflow(
    workspace: Path,
) -> None:
    _write_test(
        workspace,
        "packages/platform",
        "unit/test_uses_data.py",
        "import ditto_data\n",  # platform 测试使用 data：data 变化须选中 platform 测试
    )
    graph = load_workspace_graph(workspace)
    usage = usage_edges_of(workspace, graph)

    data_change = plan_backend_scope(
        ["packages/data/src/ditto_data/x.py"], graph=graph, usage=usage
    )
    assert data_change.production_owners == ("packages/data",)
    # 声明闭包（application、backend）+ 使用边（platform 测试用 data）。
    assert data_change.test_dirs == (
        "apps/backend/tests",
        "packages/application/tests",
        "packages/data/tests",
        "packages/platform/tests",
    )

    kernel_change = plan_backend_scope(
        ["packages/kernel/src/ditto_kernel/errors.py"], graph=graph, usage=usage
    )
    assert kernel_change.test_dirs == tuple(f"{owner}/tests" for owner in graph.owners)

    # 测试文件变动只带来直接测试责任：platform 测试变化不把 platform
    # 当作生产变化传播给它的消费者（#338 四关系之测试使用不回灌）。
    test_only = plan_backend_scope(
        ["packages/platform/tests/unit/test_uses_data.py"], graph=graph, usage=usage
    )
    assert test_only.production_owners == ()
    assert test_only.test_owners == ("packages/platform",)
    assert test_only.test_dirs == ("packages/platform/tests",)

    # 混合修改：data 生产变化 + backend 测试文件 → 并集（含使用边 platform）。
    mixed = plan_backend_scope(
        [
            "packages/data/src/ditto_data/x.py",
            "apps/backend/tests/integration/test_api.py",
        ],
        graph=graph,
        usage=usage,
    )
    assert mixed.test_dirs == (
        "apps/backend/tests",
        "packages/application/tests",
        "packages/data/tests",
        "packages/platform/tests",
    )


def test_deferred_usage_keeps_static_scope(workspace: Path) -> None:
    graph = load_workspace_graph(workspace)
    plan = plan_backend_scope(
        ["packages/kernel/src/ditto_kernel/errors.py"], graph=graph, usage=None
    )
    assert plan.usage_deferred is True
    assert plan.escalation is None
    assert plan.test_dirs == tuple(f"{owner}/tests" for owner in graph.owners)


def test_incomplete_graph_escalates_before_any_selection(workspace: Path) -> None:
    (workspace / "packages/kernel" / "pyproject.toml").unlink()
    graph = load_workspace_graph(workspace)
    plan = plan_backend_scope(
        ["packages/data/src/ditto_data/x.py"], graph=graph, usage=None
    )
    assert plan.escalation == "graph-incomplete"


def test_non_python_inputs_widen_scope_through_ownership(workspace: Path) -> None:
    graph = load_workspace_graph(workspace)
    plan = plan_backend_scope(
        ["packages/data/src/ditto_data/scripts/schema.sql"], graph=graph, usage=None
    )
    assert plan.production_owners == ("packages/data",)
    assert "packages/application/tests" in plan.test_dirs


# 决策 #338 记录的真实仓事实必须保持成立（否则图已漂移，须显式裁决）。


def test_real_graph_matches_recorded_closure_table() -> None:
    graph = load_workspace_graph(_REPO_ROOT)
    assert graph.incomplete is False
    assert len(graph.owners) == 13

    def closure_of(owner: str) -> set[str]:
        return set(production_closure(graph, frozenset({owner})))

    assert closure_of("packages/kernel") == set(graph.owners)
    assert closure_of("packages/platform") == set(graph.owners) - {
        "packages/kernel",
        "packages/portfolio",
        "packages/risk",
    }
    assert closure_of("packages/agent") == {"packages/agent", "apps/backend"}
    assert closure_of("packages/data") == {
        "packages/data",
        "packages/backtest",
        "packages/application",
        "packages/agent",
        "apps/backend",
    }
    assert closure_of("packages/features") == {
        "packages/features",
        "packages/application",
        "packages/agent",
        "apps/backend",
    }


def test_real_usage_edges_keep_the_recorded_families(
    real_usage: TestUsageFacts,
) -> None:
    usage = real_usage
    assert usage.incomplete is False
    assert "packages/data" in usage.used_by_tests.get("packages/features", frozenset())
    assert {"packages/features", "packages/analysis", "packages/strategy"} <= (
        usage.used_by_tests.get("packages/data", frozenset())
    )
    assert "apps/backend" in usage.used_by_tests.get(
        "packages/application", frozenset()
    )
    # kernel 异常测试引用 8 个上层包（#338 已确认的测试漏边例子）。
    assert len(usage.used_by_tests.get("packages/kernel", frozenset())) == 8


def test_real_backend_tests_use_every_package(real_usage: TestUsageFacts) -> None:
    graph = load_workspace_graph(_REPO_ROOT)
    usage = real_usage
    backend_users = usage.used_by_tests.get("apps/backend", frozenset())
    assert backend_users == frozenset(
        owner for owner in graph.owners if owner != "apps/backend"
    )


def test_shadow_report_is_monotonic_against_direct_owners(
    real_usage: TestUsageFacts,
) -> None:
    graph = load_workspace_graph(_REPO_ROOT)
    usage = real_usage
    plan = plan_backend_scope(
        ["packages/strategy/src/ditto_strategy/alpha/pipeline.py"],
        graph=graph,
        usage=usage,
    )
    assert "packages/data/tests" in plan.test_dirs  # data 测试使用 strategy
    assert set(plan.test_dirs) >= {
        "packages/strategy/tests",
        "packages/backtest/tests",
        "packages/application/tests",
        "apps/backend/tests",
    }


def test_cross_package_move_keeps_both_sides_in_scope(workspace: Path) -> None:
    """文件跨包移动（no-rename 两侧路径）时新旧 owner 的责任都不消失。"""
    graph = load_workspace_graph(workspace)
    plan = plan_backend_scope(
        [
            "packages/data/src/ditto_data/moved.py",  # 删除侧（旧 owner）
            "packages/platform/src/ditto_platform/moved.py",  # 新增侧（新 owner）
        ],
        graph=graph,
        usage=None,
    )
    assert plan.production_owners == ("packages/data", "packages/platform")
    # data 与 platform 两个闭包的消费者并集都在责任内。
    assert set(plan.test_dirs) >= {
        "packages/data/tests",
        "packages/platform/tests",
        "packages/application/tests",
        "apps/backend/tests",
    }


def test_ci_lane_predicates_match_the_documented_extensions() -> None:
    assert impact_scope.is_web_source_path("apps/web/src/features/x.ts") is True
    assert impact_scope.is_web_source_path("docs/guide.md") is True
    assert impact_scope.is_web_source_path("apps/web/src/logo.svg") is False
    assert impact_scope.is_web_source_path("apps/web/package.json") is False
    assert impact_scope.is_backend_source_path("packages/data/src/x.py") is True
    assert impact_scope.is_backend_source_path("docs/architecture/a.md") is True
    assert impact_scope.is_backend_source_path("apps/web/src/x.ts") is False
    assert impact_scope.is_backend_source_path("packages/data/schema.sql") is False


def test_production_imports_stay_within_declared_workspace_deps() -> None:
    """生产静态跨包 import 不得超出各自声明依赖（#338 §3：实际 import 核验声明）。

    声明闭包是选择器的保守基础；出现未声明的跨包生产 import 说明图已
    漂移，必须先补声明（或修正边界），不能让选择器静默缩小。
    """
    import ast as ast_module

    graph = load_workspace_graph(_REPO_ROOT)
    assert graph.incomplete is False
    violations: list[str] = []
    for owner in graph.owners:
        source_dir = _REPO_ROOT / owner / "src"
        if not source_dir.is_dir():
            continue
        declared = set(graph.deps.get(owner, ()))
        for source_file in source_dir.rglob("*.py"):
            # build/ 下的陈旧拷贝不属于生产源（如 packages/agent/build/lib）。
            if "build" in source_file.relative_to(_REPO_ROOT).parts:
                continue
            try:
                tree = ast_module.parse(source_file.read_text(encoding="utf-8"))
            except (OSError, SyntaxError, UnicodeDecodeError):
                violations.append(f"{source_file}: unparseable")
                continue
            for node in ast_module.walk(tree):
                if isinstance(node, ast_module.Import):
                    modules = [alias.name for alias in node.names]
                elif (
                    isinstance(node, ast_module.ImportFrom)
                    and node.module
                    and not node.level
                ):
                    modules = [node.module]
                else:
                    continue
                for module in modules:
                    module_root = module.split(".")[0]
                    target = graph.module_root_to_owner.get(module_root)
                    if (
                        target is not None
                        and target != owner
                        and target not in declared
                    ):
                        violations.append(
                            f"{source_file.relative_to(_REPO_ROOT)}: "
                            f"{module_root} not declared by {owner}"
                        )
    assert violations == []


def test_turbo_scope_verdict_covers_policy_closure() -> None:
    """#538 缝 2：turbo 选择 ∪ wrapper 升级 ⊇ 策略闭包的单调性纯判定."""
    from tooling.agent_harness.impact_scope import turbo_scope_verdict

    mapping = {
        "ditto_kernel": "packages/kernel",
        "ditto_agent": "packages/agent",
        "ditto_apps": "apps/backend",
    }
    turbo_tasks = [
        {"package": "ditto-agent"},
        {"package": "ditto-apps"},
        {"package": "@ditto/web"},
        {"package": "ditto-python-root"},
        "not-a-dict",
    ]
    covered = turbo_scope_verdict(
        {"packages/agent", "apps/backend"},
        turbo_tasks,
        mapping,
        wrapper_escalated=False,
    )
    assert covered["monotonic"] is True
    assert covered["missing_from_turbo"] == []
    assert covered["turbo_affected_owners"] == ["apps/backend", "packages/agent"]

    gap = turbo_scope_verdict(
        {"packages/kernel", "packages/agent"},
        turbo_tasks,
        mapping,
        wrapper_escalated=False,
    )
    assert gap["monotonic"] is False
    assert gap["missing_from_turbo"] == ["packages/kernel"]

    # turbo 对未知路径 fail-open（选空）时，wrapper 升级仍满足组合单调性。
    escalated = turbo_scope_verdict(
        {"packages/kernel"}, [], mapping, wrapper_escalated=True
    )
    assert escalated["monotonic"] is True
    assert escalated["turbo_overwidth"] == []
