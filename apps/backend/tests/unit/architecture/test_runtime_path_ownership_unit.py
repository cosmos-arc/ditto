"""Machine contract for deployment-owned runtime filesystem roots."""

from __future__ import annotations

import ast
from pathlib import Path

_WORKSPACE_ROOT = Path(__file__).resolve().parents[5]
_RUNTIME_SOURCE_ROOTS = (
    _WORKSPACE_ROOT / "packages" / "platform" / "src",
    _WORKSPACE_ROOT / "packages" / "data" / "src",
    _WORKSPACE_ROOT / "apps" / "backend" / "src" / "ditto_apps" / "config",
    _WORKSPACE_ROOT / "apps" / "backend" / "src" / "ditto_apps" / "registry",
)
_CHECKOUT_MARKERS = frozenset({".git", "pixi.toml", "pyproject.toml"})


def _checkout_discovery_violations(path: Path) -> list[str]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and any(
            alias.name == "find_project_root" for alias in node.names
        ):
            violations.append(f"{path}: imports find_project_root")
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and (
            node.name == "find_project_root"
        ):
            violations.append(f"{path}: defines find_project_root")
        if isinstance(node, ast.Constant) and node.value in _CHECKOUT_MARKERS:
            violations.append(f"{path}: reads checkout marker {node.value!r}")
    if "Path(__file__)" in source and ".parents[" in source:
        violations.append(f"{path}: derives a root from Path(__file__).parents")
    return violations


def test_runtime_paths_are_owned_by_the_backend_composition_root() -> None:
    """Platform/data runtime code must consume roots, never discover a checkout."""
    violations = [
        violation
        for root in _RUNTIME_SOURCE_ROOTS
        for path in root.rglob("*.py")
        for violation in _checkout_discovery_violations(path)
    ]
    project_root_module = (
        _WORKSPACE_ROOT
        / "packages/platform/src/ditto_platform/foundation/config/project_root.py"
    )
    if project_root_module.exists():
        violations.append(f"{project_root_module}: packaged checkout discovery module")

    assert violations == []


def test_research_acceptance_requires_an_explicit_workspace_root() -> None:
    """Engineering acceptance may use Git only through an explicit workspace seam."""
    source_path = (
        _WORKSPACE_ROOT
        / "apps/backend/src/ditto_apps/scripts/r3_research_acceptance.py"
    )
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(source_path))
    fixture_runner = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "run_fixture_acceptance"
    )
    live_request = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef) and node.name == "LiveAcceptanceRequest"
    )

    assert any(
        argument.arg == "workspace_root" for argument in fixture_runner.args.kwonlyargs
    )
    assert any(
        isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id == "workspace_root"
        for node in live_request.body
    )
    assert "_REPO_ROOT" not in source
    assert "Path(__file__).resolve().parents" not in source
