"""Export the runtime OpenAPI schema as deterministic canonical JSON."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ditto_apps.main import app

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_OUTPUT_PATH = _REPO_ROOT / "docs/openapi/v1.json"


def canonical_openapi_bytes(schema: dict[str, Any]) -> bytes:
    """Serialize an OpenAPI document with stable key order and one final newline."""
    payload = json.dumps(
        schema,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    return f"{payload}\n".encode()


def export_openapi(output_path: Path = _DEFAULT_OUTPUT_PATH) -> Path:
    """Write the in-process FastAPI OpenAPI projection without starting a server."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(canonical_openapi_bytes(app.openapi()))
    return output_path


def main() -> None:
    """Export the default checked-in snapshot."""
    output_path = export_openapi()
    print(output_path)


if __name__ == "__main__":
    main()
