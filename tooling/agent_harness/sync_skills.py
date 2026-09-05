#!/usr/bin/env python3
"""Mirror canonical project skills into Claude Code's discovery directory."""

from __future__ import annotations

import argparse
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / ".agents" / "skills"
MIRROR = ROOT / ".claude" / "skills"


@dataclass(frozen=True)
class TreeEntry:
    """Portable file identity required for a trustworthy generated mirror."""

    kind: str
    content: bytes
    executable: bool


def tree_files(root: Path) -> dict[str, TreeEntry]:
    """Return deterministic content, kind, and executable-bit identities."""
    if not root.is_dir():
        return {}
    entries: dict[str, TreeEntry] = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            entry = TreeEntry(
                kind="symlink",
                content=os.fsencode(path.readlink()),
                executable=False,
            )
        elif path.is_file():
            entry = TreeEntry(
                kind="file",
                content=path.read_bytes(),
                executable=bool(path.stat().st_mode & 0o111),
            )
        else:
            continue
        entries[path.relative_to(root).as_posix()] = entry
    return entries


def compare_trees(source: Path = SOURCE, mirror: Path = MIRROR) -> list[str]:
    """Describe missing, extra, and changed files between two skill trees."""
    source_files = tree_files(source)
    mirror_files = tree_files(mirror)
    problems: list[str] = []
    for relative in sorted(source_files.keys() - mirror_files.keys()):
        problems.append(f"missing from Claude mirror: {relative}")
    for relative in sorted(mirror_files.keys() - source_files.keys()):
        problems.append(f"extra in Claude mirror: {relative}")
    for relative in sorted(source_files.keys() & mirror_files.keys()):
        canonical = source_files[relative]
        generated = mirror_files[relative]
        if canonical.kind != generated.kind:
            problems.append(f"kind drift: {relative}")
        elif canonical.executable != generated.executable:
            problems.append(f"executable mode drift: {relative}")
        elif canonical.content != generated.content:
            problems.append(f"content drift: {relative}")
    return problems


def sync(source: Path = SOURCE, mirror: Path = MIRROR) -> None:
    """Replace the generated mirror after validating the canonical source."""
    if not source.is_dir() or not any(source.iterdir()):
        raise SystemExit(f"canonical skill directory is missing or empty: {source}")
    if mirror.exists():
        shutil.rmtree(mirror)
    shutil.copytree(source, mirror, symlinks=True, copy_function=shutil.copy2)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="fail if the mirror differs"
    )
    args = parser.parse_args()

    if args.check:
        problems = compare_trees()
        if problems:
            print("Agent skill mirror is out of sync:")
            for problem in problems:
                print(f"- {problem}")
            return 1
        print("Agent skill mirror is synchronized.")
        return 0

    sync()
    print(f"Mirrored {SOURCE.relative_to(ROOT)} -> {MIRROR.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
