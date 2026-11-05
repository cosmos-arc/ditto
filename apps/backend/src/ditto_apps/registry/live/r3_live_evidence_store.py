"""Small content-addressed evidence primitives shared by live acceptance flows."""

from __future__ import annotations

import hashlib
from pathlib import Path

import orjson

__all__ = ["canonical_bytes", "write_addressed"]


def canonical_bytes(value: object) -> bytes:
    """Render stable human-readable evidence bytes."""
    return (
        orjson.dumps(value, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS) + b"\n"
    )


def write_addressed(
    *,
    evidence_root: Path,
    category: str,
    payload: object,
) -> tuple[Path, str]:
    """Publish one immutable JSON evidence object under its SHA-256 identity."""
    content = canonical_bytes(payload)
    content_hash = hashlib.sha256(content).hexdigest()
    path = evidence_root / category / f"{content_hash}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() != content:
        raise ValueError("content-addressed live evidence replay drift")
    if not path.exists():
        path.write_bytes(content)
    return path, content_hash
