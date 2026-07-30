"""Canonical static OpenAPI snapshot contract."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ditto_apps.main import app

_REPO_ROOT = Path(__file__).resolve().parents[5]
_SNAPSHOT_PATH = _REPO_ROOT / "docs/openapi/v1.json"


def _canonical_openapi_bytes(schema: dict[str, Any]) -> bytes:
    payload = json.dumps(
        schema,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    return f"{payload}\n".encode()


def test_static_openapi_matches_runtime_canonical_bytes() -> None:
    """Static OpenAPI is exactly the deterministic runtime projection."""
    actual = _SNAPSHOT_PATH.read_bytes()
    expected = _canonical_openapi_bytes(app.openapi())

    assert actual.endswith(b"\n")
    assert actual == expected
