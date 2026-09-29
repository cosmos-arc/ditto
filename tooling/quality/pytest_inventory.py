"""Collect the final marked test inventory for isolated CI shards."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    """Configure inventory capture or selection after custom collectors run."""
    parser.addoption("--inventory-output")
    parser.addoption("--selection-input")


def pytest_collection_finish(session: pytest.Session) -> None:
    """Capture selected IDs and marks after all collection hooks."""
    destination = session.config.getoption("inventory_output")
    if not destination:
        return
    Path(destination).write_text(
        json.dumps(
            sorted(
                (item.nodeid, item.get_closest_marker("serial") is not None)
                for item in session.items
            )
        )
        + "\n",
        encoding="utf-8",
    )


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Select final IDs after generated collectors, rejecting any missing proof."""
    source = config.getoption("selection_input")
    if not source:
        return
    requested = Path(source).read_text().splitlines()
    names = set(requested)
    selected = [item for item in items if item.nodeid in names]
    if len(names) != len(requested) or len(selected) != len(names):
        raise pytest.UsageError(
            "shard selection contains duplicate or missing test IDs"
        )
    deselected = [item for item in items if item.nodeid not in names]
    items[:] = selected
    config.hook.pytest_deselected(items=deselected)
