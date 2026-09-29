"""
Fail-closed proof that required suites executed exactly once in shards.

Replaces blind re-execution of deduplicated suites (#350): the pit-marked
suite and the OpenAPI conformance file keep their CI guarantee by proving,
from shard artifacts alone, that every required nodeid was selected exactly
once and every selected lane produced a matching junit report. Removing the
dedicated ``task pit`` / conformance re-run must never be able to hide a
missing or silently skipped required test.
"""

from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

_INVENTORY_FIELD_COUNT = 3


class EvidenceError(ValueError):
    """Required-suite evidence is missing, duplicated or inconsistent."""


def _glob(pattern: str) -> list[Path]:
    candidate = Path(pattern)
    return sorted(candidate.parent.glob(candidate.name))


def _load_inventories(pattern: str) -> list[tuple[str, bool, bool]]:
    paths = _glob(pattern)
    if not paths:
        raise EvidenceError(f"no inventory artifacts match {pattern}")
    records: list[tuple[str, bool, bool]] | None = None
    for path in paths:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, list):
            raise EvidenceError(f"inventory {path} is not a list")
        current = []
        for item in value:
            if (
                not isinstance(item, list)
                or len(item) != _INVENTORY_FIELD_COUNT
                or not isinstance(item[0], str)
                or not isinstance(item[1], bool)
                or not isinstance(item[2], bool)
            ):
                raise EvidenceError(f"inventory {path} has a malformed entry")
            current.append((item[0], item[1], item[2]))
        if records is None:
            records = current
        elif records != current:
            raise EvidenceError(f"inventory {path} differs from the first shard")
    if records is None:  # pragma: no cover - paths 非空时 records 必已被赋值
        raise EvidenceError("no inventory artifacts were loaded")
    return records


def _required(
    inventory: list[tuple[str, bool, bool]],
    *,
    pit_marker: bool,
    path: str | None,
) -> list[str]:
    selected = [
        nodeid
        for nodeid, _serial, pit in inventory
        if (pit_marker and pit) or (path and nodeid.startswith(path + "::"))
    ]
    if not selected:
        raise EvidenceError(
            "required suite selected no tests: marker or path no longer matches "
            "any collected nodeid"
        )
    return selected


def _selected_counts(pattern: str) -> Counter[str]:
    paths = _glob(pattern)
    if not paths:
        raise EvidenceError(f"no selection artifacts match {pattern}")
    counts: Counter[str] = Counter()
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line:
                counts[line] += 1
    return counts


def _verify_junit_matches_selection(junit_pattern: str, nodes_pattern: str) -> None:
    junit_paths = _glob(junit_pattern)
    if not junit_paths:
        raise EvidenceError(f"no junit artifacts match {junit_pattern}")
    nodes_paths = _glob(nodes_pattern)
    junit_by_lane = {
        p.name.removeprefix("junit-").removesuffix(".xml"): p for p in junit_paths
    }
    nodes_by_lane = {
        p.name.removeprefix("nodes-").removesuffix(".txt"): p for p in nodes_paths
    }
    for lane, nodes_path in nodes_by_lane.items():
        junit_path = junit_by_lane.get(lane)
        if junit_path is None:
            raise EvidenceError(f"lane {lane} has selection but no junit report")
        expected = sum(
            1 for line in nodes_path.read_text(encoding="utf-8").splitlines() if line
        )
        root = ET.parse(junit_path).getroot()  # noqa: S314 - junit 来自本仓 CI 工件
        total = sum(int(suite.get("tests", 0)) for suite in root.iter("testsuite"))
        errors = sum(int(suite.get("errors", 0)) for suite in root.iter("testsuite"))
        if errors:
            raise EvidenceError(f"lane {lane} junit reports {errors} collection errors")
        if total != expected:
            raise EvidenceError(
                f"lane {lane} junit records {total} tests but {expected} were selected"
            )


def run_checks(
    inventory_glob: str,
    nodes_glob: str,
    junit_glob: str,
    *,
    pit_marker: bool,
    path: str | None,
) -> dict[str, object]:
    """Prove the required suite executed exactly once; raise on any gap."""
    inventory = _load_inventories(inventory_glob)
    required = _required(inventory, pit_marker=pit_marker, path=path)
    selected = _selected_counts(nodes_glob)
    _verify_junit_matches_selection(junit_glob, nodes_glob)

    missing = [nodeid for nodeid in required if selected[nodeid] == 0]
    duplicated = [nodeid for nodeid in required if selected[nodeid] > 1]
    if missing or duplicated:
        details = []
        if missing:
            details.append(f"missing from shard selection ({len(missing)}):")
            details.extend(f"  {nodeid}" for nodeid in missing[:20])
        if duplicated:
            details.append(f"duplicated across shard selection ({len(duplicated)}):")
            details.extend(f"  {nodeid}" for nodeid in duplicated[:20])
        raise EvidenceError("\n".join(details))

    return {
        "required": len(required),
        "selection": "exactly-once",
        "junit": "lanes-consistent",
        "suite": "pit" if pit_marker else path,
    }


def main(argv: list[str] | None = None) -> int:
    """Parse artifact globs and run the fail-closed checks."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory-glob", required=True)
    parser.add_argument("--nodes-glob", required=True)
    parser.add_argument("--junit-glob", required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--pit-marker", action="store_true")
    group.add_argument("--path")
    args = parser.parse_args(argv)
    result = run_checks(
        args.inventory_glob,
        args.nodes_glob,
        args.junit_glob,
        pit_marker=args.pit_marker,
        path=args.path,
    )
    sys.stdout.write(json.dumps(result, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except EvidenceError as error:
        sys.stderr.write(f"required-suite evidence failed: {error}\n")
        raise SystemExit(1) from error
