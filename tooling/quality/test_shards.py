"""Run isolated pytest shards and require complete evidence before coverage merging."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from collections.abc import Mapping, Sequence
from functools import lru_cache
from pathlib import Path

from tooling.quality.slow_test_gate import parse_junit

_INVENTORY_FIELD_COUNT = 2
# 未入清单文件的单例保守计权，锚定实测 p95≈0.43s（#326）：新文件按
# 0.4s×用例数估重，宁可高估也不让未知重组件打破均衡。
_DEFAULT_TEST_SECONDS = 0.4
_DURATION_MANIFEST = Path(__file__).with_name("shard_durations.json")


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


def _read_duration_manifest(path: Path) -> dict[str, float]:
    """Parse a duration manifest; missing file yields an empty mapping."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    if not isinstance(raw, dict):
        raise ShardError("duration manifest must be an object") from None
    result: dict[str, float] = {}
    for name, seconds in raw.items():
        if not isinstance(name, str) or not isinstance(seconds, int | float):
            raise ShardError("duration manifest has a malformed entry")
        result[name] = float(seconds)
    return result


@lru_cache(maxsize=1)
def _known_file_durations() -> dict[str, float]:
    """
    Load the checked-in per-file duration manifest (#326).

    Missing file（新增/改名）走默认估重，缺失或过期清单只影响均衡精度，
    不影响分配的确定性与完回性。
    """
    return _read_duration_manifest(_DURATION_MANIFEST)


def _file_groups(
    inventory: Sequence[tuple[str, bool]],
) -> dict[str, list[tuple[str, bool]]]:
    """Group inventory records by test file（nodeid 的 :: 前缀）——fixture 亲和单元."""
    groups: dict[str, list[tuple[str, bool]]] = {}
    for record in inventory:
        groups.setdefault(record[0].split("::", 1)[0], []).append(record)
    return groups


def _file_weights(
    groups: Mapping[str, list[tuple[str, bool]]],
    durations: Mapping[str, float],
) -> dict[str, float]:
    """Per-file weight:清单实测和优先，缺省文件按默认单例×用例数估重."""
    weights: dict[str, float] = {}
    for name, records in groups.items():
        known = durations.get(name)
        weights[name] = (
            float(known) if known is not None else _DEFAULT_TEST_SECONDS * len(records)
        )
    return weights


def _split_units(
    groups: Mapping[str, list[tuple[str, bool]]],
    weights: Mapping[str, float],
    count: int,
) -> dict[str, list[tuple[str, bool]]]:
    """
    把超过单片预算 60% 的巨文件按有序 nodeid 轮询拆成 count 个单元（#326）.

    文件亲和是均衡优化不是硬约束：单文件重量超过理想均值六成时，
    不拆会把均衡下限钉死（实测 852s 巨文件钉出 2.16x）。拆分单元
    按有序 nodeid 轮询，确定性完整；普通文件仍整文件分配。
    """
    total = sum(weights.values())
    budget = (total / count) * 0.6 if total > 0 else 0.0
    units: dict[str, list[tuple[str, bool]]] = {}
    for name, records in groups.items():
        if weights[name] > budget and len(records) > 1:
            targets = min(count, len(records))
            ordered = sorted(records)
            for shard in range(targets):
                units[f"{name}#split{shard}"] = ordered[shard::targets]
        else:
            units[name] = records
    return units


def _assign_files(
    groups: Mapping[str, list[tuple[str, bool]]],
    weights: Mapping[str, float],
    count: int,
) -> list[list[tuple[str, bool]]]:
    """
    LPT 装箱：单元按时长降序（同权按路径字典序）放入当前最轻的片.

    负载并列取最小片序号——纯函数，同输入同输出（#326 确定性要求）。
    """
    units = _split_units(groups, weights, count)
    unit_weights = {
        unit: (
            weights[origin] * len(records) / len(groups[origin])
            if "#split" in unit
            else weights[unit]
        )
        for unit, records in units.items()
        for origin in [unit.rsplit("#split", 1)[0]]
    }
    order = sorted(units, key=lambda name: (-unit_weights[name], name))
    loads = [0.0] * count
    buckets: list[list[tuple[str, bool]]] = [[] for _ in range(count)]
    for name in order:
        target = min(range(count), key=lambda shard: (loads[shard], shard))
        loads[target] += unit_weights[name]
        buckets[target].extend(units[name])
    return buckets


def partition(
    inventory: Sequence[tuple[str, bool]],
    index: int,
    count: int,
    durations: Mapping[str, float] | None = None,
) -> list[tuple[str, bool]]:
    """
    Distribute every nodeid exactly once, balanced by file duration (#326).

    文件为分配单元（fixture 亲和：同文件用例不跨片）；时长来自传入映射
    或仓库内清单，缺失/过期只降均衡精度，分配始终确定且完整。
    """
    if not 0 <= index < count or not inventory:
        raise ShardError("invalid shard coordinates or empty inventory")
    names = [item[0] for item in inventory]
    if len(set(names)) != len(names):
        raise ShardError("duplicate collected test IDs")
    known = durations if durations is not None else _known_file_durations()
    groups = _file_groups(inventory)
    buckets = _assign_files(groups, _file_weights(groups, known), count)
    return sorted(buckets[index])


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
        seen.add(index)
        if report["selected"] == []:
            # 合法空片（文件数少于片数时 LPT 尾片为空）：无执行即无 coverage
            continue
        data = directory / f".coverage.shard-{index}"
        if (
            not data.is_file()
            or hashlib.sha256(data.read_bytes()).hexdigest()
            != report["coverage_sha256"]
        ):
            raise ShardError("missing or changed shard coverage")
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
        "not snapshot and not sandbox_live and not capacity",
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
        files = output / f"files-{index}-{serial}.txt"
        files.write_text(
            "\n".join(sorted({name.split("::", 1)[0] for name in nodeids})) + "\n"
        )
        command = [
            "-m",
            "pytest",
            "-o",
            "addopts=",
            "--import-mode=importlib",
            "-n",
            "0" if serial else "4",
            "--dist=loadfile",
            "-q",
            "--strict-markers",
            "--strict-config",
            "--durations=25",
            "--cov",
            "--cov-report=",
            "--junitxml=" + str(output / f"junit-{index}-{serial}.xml"),
            "-p",
            "tooling.quality.pytest_inventory",
            "--selection-input",
            str(selection),
            "@" + str(files),
        ]
        if executed:
            command.append("--cov-append")
        _run(*command)
        executed = True
    if not selected:
        # 合法空片：清掉复用输出目录里上一轮的陈旧车道产物（nodes/files/
        # junit 残留会误导产物侧证据核验），验证侧按空选择跳过数据要求
        for stale in output.glob(f"nodes-{index}-*.txt"):
            stale.unlink()
        for stale in output.glob(f"files-{index}-*.txt"):
            stale.unlink()
        for stale in output.glob(f"junit-{index}-*.xml"):
            stale.unlink()
        report.update(status="passed")
        report_path.write_text(json.dumps(report) + "\n")
        return
    if not executed or not data.is_file():
        raise ShardError("shard produced no coverage")
    report.update(
        status="passed", coverage_sha256=hashlib.sha256(data.read_bytes()).hexdigest()
    )
    report_path.write_text(json.dumps(report) + "\n")


def _verify_capacity(directory: Path, commit: str) -> list[Path]:
    """Require the capacity slow-lane evidence when shard evidence is present."""
    report_path = directory / "capacity.json"
    if not report_path.is_file():
        raise ShardError("missing capacity slow-lane evidence")
    report = json.loads(report_path.read_text())
    data = directory / ".coverage.capacity"
    if (
        report["commit"] != commit
        or report["status"] != "passed"
        or not data.is_file()
        or hashlib.sha256(data.read_bytes()).hexdigest() != report["coverage_sha256"]
    ):
        raise ShardError("capacity slow-lane evidence is stale or changed")
    return [data]


def run_capacity(output: Path, commit: str) -> None:
    """Run the scheduler-capacity slow lane serially with coverage evidence."""
    output.mkdir(parents=True, exist_ok=True)
    data = output.resolve() / ".coverage.capacity"
    data.unlink(missing_ok=True)
    os.environ["COVERAGE_FILE"] = str(data)
    report = {"commit": commit, "status": "failed"}
    report_path = output / "capacity.json"
    report_path.write_text(json.dumps(report) + "\n")
    _run(
        "-m",
        "pytest",
        "-o",
        "addopts=",
        "--import-mode=importlib",
        "-n",
        "0",
        "-q",
        "--strict-markers",
        "--strict-config",
        "--durations=25",
        "-m",
        "capacity",
        "--cov",
        "--cov-report=",
        "--junitxml=" + str(output / "junit-capacity.xml"),
    )
    if not data.is_file():
        raise ShardError("capacity lane produced no coverage")
    report.update(
        status="passed", coverage_sha256=hashlib.sha256(data.read_bytes()).hexdigest()
    )
    report_path.write_text(json.dumps(report) + "\n")


def _glob_junit(pattern: str) -> list[Path]:
    """Glob junit paths with the base anchored at the first wildcard-free prefix."""
    parts = Path(pattern).parts
    base: list[str] = []
    rest: list[str] = []
    for part in parts:
        if rest or any(ch in part for ch in "*?["):
            rest.append(part)
        else:
            base.append(part)
    if not rest:
        return [Path(pattern)]
    root = Path(*base) if base else Path.cwd()
    return sorted(root.glob(str(Path(*rest))))


def refresh_durations(
    junit_globs: Sequence[str], manifest: Path, *, root: Path | None = None
) -> dict[str, float]:
    """
    Merge per-file totals from junit evidence into the duration manifest (#326).

    复用 slow_test_gate 的 junit 解析（module 定位权威实现）；批内同
    用例多次观测取最大（parse_junit 既有语义），**本批出现的文件替换
    旧值**——优化变快或瞬时离群后清单能回落；未在本批出现的文件保留
    旧值。清单只是均衡权重：缺失/过期仅降精度，不影响分配确定性与完
    固性。
    """
    merged = _read_duration_manifest(manifest)
    for pattern in junit_globs:
        paths = _glob_junit(pattern)
        if not paths:
            raise ShardError(f"no junit evidence matches {pattern}")
        for module, cases in parse_junit(paths, root or Path.cwd()).items():
            merged[module] = sum(cases.values())
    payload = {name: round(seconds, 3) for name, seconds in sorted(merged.items())}
    manifest.write_text(json.dumps(payload, indent=0, separators=(",", ":")) + "\n")
    return payload


def main() -> int:
    """Run a shard or combine authenticated complete coverage."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode", choices=("run", "combine", "capacity", "refresh-durations")
    )
    parser.add_argument("--output", type=Path, default=Path("build/test-shards"))
    parser.add_argument("--commit")
    parser.add_argument("--count", type=int, default=4)
    parser.add_argument("--index", type=int, default=0)
    parser.add_argument("--junit-glob", action="append", default=[])
    parser.add_argument("--manifest", type=Path, default=_DURATION_MANIFEST)
    args = parser.parse_args()
    os.environ["PYTHON_KEYRING_BACKEND"] = "keyring.backends.null.Keyring"
    os.environ["_TYPER_FORCE_DISABLE_TERMINAL"] = "1"
    if args.mode == "refresh-durations":
        if not args.junit_glob:
            parser.error("refresh-durations requires at least one --junit-glob")
        refresh_durations(args.junit_glob, args.manifest)
    else:
        if not args.commit:
            parser.error(f"{args.mode} requires --commit")
        if args.mode == "run":
            run_shard(args.output, args.commit, args.index, args.count)
        elif args.mode == "capacity":
            run_capacity(args.output, args.commit)
        else:
            data = verify_manifests(args.output, args.commit, args.count)
            data += _verify_capacity(args.output, args.commit)
            _run("-m", "coverage", "combine", "--keep", *map(str, data))
            _run("-m", "coverage", "json", "-o", "coverage.json")
            _run("-m", "coverage", "xml", "-o", "coverage.xml")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
