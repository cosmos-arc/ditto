"""Atomically export the pure non-debug OpenAPI contract."""

from __future__ import annotations

import os
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any

from ditto_apps.main import app
from ditto_apps.openapi_contract import canonical_openapi_bytes

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_OUTPUT_PATH = _REPO_ROOT / "docs/openapi/v1.json"
_NON_CONTRACT_PATHS = frozenset({"/api/v1/logs/test"})


def runtime_openapi_schema() -> dict[str, Any]:
    """Project the runtime schema onto the public, non-debug API contract."""
    schema = deepcopy(app.openapi())
    paths = schema.get("paths")
    if not isinstance(paths, dict):
        raise RuntimeError("runtime OpenAPI schema has no paths object")
    schema["paths"] = {
        path: path_item
        for path, path_item in paths.items()
        if path not in _NON_CONTRACT_PATHS
    }
    return schema


def canonical_runtime_openapi_bytes() -> bytes:
    """Return the one canonical byte projection used by export and tests."""
    return canonical_openapi_bytes(runtime_openapi_schema())


def _fsync_directory(path: Path) -> None:
    """Persist a successful rename in the containing directory."""
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    directory_fd = os.open(path, flags)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def export_openapi(output_path: Path = _DEFAULT_OUTPUT_PATH) -> Path:
    """Atomically write the explicit non-debug contract without runtime setup."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical_runtime_openapi_bytes()
    file_descriptor, temporary_name = tempfile.mkstemp(
        dir=output_path.parent,
        prefix=f".{output_path.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "wb") as temporary_file:
            temporary_file.write(payload)
            temporary_file.flush()
            os.fchmod(temporary_file.fileno(), 0o644)
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, output_path)  # noqa: PTH105
        _fsync_directory(output_path.parent)
    finally:
        temporary_path.unlink(missing_ok=True)
    return output_path


def main() -> None:
    """Export the default checked-in snapshot."""
    output_path = export_openapi()
    print(output_path)


if __name__ == "__main__":
    main()
