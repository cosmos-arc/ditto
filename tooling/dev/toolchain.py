#!/usr/bin/env python3
"""Fail-closed validation for the root Pixi, Python, and Bun toolchains."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

VERSION_PATTERN = re.compile(r"(?P<version>\d+\.\d+(?:\.\d+)?)")
PIXI_REQUIREMENT_PATTERN = re.compile(
    r"(?P<operator>>=|<=|==|>|<)\s*(?P<version>\d+\.\d+(?:\.\d+)?)"
)


class ToolchainError(RuntimeError):
    """Raised when an installed tool cannot satisfy the repository contract."""


def _version_tuple(raw: str) -> tuple[int, int, int]:
    match = VERSION_PATTERN.search(raw)
    if match is None:
        raise ToolchainError(f"unable to parse tool version from {raw!r}")
    parts = [int(part) for part in match.group("version").split(".")]
    padded = [*parts, 0, 0]
    return padded[0], padded[1], padded[2]


def _satisfies_pixi_requirement(
    version: tuple[int, int, int], requirement: str
) -> bool:
    clauses = [clause.strip() for clause in requirement.split(",")]
    if not clauses or any(not clause for clause in clauses):
        raise ToolchainError(f"invalid requires-pixi constraint: {requirement!r}")
    for clause in clauses:
        match = PIXI_REQUIREMENT_PATTERN.fullmatch(clause)
        if match is None:
            raise ToolchainError(f"unsupported requires-pixi clause: {clause!r}")
        expected = _version_tuple(match.group("version"))
        operator = match.group("operator")
        satisfied = {
            ">=": version >= expected,
            "<=": version <= expected,
            "==": version == expected,
            ">": version > expected,
            "<": version < expected,
        }[operator]
        if not satisfied:
            return False
    return True


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
        "pixi": _run_version("pixi", "--version"),
        "python": ".".join(str(part) for part in sys.version_info[:3]),
    }


def validate_toolchain(root: Path, *, actual: dict[str, str] | None = None) -> None:
    """Validate installed tools against root manifests without mutating anything."""
    package = json.loads((root / "package.json").read_text(encoding="utf-8"))
    pixi = tomllib.loads((root / "pixi.toml").read_text(encoding="utf-8"))
    package_manager = package.get("packageManager")
    if not isinstance(package_manager, str) or not package_manager.startswith("bun@"):
        raise ToolchainError("package.json must pin packageManager to bun@<version>")
    expected_bun = package_manager.removeprefix("bun@")

    python_constraint = pixi.get("dependencies", {}).get("python")
    if not isinstance(python_constraint, str):
        raise ToolchainError("pixi.toml must declare the Python runtime")
    expected_python = python_constraint.removesuffix(".*")
    pixi_requirement = pixi.get("workspace", {}).get("requires-pixi")
    if not isinstance(pixi_requirement, str):
        raise ToolchainError("pixi.toml must declare workspace.requires-pixi")
    versions = installed_toolchains() if actual is None else actual

    if versions.get("bun") != expected_bun:
        raise ToolchainError(
            f"Bun mismatch: expected {expected_bun}, got {versions.get('bun')}"
        )
    if not versions.get("python", "").startswith(f"{expected_python}."):
        actual_python = versions.get("python")
        raise ToolchainError(
            f"Python mismatch: expected {expected_python}.x, got {actual_python}"
        )
    actual_pixi = versions.get("pixi", "")
    if not _satisfies_pixi_requirement(_version_tuple(actual_pixi), pixi_requirement):
        raise ToolchainError(
            f"Pixi mismatch: expected {pixi_requirement}, got {actual_pixi}"
        )


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
