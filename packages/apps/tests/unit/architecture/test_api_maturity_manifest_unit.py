"""API maturity manifest consistency tests."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
from ditto_apps.api.maturity import ROUTE_MATURITY_BY_PREFIX, ApiMaturity

_REPO_ROOT = Path(__file__).resolve().parents[5]
_MANIFEST = _REPO_ROOT / "docs" / "architecture" / "capability-maturity.md"
_SECTION_HEADER = "### API Route Maturity"

type ManifestRouteEntry = tuple[str, ApiMaturity, str]


def _normalize_manifest_prefix(prefix: str) -> str:
    if prefix in {"/", "/healthz"}:
        return prefix
    if prefix.startswith("/api/v1"):
        return prefix
    return f"/api/v1{prefix}"


def _manifest_route_entries() -> dict[str, ManifestRouteEntry]:
    lines = _MANIFEST.read_text(encoding="utf-8").splitlines()
    start = next(
        index for index, line in enumerate(lines) if line.startswith(_SECTION_HEADER)
    )
    entries: dict[str, ManifestRouteEntry] = {}

    for line in lines[start + 1 :]:
        if line.startswith("### "):
            break
        if not line.startswith("| `"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) != 3:
            continue
        raw_prefix = cells[0].strip("`")
        maturity = cast(ApiMaturity, cells[1])
        module = cells[2].strip("`")
        prefix = _normalize_manifest_prefix(raw_prefix)
        entries[prefix] = (raw_prefix, maturity, module)

    return entries


@pytest.mark.unit
def test_api_route_maturity_manifest_matches_openapi_prefix_registry() -> None:
    """Route maturity table and OpenAPI prefix registry should not drift."""
    manifest_entries = _manifest_route_entries()

    assert set(manifest_entries) == set(ROUTE_MATURITY_BY_PREFIX)
    for prefix, maturity in ROUTE_MATURITY_BY_PREFIX.items():
        assert manifest_entries[prefix][1] == maturity


@pytest.mark.unit
def test_api_route_maturity_manifest_module_paths_exist() -> None:
    """Manifest rows should point to concrete route or app modules."""
    app_src = _REPO_ROOT / "packages" / "apps" / "src" / "ditto_apps"
    for _, _, module in _manifest_route_entries().values():
        assert (app_src / module).is_file()
