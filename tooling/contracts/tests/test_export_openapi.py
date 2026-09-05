"""Contract tests for the pure canonical OpenAPI exporter."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from tooling.contracts import export_openapi

_REPO_ROOT = Path(__file__).resolve().parents[3]


def test_importing_exporter_does_not_import_runtime_composition_root() -> None:
    """Schema generation must not construct the production application."""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "import tooling.contracts.export_openapi; "
                "assert 'ditto_apps.main' not in sys.modules"
            ),
        ],
        cwd=_REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_check_snapshot_is_byte_exact_and_never_rewrites(
    tmp_path: Path,
) -> None:
    snapshot = tmp_path / "v1.json"
    canonical = b'{\n  "openapi": "3.1.0"\n}\n'
    snapshot.write_bytes(canonical)

    export_openapi.check_snapshot(snapshot, canonical)

    stale = b'{"openapi":"3.1.0"}\n'
    snapshot.write_bytes(stale)
    with pytest.raises(export_openapi.SnapshotMismatchError, match="byte-identical"):
        export_openapi.check_snapshot(snapshot, canonical)
    assert snapshot.read_bytes() == stale
