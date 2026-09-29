"""
Single authoritative directory-to-layer rule for pytest markers.

Registered from the repository-root conftest, so every entry (single file,
owner tree, full testpaths, CI shards with ``-o addopts=``) applies the same
rule to the same nodeid. Near-tree conftests must not mutate foreign owners'
markers (#330 B1); the legacy per-package path hooks were removed in favor
of this module.

The rule is component-exact: a directory literally named ``integration`` /
``unit`` / ``contract`` / ``e2e`` **under the item's tests root** decides the
layer. Components above the last ``tests`` directory never match, so a
checkout path like ``/tmp/integration/ditto`` cannot flip every marker; file
names never match either. Explicit markers on a test always remain on top of
the directory layer. Unclassified test trees (registry, benchmarks,
``tooling/*/tests``) default to ``unit``.

``integration`` directories also carry ``serial`` — the blanket resource
policy inherited from the legacy hooks. The per-resource serial audit (#226)
lifts it tree by tree through the explicit registry below: an audited tree
keeps the ``integration`` layer marker and loses only the layer-implied
``serial``. Audit evidence and the disposition of every still-serial tree
live in ``docs/engineering/testing.md``; a tree-specific relapse is contained
by an explicit ``@pytest.mark.serial`` without touching the registry.

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

# Serial-audit opt-out (#226/#359/#363/#347): repo-relative integration trees whose
# blanket ``serial`` was lifted after a resource audit — per-test tmp/:memory:
# state, read-only immutable templates reused per worker, no ports,
# subprocesses or cross-test global init. Entries are matched as whole path
# components, so a sibling like ``integration-x`` never matches; new entries
# require the audit record in docs/engineering/testing.md.
_SERIAL_OPT_OUT_TREES: frozenset[str] = frozenset(
    {
        "packages/analysis/tests/integration",
        "packages/application/tests/integration",
        "packages/backtest/tests/integration",
        "packages/data/tests/integration",
        "packages/execution/tests/integration",
        "packages/platform/tests/integration",
        "packages/strategy/tests/integration",
    }
)

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


def _under_serial_opt_out(parts: tuple[str, ...]) -> bool:
    """Match whole path components so sibling trees never match."""
    for tree in _SERIAL_OPT_OUT_TREES:
        components = tuple(tree.split("/"))
        if parts[: len(components)] == components:
            return True
    return False


def layer_markers_for(path: Path, root: Path) -> tuple[str, ...]:
    """
    Markers implied by the layer directories under the item's tests root.

    Only components of the repository-relative path below its last ``tests``
    directory participate, so neither checkout ancestors (``/tmp/tests/...``
    or ``/tmp/integration/...``) nor their subdirectories can decide a layer.
    A module with no ``tests`` root inside the repository keeps the default
    layer.
    """
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        return _DEFAULT_LAYER
    for index in range(len(parts) - 1, -1, -1):
        if parts[index] == "tests":
            inner = parts[index + 1 :]
            for component, markers in _LAYER_BY_COMPONENT.items():
                if component in inner:
                    if "serial" in markers and _under_serial_opt_out(parts):
                        return tuple(name for name in markers if name != "serial")
                    return markers
            break
    return _DEFAULT_LAYER


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Add the directory layer markers to every collected item."""
    root = Path(config.rootpath)
    for item in items:
        for name in layer_markers_for(item.path, root):
            item.add_marker(getattr(pytest.mark, name))


def pytest_collectstart(collector: pytest.Collector) -> None:
    """
    Apply tree-scoped import brackets around each collector's run.

    A module is imported inside its collector's ``collect()``; this hook
    fires immediately before that collector runs, so the bracket stays
    correct even when pytest creates many collectors up front (CI shard
    ``@files`` invocations), where a collector-creation-time bracket would
    leave the replacement state matching only the last collector created.
    """
    if not _import_brackets:
        return
    path = getattr(collector, "path", None)
    if path is None:
        return
    resolved = Path(path).resolve()
    for scope, apply, restore in _import_brackets:
        if scope in resolved.parents:
            apply()
        else:
            restore()


def pytest_collection_finish(session: pytest.Session) -> None:
    """Restore every registered import replacement after collection."""
    for _scope, _apply, restore in _import_brackets:
        restore()
