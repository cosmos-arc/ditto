"""Fail closed on oversized repository files without an exact audited fingerprint."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import TypedDict, cast

_SHA256_HEX_LENGTH = 64


class _Allowance(TypedDict):
    path: str
    sha256: str
    reason: str


class LargeFilePolicyError(RuntimeError):
    """Raised when repository files or policy cannot be proven safe."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _repository_files(root: Path) -> tuple[Path, ...]:
    git = shutil.which("git")
    if git is None:
        raise LargeFilePolicyError("git executable is unavailable")
    result = subprocess.run(  # noqa: S603
        [git, "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=root,
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        raise LargeFilePolicyError("could not enumerate repository files")
    paths: list[Path] = []
    for raw in result.stdout.split(b"\0"):
        if not raw:
            continue
        relative = Path(os.fsdecode(raw))
        candidate = root / relative
        if candidate.is_file() and not candidate.is_symlink():
            paths.append(relative)
    return tuple(paths)


def _load_policy(root: Path) -> tuple[int, dict[str, _Allowance]]:
    loaded = tomllib.loads((root / ".large-files.toml").read_text(encoding="utf-8"))
    if loaded.get("schema_version") != 1:
        raise LargeFilePolicyError("large-file policy schema must be 1")
    maximum = loaded.get("max_bytes")
    raw_allowances = loaded.get("allow")
    if not isinstance(maximum, int) or maximum <= 0:
        raise LargeFilePolicyError("large-file max_bytes must be positive")
    if not isinstance(raw_allowances, list):
        raise LargeFilePolicyError("large-file allow must be an array")
    allowances: dict[str, _Allowance] = {}
    for raw in raw_allowances:
        if not isinstance(raw, dict):
            raise LargeFilePolicyError("large-file allowance must be a table")
        allowance = cast("_Allowance", raw)
        path = allowance.get("path")
        digest = allowance.get("sha256")
        reason = allowance.get("reason")
        if (
            not isinstance(path, str)
            or not path
            or path in allowances
            or not isinstance(digest, str)
            or len(digest) != _SHA256_HEX_LENGTH
            or any(character not in "0123456789abcdef" for character in digest)
            or not isinstance(reason, str)
            or not reason.strip()
        ):
            raise LargeFilePolicyError("large-file allowance is invalid or duplicated")
        allowances[path] = allowance
    return maximum, allowances


def validate_large_files(root: Path) -> list[str]:
    """Return deterministic violations for tracked and non-ignored untracked files."""
    workspace = root.expanduser().resolve(strict=True)
    maximum, allowances = _load_policy(workspace)
    violations: list[str] = []
    observed_allowances: set[str] = set()
    for relative in _repository_files(workspace):
        normalized = relative.as_posix()
        candidate = workspace / relative
        if candidate.stat().st_size <= maximum:
            continue
        allowance = allowances.get(normalized)
        if allowance is None:
            violations.append(
                f"{normalized}: exceeds {maximum} bytes without an allowance"
            )
            continue
        observed_allowances.add(normalized)
        actual = _sha256(candidate)
        if actual != allowance["sha256"]:
            violations.append(f"{normalized}: allowance SHA-256 does not match")
    stale = sorted(set(allowances) - observed_allowances)
    violations.extend(f"{path}: stale large-file allowance" for path in stale)
    return sorted(violations)


def main() -> int:
    """Validate the workspace large-file policy."""
    root = Path(__file__).resolve().parents[2]
    try:
        violations = validate_large_files(root)
    except (LargeFilePolicyError, OSError, tomllib.TOMLDecodeError) as error:
        sys.stderr.write(f"large-file-check: FAIL: {error}\n")
        return 1
    if violations:
        sys.stderr.write("large-file-check: FAIL\n" + "\n".join(violations) + "\n")
        return 1
    sys.stdout.write("large-file-check: PASS\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
