"""Bind a production Python environment to its lock, interpreter source and platform."""

from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Mapping
from pathlib import Path


def environment_identity(root: Path, *, platform: str = "linux/amd64") -> str:
    """Hash the exact lock and immutable container bases used by the artifact gate."""
    inputs = {
        relative: hashlib.sha256((root / relative).read_bytes()).hexdigest()
        for relative in ("uv.lock", ".python-version", "deploy/docker/Dockerfile")
    }
    return identity_from_hashes(inputs, platform=platform)


def identity_from_hashes(inputs: Mapping[str, str], *, platform: str) -> str:
    """Use the same canonical input identity in builds and offline verification."""
    payload = {"schema_version": 1, "platform": platform, "inputs": dict(inputs)}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


if __name__ == "__main__":
    sys.stdout.write(environment_identity(Path.cwd()) + "\n")
