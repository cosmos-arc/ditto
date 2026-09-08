"""Repository-wide file policies shared by hooks and static validation."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

FORBIDDEN_PACKAGE_MANAGER_FILES = frozenset(
    {
        ".npmrc",
        ".pnp.cjs",
        ".pnp.loader.mjs",
        ".pnpmfile.cjs",
        ".yarnrc",
        ".yarnrc.yml",
        "bun.lockb",
        "npm-shrinkwrap.json",
        "package-lock.json",
        "pnpm-lock.yaml",
        "pnpm-workspace.yml",
        "pnpm-workspace.yaml",
        "yarn.lock",
    }
)
FORBIDDEN_PACKAGE_MANAGER_DIRECTORIES = frozenset({".pnpm-store", ".yarn"})
_FALLBACK_EXCLUDED_DIRECTORIES = frozenset(
    {".cache", ".git", ".pixi", ".venv", "artifacts", "node_modules"}
)


def _nul_paths(root: Path, arguments: tuple[str, ...]) -> set[str] | None:
    try:
        result = subprocess.run(
            ["git", *arguments],
            cwd=root,
            capture_output=True,
            check=False,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    return {os.fsdecode(raw) for raw in result.stdout.split(b"\0") if raw}


def repository_paths(root: Path) -> set[str]:
    """Enumerate tracked and non-ignored untracked repository inputs."""
    indexed = _nul_paths(root, ("ls-files", "--cached", "-z", "--"))
    untracked = _nul_paths(
        root, ("ls-files", "--others", "--exclude-standard", "-z", "--")
    )
    if indexed is not None and untracked is not None:
        present_untracked = {
            path
            for path in untracked
            if (root / path).is_file() or (root / path).is_symlink()
        }
        return indexed | present_untracked

    paths: set[str] = set()
    for directory, names, filenames in os.walk(root):
        names[:] = [
            name for name in names if name not in _FALLBACK_EXCLUDED_DIRECTORIES
        ]
        base = Path(directory)
        paths.update(
            (base / filename).relative_to(root).as_posix() for filename in filenames
        )
    return paths


def is_forbidden_package_manager_path(path: str) -> bool:
    """Return whether a repository path violates the Bun-only policy."""
    parts = Path(path).parts
    if not parts:
        return False
    filename = parts[-1]
    return (
        (filename in {"bun.lock", "bunfig.toml"} and len(parts) > 1)
        or filename in FORBIDDEN_PACKAGE_MANAGER_FILES
        or bool(FORBIDDEN_PACKAGE_MANAGER_DIRECTORIES.intersection(parts))
    )


def forbidden_package_manager_paths(root: Path) -> tuple[str, ...]:
    """Find tracked and non-ignored untracked Bun-only policy violations."""
    return tuple(
        sorted(
            path
            for path in repository_paths(root)
            if is_forbidden_package_manager_path(path)
        )
    )
