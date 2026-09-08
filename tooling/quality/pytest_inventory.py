"""Collect the final marked test inventory for isolated CI shards."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    """Require an explicit inventory destination."""
    parser.addoption("--inventory-output", required=True)


def pytest_collection_finish(session: pytest.Session) -> None:
    """Capture selected IDs and marks after all collection hooks."""
    Path(session.config.getoption("inventory_output")).write_text(
        json.dumps(
            sorted(
                (item.nodeid, item.get_closest_marker("serial") is not None)
                for item in session.items
            )
        )
        + "\n",
        encoding="utf-8",
    )
