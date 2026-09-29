"""
Fail-closed proof that required suites executed exactly once in shards.

Replaces blind re-execution of deduplicated suites (#350): the pit-marked
suite and the OpenAPI conformance file keep their CI guarantee by proving
that every required nodeid was selected exactly once by the shards and every
selected lane produced a matching junit report. The required set comes from
an UNFILTERED live marker collection, so a pit-marked test that also carries
snapshot/sandbox_live/capacity cannot silently fall out of the proof.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]


class EvidenceError(ValueError):
    """Required-suite evidence is missing, duplicated or inconsistent."""


def collect_marker_dump(dump_path: Path) -> dict[str, list[str]]:
    """Collect the unfiltered marker dump for this working tree (#350 P2)."""
    environment = {
        **os.environ,
        "PYTHONPATH": str(_REPO_ROOT),
        "MARKER_DUMP": str(dump_path),
    }
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-o",
            "addopts=",
            "--import-mode=importlib",
            "-p",
            "tooling.quality.pytest_marker_dump",
            "--collect-only",
            "-q",
            "--no-header",
        ],
        cwd=_REPO_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    if proc.returncode != 0 or not dump_path.is_file():
        detail = f"{proc.stdout[-2000:]}\n{proc.stderr[-2000:]}"
        raise EvidenceError(f"unfiltered marker collection failed:\n{detail}")
    return json.loads(dump_path.read_text(encoding="utf-8"))


def required_from_dump(
    dump: dict[str, list[str]],
    *,
    pit_marker: bool,
    path: str | None,
) -> list[str]:
    """Derive the required nodeids from the unfiltered marker dump."""
    selected = [
        nodeid
        for nodeid, markers in dump.items()
        if (pit_marker and "pit" in markers)
        or (path and nodeid.startswith(path + "::"))
    ]
    if not selected:
        raise EvidenceError(
            "required suite selected no tests: marker or path no longer matches "
            "any collected nodeid"
        )
    return selected


def _glob(pattern: str) -> list[Path]:
    """Glob with the base anchored at the first wildcard-free prefix."""
    parts = Path(pattern).parts
    base: list[str] = []
    rest: list[str] = []
    for part in parts:
        if rest or any(ch in part for ch in "*?["):
            rest.append(part)
        else:
            base.append(part)
    if not rest:
        raise EvidenceError(f"pattern has no wildcard component: {pattern}")
    root = Path(*base) if base else Path.cwd()
    return sorted(root.glob(str(Path(*rest))))


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
    required: list[str],
    *,
    nodes_glob: str,
    junit_glob: str,
) -> dict[str, object]:
    """Prove the required suite executed exactly once; raise on any gap."""
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
    }


def main(argv: list[str] | None = None) -> int:
    """Collect markers live, then verify shard artifacts fail-closed."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nodes-glob", required=True)
    parser.add_argument("--junit-glob", required=True)
    selectors = parser.add_argument_group("required suite selectors (union)")
    selectors.add_argument("--pit-marker", action="store_true")
    selectors.add_argument("--path")
    args = parser.parse_args(argv)
    if not (args.pit_marker or args.path):
        parser.error("at least one selector (--pit-marker or --path) is required")

    with tempfile.TemporaryDirectory() as tmp:
        dump = collect_marker_dump(Path(tmp) / "markers.json")
    required = required_from_dump(dump, pit_marker=args.pit_marker, path=args.path)
    result = run_checks(
        required, nodes_glob=args.nodes_glob, junit_glob=args.junit_glob
    )
    result["suites"] = [
        *(["pit"] if args.pit_marker else []),
        *([args.path] if args.path else []),
    ]
    sys.stdout.write(json.dumps(result, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except EvidenceError as error:
        sys.stderr.write(f"required-suite evidence failed: {error}\n")
        raise SystemExit(1) from error
