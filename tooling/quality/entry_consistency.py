"""
Compare per-nodeid marker sets across collection entries (#330 B1).

Runs the marker dump over representative entries — full testpaths, every
owner tree, the tooling trees outside testpaths (singly and combined the way
``task tooling-test`` invokes them), a mirrored CI shard collect, and sampled
single files — then requires each nodeid to carry an identical marker set in
every entry that collected it, and requires no entry to silently drop a
nodeid another entry collected. Exit 1 on drift, dropped membership, or a
failed entry; the comparison is per nodeid, never by case counts.
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

SHARD_EXCLUDED_MARKERS = ("snapshot", "sandbox_live", "capacity")
# Mirrors the CI shard collect expression in tooling/quality/test_shards.py; the
# tuple is the source of truth — splitting the expression string is unsafe
# because marker names themselves contain "and" (sandbox_live).
SHARD_EXPR = " and ".join(f"not {marker}" for marker in SHARD_EXCLUDED_MARKERS)
_ENTRY_TIMEOUT_SECONDS = 900
_SAMPLE_LIMIT = 10
_LAYER_MARKERS = frozenset({"unit", "integration", "e2e"})
_EXAMPLES_LIMIT = 3


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
        tooling = _trees(root, "tooling/*/tests")
        for tree in tooling:
            collect(f"tooling:{tree}", [tree])
        # Mirror how task tooling-test really invokes the tooling trees: one
        # pytest process over all of them, where a near-tree conftest could
        # mutate the others' collection.
        if tooling:
            collect("tooling:combined", tooling)
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


def _expr_allows(marks: list[str], excluded: tuple[str, ...]) -> bool:
    """Whether the marks survive a ``not <marker>`` exclusion set."""
    return not set(marks) & set(excluded)


def _dropped(name: str, dump: dict[str, list[str]], reference: set[str]) -> list[str]:
    """Nodeids an entry collected that the reference entry silently dropped."""
    return sorted(set(dump) - reference)


def _membership_failures(dumps: dict[str, dict[str, list[str]]]) -> list[str]:
    """No entry may drop a nodeid its reference entry collected."""
    failures: list[str] = []
    full = dumps["full"]
    full_ids = set(full)
    for name, dump in sorted(dumps.items()):
        if name.startswith("owner:"):
            dropped = _dropped(name, dump, full_ids)
            if dropped:
                examples = ", ".join(dropped[:_EXAMPLES_LIMIT])
                failures.append(
                    f"{name} collected {len(dropped)} nodeids the full entry"
                    + f" dropped, e.g. {examples}"
                )
    shard_ids = set(dumps["shard"])
    expected_shard = {
        nodeid
        for nodeid, marks in full.items()
        if _expr_allows(marks, SHARD_EXCLUDED_MARKERS)
    }
    missing = sorted(expected_shard - shard_ids)
    if missing:
        examples = ", ".join(missing[:_EXAMPLES_LIMIT])
        failures.append(
            f"shard dropped {len(missing)} expected nodeids, e.g. {examples}"
        )
    unexpected = sorted(shard_ids - full_ids)
    if unexpected:
        examples = ", ".join(unexpected[:_EXAMPLES_LIMIT])
        failures.append(
            f"shard collected {len(unexpected)} nodeids outside the full entry,"
            + f" e.g. {examples}"
        )
    if "tooling:combined" in dumps:
        combined_ids = set(dumps["tooling:combined"])
        for name, dump in sorted(dumps.items()):
            if name.startswith("tooling:") and name != "tooling:combined":
                dropped = _dropped(name, dump, combined_ids)
                if dropped:
                    examples = ", ".join(dropped[:_EXAMPLES_LIMIT])
                    failures.append(
                        f"{name} collected {len(dropped)} nodeids the combined"
                        + f" tooling entry dropped, e.g. {examples}"
                    )
    return failures


def _marker_drift(
    dumps: dict[str, dict[str, list[str]]],
) -> dict[str, dict[str, tuple[str, ...]]]:
    marks_per_nodeid: dict[str, dict[str, tuple[str, ...]]] = defaultdict(dict)
    for entry, dump in dumps.items():
        for nodeid, marks in dump.items():
            marks_per_nodeid[nodeid][entry] = tuple(marks)
    return {
        nodeid: per
        for nodeid, per in marks_per_nodeid.items()
        if len(set(per.values())) > 1
    }


def _compare(dumps: dict[str, dict[str, list[str]]]) -> int:
    drift = _marker_drift(dumps)
    membership = _membership_failures(dumps)
    for entry in sorted(dumps):
        print(f"{entry}: {len(dumps[entry])} items")
    if not drift and not membership:
        total = len({nodeid for dump in dumps.values() for nodeid in dump})
        print(f"entry consistency: {total} nodeids stable")
        return 0
    if drift:
        print(f"entry drift on {len(drift)} nodeids; first examples:")
        for nodeid, per in sorted(drift.items())[:20]:
            print(f"  {nodeid}")
            for entry in sorted(per):
                print(f"    {entry}: {list(per[entry])}")
    for failure in membership:
        print(f"membership failure: {failure}")
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
