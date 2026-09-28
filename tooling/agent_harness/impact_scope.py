"""Shared impact facts for backend verification scopes (#317 C, decision #338).

One authoritative layer answers "which owners' tests does this change owe"
from four separated relations:

- code owner: the package a changed path lives in (``packages/<name>`` or
  ``apps/backend``); never the whole affected set on its own;
- production dependency: declared workspace dependencies from each owner's
  ``pyproject.toml``; changes propagate along the *reverse* transitive
  closure to every direct and indirect consumer;
- test usage: owners whose tests import another owner's production modules;
  selecting those tests adds the *test* responsibility only and never
  re-propagates as if the test owner's source had changed;
- non-code inputs (SQL/schema/fixture) resolve through path ownership to the
  package that reads them, so they widen scope exactly like source files.

The layer is deliberately conservative: a manifest that cannot be parsed, a
``ditto_*`` import that maps to no known owner, or an owner without a
manifest all mark the graph incomplete, and callers must fail closed to the
full gate (#338: 图不完整/未知不缩小范围).

base/head union is realized at path level (diffs keep both sides with
``--no-renames``, so deleted/renamed material still names its old owner)
plus policy: any manifest change escalates to the full check before the
graph is consulted, which covers every way the declared graph itself can
change between the two sides.
"""

from __future__ import annotations

import argparse
import ast
import subprocess
import sys
import tomllib
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path

_OWNER_PREFIXES = ("packages/", "apps/backend/")
_BACKEND = "apps/backend"


@dataclass(frozen=True)
class WorkspaceGraph:
    """Declared production dependencies between the Python workspace owners."""

    owners: tuple[str, ...]
    deps: dict[str, tuple[str, ...]] = field(hash=False)
    module_root_to_owner: dict[str, str] = field(hash=False)
    incomplete: bool


@dataclass(frozen=True)
class TestUsageFacts:
    """Which owners' tests import which owners' production modules."""

    # test owner -> production owners its tests import (cross-package only)
    used_by_tests: dict[str, frozenset[str]] = field(hash=False)
    incomplete: bool


@dataclass(frozen=True)
class ScopePlan:
    """Resolved verification scope for a backend-area change set."""

    production_owners: tuple[str, ...]
    test_owners: tuple[str, ...]
    closure_owners: tuple[str, ...]
    usage_owners: tuple[str, ...]
    test_dirs: tuple[str, ...]
    escalation: str | None
    usage_deferred: bool


def backend_owner(path: str) -> str | None:
    """Owner prefix of a backend-area path; paths outside owners have none."""
    for prefix in _OWNER_PREFIXES:
        if path.startswith(prefix):
            return "/".join(path.split("/")[:2])
    return None


_OWNER_PATH_MIN_PARTS = 3  # packages/<name>/tests/... 与 apps/backend/tests/...


def test_tree_owner(path: str) -> str | None:
    """Owner whose test tree a path belongs to (test material is owner-scoped)."""
    parts = Path(path).parts
    if (
        len(parts) >= _OWNER_PATH_MIN_PARTS
        and parts[0] == "packages"
        and parts[2] == "tests"
    ):
        return f"packages/{parts[1]}"
    if parts[:_OWNER_PATH_MIN_PARTS] == ("apps", "backend", "tests"):
        return _BACKEND
    return None


def _manifest_project(root: Path, owner: str) -> dict[str, object] | None:
    """Parsed ``[project]`` table of an owner manifest; None when unusable."""
    manifest = root / owner / "pyproject.toml"
    try:
        project = tomllib.loads(manifest.read_text(encoding="utf-8"))["project"]
    except (OSError, tomllib.TOMLDecodeError, KeyError, TypeError):
        return None
    return project if isinstance(project, dict) else None


def _owner_directories(root: Path) -> list[str]:
    """Every workspace owner directory present under ``packages/`` + backend."""
    owner_dirs: list[str] = []
    packages_dir = root / "packages"
    if packages_dir.is_dir():
        owner_dirs.extend(
            f"packages/{child.name}"
            for child in sorted(packages_dir.iterdir())
            if child.is_dir()
        )
    if (root / _BACKEND).is_dir():
        owner_dirs.append(_BACKEND)
    return owner_dirs


def _declared_workspace_deps(
    declared: list[str], name_to_owner: dict[str, str], owner: str
) -> tuple[str, ...]:
    """Workspace owners named by a manifest's requirement strings."""
    workspace_deps = []
    for requirement in declared:
        base = requirement.split(";")[0].split("[")[0]
        for separator in (" ", ">", "<", "=", "!", "~"):
            base = base.split(separator)[0]
        target = name_to_owner.get(base.strip())
        if target is not None and target != owner:
            workspace_deps.append(target)
    return tuple(sorted(set(workspace_deps)))


def load_workspace_graph(root: Path) -> WorkspaceGraph:
    """Read declared workspace production deps from the owner manifests.

    Only ``project.dependencies`` entries naming another workspace owner
    become edges (#338: 包声明提供保守基础). Any missing or unparseable
    manifest marks the graph incomplete so callers fail closed.
    """
    owner_dirs = _owner_directories(root)

    name_to_owner: dict[str, str] = {}
    incomplete = False
    for owner in owner_dirs:
        project = _manifest_project(root, owner)
        name = project.get("name") if project else None
        if isinstance(name, str) and name:
            name_to_owner[name] = owner
        else:
            incomplete = True

    deps: dict[str, tuple[str, ...]] = {}
    for owner in owner_dirs:
        if owner not in name_to_owner.values():
            continue
        project = _manifest_project(root, owner)
        declared = project.get("dependencies") if project else None
        if declared is None:
            deps[owner] = ()  # 叶包可不声明 dependencies（PEP 621 可选项）
        elif isinstance(declared, list) and all(
            isinstance(item, str) for item in declared
        ):
            deps[owner] = _declared_workspace_deps(declared, name_to_owner, owner)
        else:
            incomplete = True

    module_root_to_owner = {
        name.replace("-", "_"): owner for name, owner in name_to_owner.items()
    }
    return WorkspaceGraph(
        owners=tuple(sorted(name_to_owner.values())),
        deps=deps,
        module_root_to_owner=module_root_to_owner,
        incomplete=incomplete,
    )


def _imported_module_roots(tree: ast.Module) -> Iterator[str]:
    """Root module names of the absolute imports in one parsed module."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            modules = [node.module]
        else:
            continue
        for module in modules:
            yield module.split(".")[0]


def production_closure(graph: WorkspaceGraph, owners: frozenset[str]) -> frozenset[str]:
    """Reverse transitive closure: every owner transitively consuming ``owners``.

    Unknown owners (not in the graph) are returned unchanged so callers can
    still decide their own fail-closed behaviour; the closure only widens.
    """
    seen = set(owners)
    frontier = list(owners)
    while frontier:
        provider = frontier.pop()
        for owner, declared in graph.deps.items():
            if provider in declared and owner not in seen:
                seen.add(owner)
                frontier.append(owner)
    return frozenset(seen)


def _scan_owner_tests(
    tests_dir: Path, graph: WorkspaceGraph, owner: str
) -> tuple[frozenset[str], bool]:
    """Cross-package targets one owner's tests import; unparseable files and
    ``ditto_*`` imports mapping to no known owner mark the facts incomplete."""
    targets: set[str] = set()
    incomplete = False
    for test_file in tests_dir.rglob("*.py"):
        try:
            tree = ast.parse(test_file.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, UnicodeDecodeError):
            incomplete = True
            continue
        for module_root in _imported_module_roots(tree):
            if not module_root.startswith("ditto_"):
                continue
            target = graph.module_root_to_owner.get(module_root)
            if target is None:
                incomplete = True
            elif target != owner:
                targets.add(target)
    return frozenset(targets), incomplete


def test_usage_edges(root: Path, graph: WorkspaceGraph) -> TestUsageFacts:
    """Map each owner's tests to the other owners' modules they import.

    Static ``ditto_*`` imports only: dynamic dependency edges cannot be
    proven absent here, so an import that maps to no known owner marks the
    facts incomplete and callers fail closed (#338: 动态边不可建模时扩大).
    """
    used_by_tests: dict[str, frozenset[str]] = {}
    incomplete = False
    for owner in graph.owners:
        tests_dir = root / owner / "tests"
        if not tests_dir.is_dir():
            continue
        targets, unmapped = _scan_owner_tests(tests_dir, graph, owner)
        incomplete = incomplete or unmapped
        if targets:
            used_by_tests[owner] = targets
    return TestUsageFacts(used_by_tests=used_by_tests, incomplete=incomplete)


def plan_backend_scope(
    paths: Sequence[str],
    *,
    graph: WorkspaceGraph,
    usage: TestUsageFacts | None,
) -> ScopePlan:
    """Combine the relations into the test scope a backend change owes.

    ``usage=None`` (planning paths that must stay fast) defers the AST scan;
    the plan then carries the statically derivable scope and flags the
    deferral. Test-material owners join the scope directly, but their source
    never propagates further (#338: 测试使用在选择测试时闭合).
    """
    production: set[str] = set()
    tests: set[str] = set()
    for path in paths:
        if owner := test_tree_owner(path):
            tests.add(owner)
        elif owner := backend_owner(path):
            production.add(owner)
    incomplete = graph.incomplete or (usage is not None and usage.incomplete)
    escalation = "graph-incomplete" if incomplete else None
    closure = (
        production_closure(graph, frozenset(production)) if production else frozenset()
    )
    usage_additions: set[str] = set()
    if usage is not None:
        for test_owner_key, targets in usage.used_by_tests.items():
            if targets & production:
                usage_additions.add(test_owner_key)
    scope = production | tests | closure | usage_additions
    return ScopePlan(
        production_owners=tuple(sorted(production)),
        test_owners=tuple(sorted(tests)),
        closure_owners=tuple(sorted(closure)),
        usage_owners=tuple(sorted(usage_additions)),
        test_dirs=tuple(sorted(f"{owner}/tests" for owner in scope)),
        escalation=escalation,
        usage_deferred=usage is None,
    )


def is_web_source_path(path: str) -> bool:
    """Whether a path is web material for CI's pure-web lane."""
    return path.startswith(
        ("apps/web/src/", "apps/web/tests/", "apps/web/prototype/", "docs/")
    ) and path.endswith((".ts", ".tsx", ".css", ".md", ".rst"))


def is_backend_source_path(path: str) -> bool:
    """Whether a path is backend material for CI's backend lane."""
    return path.endswith((".py", ".md", ".rst")) and path.startswith(
        ("packages/", "apps/backend/", "docs/")
    )


def diff_paths(root: Path, base: str, head: str) -> list[str]:
    """Both-side changed paths between two revisions (no rename folding)."""
    raw = (
        subprocess.check_output(
            ["git", "diff", "--raw", "-z", "--no-renames", base, head], cwd=root
        )
        .decode()
        .split("\0")
    )
    # --raw -z 记录交替为 (header, path)；路径在奇数位。
    return [raw[index] for index in range(1, len(raw) - 1, 2)]


def shadow_report(root: Path, base: str, head: str) -> dict[str, object]:
    """Shadow-comparison facts for one historical base/head pair (#338 §7).

    Records per-relation scope reasons and checks the monotonicity
    contract: the closure+usage test scope must be a superset of the
    direct-owner scope the pre-C ladder selected.
    """
    paths = diff_paths(root, base, head)
    graph = load_workspace_graph(root)
    usage = test_usage_edges(root, graph)
    plan = plan_backend_scope(paths, graph=graph, usage=usage)
    direct = {owner for owner in map(backend_owner, paths) if owner is not None} | {
        owner for owner in map(test_tree_owner, paths) if owner is not None
    }
    direct_dirs = {f"{owner}/tests" for owner in direct}
    monotonic = direct_dirs <= set(plan.test_dirs)
    return {
        "base": base,
        "head": head,
        "changed_paths": len(paths),
        "direct_owners": sorted(direct),
        "closure_additions": sorted(set(plan.closure_owners) - direct),
        "usage_additions": sorted(set(plan.usage_owners) - direct),
        "test_dirs": list(plan.test_dirs),
        "escalation": plan.escalation,
        "monotonic_vs_direct": monotonic,
    }


def main(argv: list[str] | None = None) -> int:
    """Print a shadow report for a base/head pair (replay evidence tool)."""
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    report_command = subcommands.add_parser(
        "report", help="compare closure+usage scope against direct owners"
    )
    report_command.add_argument("--base", required=True)
    report_command.add_argument("--head", required=True)
    arguments = parser.parse_args(argv)
    root = Path(
        subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"], text=True
        ).strip()
    )
    try:
        report = shadow_report(root.resolve(), arguments.base, arguments.head)
    except subprocess.CalledProcessError as error:
        print(f"impact-scope: {error}", file=sys.stderr)
        return 1
    for key, value in report.items():
        print(f"{key}: {value}")
    return 0 if report["monotonic_vs_direct"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
