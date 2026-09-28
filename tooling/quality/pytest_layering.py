"""
Single authoritative directory-to-layer rule for pytest markers.

Registered from the repository-root conftest, so every entry (single file,
owner tree, full testpaths, CI shards with ``-o addopts=``) applies the same
rule to the same nodeid. Near-tree conftests must not mutate foreign owners'
markers (#330 B1); the legacy per-package path hooks were removed in favor
of this module.

The rule is component-exact: a directory literally named ``integration`` /
``unit`` / ``contract`` / ``e2e`` decides the layer. File-name substrings
never do. Explicit markers on a test always remain on top of the directory
layer. Unclassified test trees (registry, benchmarks, ``tooling/*/tests``)
default to ``unit``.

``integration`` directories also carry ``serial`` — the blanket resource
policy inherited from the legacy hooks. It stays until the per-resource
serial audit (#226) replaces it group by group; relax it there, not here.

This plugin is globally registered, so unlike a conftest hook its module
hooks fire for every collected file regardless of path (pytest scopes
conftest hooks to the file's own directory chain). That is what makes the
import-bracket registry below able to scope import-time replacements — a
conftest applying them at import time leaks them into every module the same
process imports afterwards (#330 B1).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

# Checked in priority order, matching the legacy hooks' precedence: an
# ``integration`` component wins over ``unit`` on paths containing both.
_LAYER_BY_COMPONENT: dict[str, tuple[str, ...]] = {
    "integration": ("integration", "serial"),
    "contract": ("integration",),
    "e2e": ("e2e",),
    "unit": ("unit",),
}
_DEFAULT_LAYER: tuple[str, ...] = ("unit",)

# (scope tree, apply while a module under the scope imports, restore otherwise)
_ImportBracket = tuple[Path, Callable[[], None], Callable[[], None]]
_import_brackets: list[_ImportBracket] = []


def register_import_bracket(
    scope: Path, apply: Callable[[], None], restore: Callable[[], None]
) -> None:
    """
    Scope an import-time replacement to one test tree (#330 B1).

    A conftest calls this at load time with its own tree and the pair of
    enter/leave callbacks for its replacement (for example the backend unit
    Prefect decorator mock). While collection imports modules inside the
    scope the replacement is applied; every module outside the tree — other
    owners in merged entries included — imports with it restored.
    """
    _import_brackets.append((scope.resolve(), apply, restore))


def layer_markers_for(path: Path) -> tuple[str, ...]:
    """Markers implied by the directory location of a collected item."""
    for component, markers in _LAYER_BY_COMPONENT.items():
        if component in path.parts:
            return markers
    return _DEFAULT_LAYER


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Add the directory layer markers to every collected item."""
    for item in items:
        for name in layer_markers_for(item.path):
            item.add_marker(getattr(pytest.mark, name))


def pytest_pycollect_makemodule(module_path: Path, parent: pytest.Collector) -> None:
    """Apply tree-scoped import brackets around each module import."""
    if not _import_brackets:
        return None
    resolved = Path(module_path).resolve()
    for scope, apply, restore in _import_brackets:
        if scope in resolved.parents:
            apply()
        else:
            restore()
    return None


def pytest_collection_finish(session: pytest.Session) -> None:
    """Restore every registered import replacement after collection."""
    for _scope, _apply, restore in _import_brackets:
        restore()
