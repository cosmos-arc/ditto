"""Shared JSON helpers for derived catalog runtime stores."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import orjson
from ditto_datahub.models.derived import JsonDict
from ditto_infra.foundation.util.io import atomic_bytes_write


def read_json_file(path: Path) -> JsonDict | None:
    """Read a JSON file into a dictionary."""
    if not path.exists():
        return None

    data = orjson.loads(path.read_bytes())
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return cast(JsonDict, data)


def write_json_file(path: Path, payload: JsonDict) -> None:
    """Write a JSON dictionary to disk atomically."""
    atomic_bytes_write(orjson.dumps(payload, option=orjson.OPT_INDENT_2), path)


def list_json_files(path: Path) -> list[Path]:
    """Return sorted JSON files under a directory."""
    if not path.exists():
        return []
    return sorted(file_path for file_path in path.glob("*.json") if file_path.is_file())
