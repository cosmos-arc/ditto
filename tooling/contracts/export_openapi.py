"""Export and verify the pure, canonical, non-debug OpenAPI contract."""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any

from ditto_apps.openapi_contract import canonical_openapi_bytes, create_openapi_app

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_OUTPUT_PATH = _REPO_ROOT / "contracts/openapi/v1.json"


class SnapshotMismatchError(RuntimeError):
    """The checked-in OpenAPI snapshot is not the canonical factory export."""


def runtime_openapi_schema() -> dict[str, Any]:
    """Build the public schema without importing the runtime composition root."""
    schema = deepcopy(create_openapi_app(include_debug=False).openapi())
    paths = schema.get("paths")
    if not isinstance(paths, dict):
        raise RuntimeError("pure OpenAPI schema has no paths object")
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


def check_snapshot(snapshot_path: Path, canonical_payload: bytes) -> None:
    """Require a snapshot to match canonical bytes without mutating it."""
    try:
        actual_payload = snapshot_path.read_bytes()
    except FileNotFoundError as error:
        raise SnapshotMismatchError(
            f"OpenAPI snapshot is missing: {snapshot_path}"
        ) from error
    if actual_payload != canonical_payload:
        raise SnapshotMismatchError(
            "".join(
                (
                    "OpenAPI snapshot is not byte-identical to the canonical export: ",
                    f"{snapshot_path}. Run this module with --write.",
                )
            )
        )


def check_runtime_snapshot(snapshot_path: Path = _DEFAULT_OUTPUT_PATH) -> None:
    """Export through a temporary file, then byte-compare the snapshot."""
    with tempfile.TemporaryDirectory(prefix="ditto-openapi-export-") as directory:
        candidate_path = Path(directory) / snapshot_path.name
        export_openapi(candidate_path)
        check_snapshot(snapshot_path, candidate_path.read_bytes())


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check",
        action="store_true",
        help="verify canonical bytes without modifying the snapshot (default)",
    )
    mode.add_argument(
        "--write",
        action="store_true",
        help="atomically refresh the checked-in snapshot",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=_DEFAULT_OUTPUT_PATH,
        help="snapshot path (defaults to contracts/openapi/v1.json)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Check by default; mutate the snapshot only with explicit ``--write``."""
    arguments = _parser().parse_args(argv)
    output_path = arguments.output.resolve()
    if arguments.write:
        export_openapi(output_path)
        sys.stdout.write(f"OpenAPI snapshot updated: {output_path}\n")
        return 0
    try:
        check_runtime_snapshot(output_path)
    except SnapshotMismatchError as error:
        sys.stderr.write(f"{error}\n")
        return 1
    sys.stdout.write(f"OpenAPI snapshot is canonical: {output_path}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
