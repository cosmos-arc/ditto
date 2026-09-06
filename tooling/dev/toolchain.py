#!/usr/bin/env python3
"""Fail-closed validation for the root uv, Task, Python, Node, and Bun toolchains."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

VERSION_PATTERN = re.compile(r"(?P<version>\d+\.\d+(?:\.\d+)?)")


class ToolchainError(RuntimeError):
    """Raised when an installed tool cannot satisfy the repository contract."""


def _run_version(executable: str, *arguments: str) -> str:
    resolved = shutil.which(executable)
    if resolved is None:
        raise ToolchainError(f"required tool is unavailable: {executable}")
    result = subprocess.run(
        [resolved, *arguments], capture_output=True, text=True, check=False
    )
    output = (result.stdout or result.stderr).strip()
    if result.returncode != 0 or not output:
        raise ToolchainError(f"unable to query {executable} version: {output}")
    return output


def installed_toolchains() -> dict[str, str]:
    """Return versions from the executables used by the current process."""
    return {
        "bun": _run_version("bun", "--version"),
        "node": _run_version("node", "--version"),
        "uv": _run_version("uv", "--version"),
        "task": _run_version("task", "--version"),
        "python": ".".join(str(part) for part in sys.version_info[:3]),
    }


def validate_node(root: Path, version: str) -> None:
    """Require the exact Node runtime declared for local and CI execution."""
    expected = (root / ".node-version").read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+", expected):
        raise ToolchainError(".node-version must pin an exact Node version")
    if version.removeprefix("v") != expected:
        raise ToolchainError(f"Node mismatch: expected {expected}, got {version!r}")


def node_executable(root: Path) -> str:
    """Resolve and validate Node without installing or changing the environment."""
    executable = shutil.which("node")
    if executable is None:
        raise ToolchainError(
            "Node is unavailable; install the version in .node-version"
        )
    validate_node(root, _run_version(executable, "--version"))
    subprocess.run(["bun", str(root / "tooling/dev/bun-workspace.mjs")], check=True)
    return executable


def validate_toolchain(root: Path, *, actual: dict[str, str] | None = None) -> None:
    """Validate installed tools against root manifests without mutating anything."""
    package = json.loads((root / "package.json").read_text(encoding="utf-8"))
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    manager = package.get("packageManager", "")
    if not isinstance(manager, str) or not re.fullmatch(r"bun@\d+\.\d+\.\d+", manager):
        raise ToolchainError("package.json must pin packageManager to bun@<version>")
    expected = {
        "bun": manager.removeprefix("bun@"),
        "python": (root / ".python-version")
        .read_text(encoding="utf-8")
        .strip()
        .removeprefix("cpython-"),
        "uv": project["tool"]["uv"]["required-version"].removeprefix("=="),
        "task": (root / ".task-version").read_text(encoding="utf-8").strip(),
    }
    versions = installed_toolchains() if actual is None else actual
    for name, version in expected.items():
        found = VERSION_PATTERN.search(versions.get(name, ""))
        if not found or found.group("version") != version:
            label = {"bun": "Bun", "python": "Python", "task": "Task"}.get(name, name)
            raise ToolchainError(
                f"{label} mismatch: expected {version}, got {versions.get(name)!r}"
            )
    validate_node(root, versions.get("node", ""))


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    try:
        versions = installed_toolchains()
        validate_toolchain(root, actual=versions)
    except (OSError, ValueError, ToolchainError, tomllib.TOMLDecodeError) as error:
        print(f"Toolchain validation failed: {error}", file=sys.stderr)
        return 1
    print(
        "Toolchain validation passed: "
        + ", ".join(f"{name}={value}" for name, value in sorted(versions.items()))
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
