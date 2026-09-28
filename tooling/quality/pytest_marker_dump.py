"""
Dump per-nodeid marker sets after collection (entry-consistency evidence).

Activated through ``-p tooling.quality.pytest_marker_dump`` with the output
path in the ``MARKER_DUMP`` environment variable; runs after the layering
plugin so the dump reflects final markers.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Write ``{nodeid: sorted marker names}`` for every collected item."""
    destination = os.environ.get("MARKER_DUMP")
    if not destination:
        return
    dump = {
        item.nodeid: sorted({marker.name for marker in item.iter_markers()})
        for item in items
    }
    Path(destination).write_text(json.dumps(dump, sort_keys=True), encoding="utf-8")
