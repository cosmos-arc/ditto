"""Minimal Docker archive for offline environment-binding counterexamples."""

from __future__ import annotations

import hashlib
import io
import json
import tarfile
from pathlib import Path

from tooling.release.environment_identity import identity_from_hashes


def write_image(path: Path, inputs_root: Path, *, staged: bool = True) -> None:
    inputs = {
        name: hashlib.sha256(
            (inputs_root / (Path(name).name if staged else name)).read_bytes()
        ).hexdigest()
        for name in ("uv.lock", ".python-version", "deploy/docker/Dockerfile")
    }
    version = (
        (inputs_root / ".python-version").read_text().strip().removeprefix("cpython-")
    )
    config = {
        "os": "linux",
        "architecture": "amd64",
        "config": {
            "Env": [
                "DITTO_RESEARCH_ENVIRONMENT_LOCK_HASH="
                + identity_from_hashes(inputs, platform="linux/amd64"),
                "PYTHON_VERSION=" + version,
            ]
        },
    }
    with tarfile.open(path, "w") as archive:
        for name, value in (
            ("manifest.json", [{"Config": "config.json"}]),
            ("config.json", config),
        ):
            payload = json.dumps(value).encode()
            member = tarfile.TarInfo(name)
            member.size = len(payload)
            archive.addfile(member, io.BytesIO(payload))
