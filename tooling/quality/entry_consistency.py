"""
Compare per-nodeid marker sets across collection entries (#330 B1).

Runs the marker dump over representative entries — full testpaths, every
owner tree, the tooling trees outside testpaths, a mirrored CI shard
collect, and sampled single files — then requires each nodeid to carry an
identical marker set in every entry that collected it. Exit 1 on any drift
or failed entry; the comparison is per nodeid, never by case counts.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

SHARD_EXPR = "not snapshot and not sandbox_live and not capacity"
_ENTRY_TIMEOUT_SECONDS = 900
_SAMPLE_LIMIT = 10
_LAYER_MARKERS = frozenset({"unit", "integration", "e2e"})


def _trees(root: Path, pattern: str) -> list[str]:
    return sorted(
        str(path.relative_to(root)) for path in root.glob(pattern) if path.is_dir()
    )


def _slug(name: str) -> str:
    """Filesystem-safe dump name for an entry label."""
    return name.replace(":", "__").replace("/", "-")


def _collect(
    root: Path, name: str, args: list[str], dump: Path
) -> dict[str, list[str]]:
    """Collect one entry and return its ``{nodeid: markers}`` dump."""
    environment = {**os.environ, "MARKER_DUMP": str(dump)}
    try:
        proc = subprocess.run(  # noqa: S603 - fixed interpreter and pytest args
            [
                sys.executable,
                "-m",
                "pytest",
                *args,
                "-p",
                "tooling.quality.pytest_marker_dump",
                "--collect-only",
                "-q",
                "--no-header",
            ],
            cwd=root,
            env=environment,
            capture_output=True,
            text=True,
            timeout=_ENTRY_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise SystemExit(f"[fail] {name}: {error!r}") from error
    if proc.returncode != 0 or not dump.is_file():
        tail = (proc.stderr + proc.stdout)[-2000:]
        raise SystemExit(f"[fail] {name}: rc={proc.returncode}\n{tail}")
    return json.loads(dump.read_text(encoding="utf-8"))


def _sample_files(
    dumps: dict[str, dict[str, list[str]]], limit: int
) -> list[tuple[str, str]]:
    """One representative file per (tree, layer) from already-collected dumps."""
    chosen: dict[tuple[str, str], str] = {}
    for entry, dump in dumps.items():
        tree = entry.split(":", 1)[1] if ":" in entry else ""
        for nodeid, marks in dump.items():
            path = nodeid.split("::", 1)[0]
            if not path.endswith(".py"):
                continue
            layers = ",".join(sorted(set(marks) & _LAYER_MARKERS)) or "none"
            key = (tree, layers)
            if key not in chosen:
                chosen[key] = path
    return [(f"{tree}:{layers}", path) for (tree, layers), path in chosen.items()][
        :limit
    ]


def _run_entries(root: Path) -> dict[str, dict[str, list[str]]]:
    dumps: dict[str, dict[str, list[str]]] = {}
    with tempfile.TemporaryDirectory(prefix="entry-consistency-") as tmp:
        dump_dir = Path(tmp)

        def collect(name: str, args: list[str]) -> None:
            dumps[name] = _collect(root, name, args, dump_dir / f"{_slug(name)}.json")

        collect("full", [])
        owners = _trees(root, "packages/*/tests")
        if (root / "apps/backend/tests").is_dir():
            owners.append("apps/backend/tests")
        for tree in owners:
            collect(f"owner:{tree}", [tree])
        for tree in _trees(root, "tooling/*/tests"):
            collect(f"tooling:{tree}", [tree])
        collect(
            "shard",
            [
                "-o",
                "addopts=",
                "-p",
                "tooling.quality.pytest_inventory",
                "--import-mode=importlib",
                "-m",
                SHARD_EXPR,
            ],
        )
        for label, path in _sample_files(dumps, _SAMPLE_LIMIT):
            collect(f"single:{label}", [path])
    return dumps


def _compare(dumps: dict[str, dict[str, list[str]]]) -> int:
    marks_per_nodeid: dict[str, dict[str, tuple[str, ...]]] = defaultdict(dict)
    for entry, dump in dumps.items():
        for nodeid, marks in dump.items():
            marks_per_nodeid[nodeid][entry] = tuple(marks)
    drift = {
        nodeid: per
        for nodeid, per in marks_per_nodeid.items()
        if len(set(per.values())) > 1
    }
    for entry in sorted(dumps):
        print(f"{entry}: {len(dumps[entry])} items")
    if not drift:
        print(f"entry consistency: {len(marks_per_nodeid)} nodeids stable")
        return 0
    print(f"entry drift on {len(drift)} nodeids; first examples:")
    for nodeid, per in sorted(drift.items())[:20]:
        print(f"  {nodeid}")
        for entry in sorted(per):
            print(f"    {entry}: {list(per[entry])}")
    return 1


def main(argv: list[str] | None = None) -> int:
    """Entry point: run the entries, then compare per-nodeid markers."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="repository root")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    dumps = _run_entries(root)
    return _compare(dumps)


if __name__ == "__main__":
    raise SystemExit(main())
