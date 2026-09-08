"""Run isolated pytest shards and require complete evidence before coverage merging."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

_INVENTORY_FIELD_COUNT = 2


class ShardError(ValueError):
    """Shard evidence does not prove the complete current test inventory."""


def _inventory(value: object) -> list[tuple[str, bool]]:
    if not isinstance(value, list):
        raise ShardError("inventory must be a list")
    result: list[tuple[str, bool]] = []
    for item in value:
        if (
            not isinstance(item, list)
            or len(item) != _INVENTORY_FIELD_COUNT
            or not isinstance(item[0], str)
            or not isinstance(item[1], bool)
        ):
            raise ShardError("malformed test inventory entry")
        result.append((item[0], item[1]))
    return result


def partition(
    inventory: Sequence[tuple[str, bool]], index: int, count: int
) -> list[tuple[str, bool]]:
    """Distribute sorted node IDs once, including slow parametrized cases."""
    if not 0 <= index < count or not inventory:
        raise ShardError("invalid shard coordinates or empty inventory")
    names = [item[0] for item in inventory]
    if len(set(names)) != len(names):
        raise ShardError("duplicate collected test IDs")
    return sorted(inventory)[index::count]


def verify_manifests(directory: Path, commit: str, count: int) -> list[Path]:
    """Reject missing, stale, changed or incomplete shard evidence."""
    manifests = sorted(directory.glob("shard-*.json"))
    if len(manifests) != count:
        raise ShardError("missing or extra shard manifests")
    inventory: list[tuple[str, bool]] | None = None
    seen: set[int] = set()
    coverage: list[Path] = []
    for path in manifests:
        report = json.loads(path.read_text())
        index = report["index"]
        if (
            report["commit"] != commit
            or report["count"] != count
            or report["status"] != "passed"
            or index in seen
        ):
            raise ShardError("failed, duplicate or stale shard")
        current = _inventory(report["inventory"])
        if inventory is not None and current != inventory:
            raise ShardError("shards collected different test inventories")
        inventory = current
        if _inventory(report["selected"]) != partition(current, index, count):
            raise ShardError("shard selection is incomplete or overlapping")
        data = directory / f".coverage.shard-{index}"
        if (
            not data.is_file()
            or hashlib.sha256(data.read_bytes()).hexdigest()
            != report["coverage_sha256"]
        ):
            raise ShardError("missing or changed shard coverage")
        seen.add(index)
        coverage.append(data)
    if seen != set(range(count)):
        raise ShardError("shard index set is incomplete")
    return coverage


def _run(*arguments: str) -> None:
    subprocess.run([sys.executable, *arguments], check=True)  # noqa: S603 - fixed Python modules and test IDs


def run_shard(output: Path, commit: str, index: int, count: int) -> None:
    """Run parallel then serial test lanes within one isolated runner."""
    output.mkdir(parents=True, exist_ok=True)
    inventory_path = output / f"inventory-{index}.json"
    _run(
        "-m",
        "pytest",
        "-o",
        "addopts=",
        "-p",
        "tooling.quality.pytest_inventory",
        "--inventory-output",
        str(inventory_path),
        "--import-mode=importlib",
        "--collect-only",
        "-q",
        "-m",
        "not snapshot and not sandbox_live",
    )
    inventory = _inventory(json.loads(inventory_path.read_text()))
    selected = partition(inventory, index, count)
    data = output.resolve() / f".coverage.shard-{index}"
    data.unlink(missing_ok=True)
    os.environ["COVERAGE_FILE"] = str(data)
    report = {
        "commit": commit,
        "index": index,
        "count": count,
        "inventory": inventory,
        "selected": selected,
        "status": "failed",
    }
    report_path = output / f"shard-{index}.json"
    report_path.write_text(json.dumps(report) + "\n")
    executed = False
    for serial in (False, True):
        nodeids = [name for name, marked in selected if marked is serial]
        if not nodeids:
            continue
        selection = output / f"nodes-{index}-{serial}.txt"
        selection.write_text("\n".join(nodeids) + "\n")
        command = [
            "-m",
            "pytest",
            "-o",
            "addopts=",
            "--import-mode=importlib",
            "-n",
            "0" if serial else "2",
            "--dist=loadfile",
            "-q",
            "--strict-markers",
            "--strict-config",
            "--durations=25",
            "--cov",
            "--cov-report=",
            "--junitxml=" + str(output / f"junit-{index}-{serial}.xml"),
            "@" + str(selection),
        ]
        if executed:
            command.append("--cov-append")
        _run(*command)
        executed = True
    if not executed or not data.is_file():
        raise ShardError("shard produced no coverage")
    report.update(
        status="passed", coverage_sha256=hashlib.sha256(data.read_bytes()).hexdigest()
    )
    report_path.write_text(json.dumps(report) + "\n")


def main() -> int:
    """Run a shard or combine authenticated complete coverage."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("run", "combine"))
    parser.add_argument("--output", type=Path, default=Path("build/test-shards"))
    parser.add_argument("--commit", required=True)
    parser.add_argument("--count", type=int, default=4)
    parser.add_argument("--index", type=int, default=0)
    args = parser.parse_args()
    os.environ["PYTHON_KEYRING_BACKEND"] = "keyring.backends.null.Keyring"
    os.environ["_TYPER_FORCE_DISABLE_TERMINAL"] = "1"
    if args.mode == "run":
        run_shard(args.output, args.commit, args.index, args.count)
    else:
        data = verify_manifests(args.output, args.commit, args.count)
        _run("-m", "coverage", "combine", "--keep", *map(str, data))
        _run("-m", "coverage", "json", "-o", "coverage.json")
        _run("-m", "coverage", "xml", "-o", "coverage.xml")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
