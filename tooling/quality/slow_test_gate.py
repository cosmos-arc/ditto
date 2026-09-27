"""
Block new tests exceeding duration thresholds unless marked slow/capacity.

Durations come from shard junit XML artifacts, so no second pytest run is
needed beyond collection. Identity is class-qualified (``Class.method`` or
bare function) on BOTH sides: head and base identities come from pytest
collection — the base collected inside a temporary worktree pinned to the
immutable merge-base SHA — so inherited tests, ``__test__`` activation and
renames resolve exactly as pytest would. A legitimately slow new test
escapes via ``@pytest.mark.slow``/``@pytest.mark.capacity`` only when every
parameter case of the test carries the marker.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path

UNIT_THRESHOLD = 0.5
INTEGRATION_THRESHOLD = 5.0
_EXEMPT_MARKER_EXPR = "slow or capacity"
_DUAL_PATH_COUNT = 2
_SINGLE_PATH_COUNT = 1
_GIT = shutil.which("git") or "git"


def threshold_for(path: str) -> float:
    """Return the path-fallback duration budget for a test file by layer."""
    if "/tests/integration/" in path or "/tests/e2e/" in path:
        return INTEGRATION_THRESHOLD
    return UNIT_THRESHOLD


def layer_budget(
    file: str,
    name: str,
    unit_nodes: set[tuple[str, str]],
    integration_nodes: set[tuple[str, str]],
) -> float:
    """
    Return the budget for one identity: markers first, path fallback.

    Shared authority: a ``unit``-marked helper under ``tests/e2e`` gets the
    unit budget here and in the analyzer alike.
    """
    if (file, name) in unit_nodes:
        return UNIT_THRESHOLD
    if (file, name) in integration_nodes:
        return INTEGRATION_THRESHOLD
    return threshold_for(file)


def _bare_name(display: str) -> str:
    """Reduce a junit/collect display name to its bare final identifier."""
    segment = display.split("[", 1)[0]
    return segment.rsplit("::", 1)[-1]


def normalize_node(raw: str) -> tuple[str, str] | None:
    """
    Normalize a collected node id to (file, qualified name).

    The bracketed parameter suffix is stripped before splitting on ``::`` so
    parameter ids containing ``::`` stay inside the parameter part.
    """
    node = raw.split("[", 1)[0]
    file_part, *rest = node.split("::")
    if not file_part.endswith(".py") or not rest:
        return None
    return file_part, ".".join(rest)


def _module_path(
    classname: str, root: Path, cache: dict[str, str | None]
) -> str | None:
    """
    Resolve the longest dotted junit-classname prefix that exists as a file.

    junit classnames append the class chain after the module name
    (``pkg.tests.unit.test_x.TestSubject``), so only a prefix that exists on
    disk is the module; the remainder is the class chain.
    """
    if classname in cache:
        return cache[classname]
    parts = classname.split(".")
    resolved = None
    for index in range(len(parts), 0, -1):
        candidate = Path("/".join(parts[:index]) + ".py")
        if (root / candidate).is_file():
            resolved = str(candidate)
            break
    cache[classname] = resolved
    return resolved


def parse_junit(paths: list[Path], root: Path) -> dict[str, dict[str, float]]:
    """
    Map file path -> qualified test name -> slowest observed duration.

    The qualified name keeps the class chain from ``classname``, so a legacy
    ``TestA.test_valid`` can never lend its duration to a new
    ``TestB.test_valid``; parametrized cases of one method max-merge.
    """
    durations: dict[str, dict[str, float]] = {}
    cache: dict[str, str | None] = {}
    for path in paths:
        xml_root = ET.parse(path).getroot()  # noqa: S314 - junit 来自本仓 CI 工件
        for case in xml_root.iter("testcase"):
            classname = case.get("classname")
            name = case.get("name")
            time_attr = case.get("time")
            if not classname or not name or time_attr is None:
                continue
            try:
                seconds = float(time_attr)
            except ValueError:
                continue
            module = _module_path(classname, root, cache)
            if module is None:
                continue
            consumed = len(Path(module).with_suffix("").parts)
            classes = classname.split(".")[consumed:]
            qualname = ".".join([*classes, _bare_name(name)])
            by_name = durations.setdefault(module, {})
            by_name[qualname] = max(by_name.get(qualname, 0.0), seconds)
    return durations


def collect_ids(
    changed_files: Sequence[str] | None,
    marker_expr: str | None = None,
    *,
    cwd: Path | None = None,
) -> set[str]:
    """
    Collect raw node ids from pytest, optionally filtered by a marker.

    ``changed_files=None`` collects the configured testpaths (whole suite);
    ``cwd`` collects inside another checkout (e.g. a base worktree).
    """
    command = [
        sys.executable,
        "-m",
        "pytest",
        "--collect-only",
        "-q",
        "--import-mode=importlib",
        "-o",
        "addopts=",
        "-p",
        "no:cacheprovider",
    ]
    if marker_expr is not None:
        command += ["-m", marker_expr]
    if changed_files:
        command += list(changed_files)
    env = dict(os.environ, PYTHON_KEYRING_BACKEND="keyring.backends.null.Keyring")
    result = subprocess.run(  # noqa: S603 - venv 内固定 pytest 参数
        command, capture_output=True, text=True, check=False, env=env, cwd=cwd
    )
    # 5 = nothing collected (e.g. marker expression matches nothing)
    if result.returncode not in (0, 5):
        message = f"collect-only failed ({result.returncode})"
        raise SystemExit(f"{message}:\n{result.stdout}\n{result.stderr}")
    collected: set[str] = set()
    for raw in result.stdout.splitlines():
        line = raw.strip()
        if not line or line.startswith(("=", "!", " ")):
            continue
        if normalize_node(line) is None:
            continue
        collected.add(line)
    return collected


def _node_set(raw_ids: set[str]) -> set[tuple[str, str]]:
    """Normalize a raw collect result into (file, qualified name) pairs."""
    return {node for raw in raw_ids if (node := normalize_node(raw))}


def collect_base_ids(
    base: str, base_paths: Sequence[str], root: Path
) -> set[tuple[str, str]]:
    """
    Collect pytest identities at the base revision inside a worktree.

    Collection semantics (inheritance, ``__test__``, parametrization) resolve
    exactly as they did at base; non-test or missing paths collect nothing.
    """
    with tempfile.TemporaryDirectory() as td:
        worktree = Path(td) / "base"
        subprocess.run(  # noqa: S603 - git 固定参数
            [_GIT, "-C", str(root), "worktree", "add", "--detach", str(worktree), base],
            capture_output=True,
            text=True,
            check=True,
        )
        try:
            existing = [
                path for path in sorted(set(base_paths)) if (worktree / path).is_file()
            ]
            raw = collect_ids(existing, cwd=worktree)
        finally:
            subprocess.run(  # noqa: S603 - git 固定参数
                [_GIT, "-C", str(root), "worktree", "remove", "--force", str(worktree)],
                capture_output=True,
                check=False,
            )
    return {node for line in raw if (node := normalize_node(line)) is not None}


def find_violations(
    new_tests: Mapping[str, set[str]],
    durations: Mapping[str, Mapping[str, float]],
    exempt: set[tuple[str, str]],
    unit_nodes: set[tuple[str, str]] | None = None,
    integration_nodes: set[tuple[str, str]] | None = None,
) -> list[tuple[str, str, float, float]]:
    """Return over-threshold new tests as tuples, slowest first."""
    violations: list[tuple[str, str, float, float]] = []
    for file, names in new_tests.items():
        for name in names:
            if (file, name) in exempt:
                continue
            measured = durations.get(file, {}).get(name)
            if measured is None:
                continue
            limit = layer_budget(
                file, name, unit_nodes or set(), integration_nodes or set()
            )
            if measured > limit:
                violations.append((file, name, measured, limit))
    return sorted(violations, key=lambda item: -item[2])


def parse_name_status(raw: str) -> dict[str, str]:
    """Parse ``git diff -z --name-status -M`` into head path -> base path."""
    fields = raw.split("\0")
    mapping: dict[str, str] = {}
    index = 0
    while index < len(fields):
        status = fields[index]
        if not status:
            index += 1
            continue
        dual = status.startswith(("R", "C"))
        span = _DUAL_PATH_COUNT + 1 if dual else _SINGLE_PATH_COUNT + 1
        entries = fields[index + 1 : index + span]
        if dual and len(entries) == _DUAL_PATH_COUNT:
            mapping[entries[1]] = entries[0]
        elif not dual and len(entries) == _SINGLE_PATH_COUNT:
            mapping[entries[0]] = entries[0]
        index += span
    return mapping


def resolve_base(base: str, root: Path) -> str:
    """Pin the comparison base to the immutable merge-base SHA."""
    return subprocess.run(  # noqa: S603 - git 固定参数
        [_GIT, "-C", str(root), "merge-base", "HEAD", base],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def changed_test_files(base: str, root: Path) -> dict[str, str]:
    """Map changed test modules to their base path (rename-aware)."""
    raw = subprocess.run(  # noqa: S603 - git 固定参数
        [
            _GIT,
            "-C",
            str(root),
            "diff",
            "--name-status",
            "-z",
            "-M",
            "--diff-filter=ACMR",
            f"{base}..HEAD",
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    mapping = parse_name_status(raw)
    return {
        head: base_path
        for head, base_path in mapping.items()
        if Path(head).name.startswith("test_") and head.endswith(".py")
    }


def new_tests_at_head(
    files: Mapping[str, str],
    collected: set[tuple[str, str]],
    base_ids: set[tuple[str, str]],
) -> dict[str, set[str]]:
    """
    Map each changed test file to head identities absent at base.

    Both sides are pytest collection identities, so inherited tests,
    ``__test__`` activation and dormant definitions resolve exactly; the
    base identities are matched at each file's base (renamed) path.
    """
    result: dict[str, set[str]] = {}
    for head_path, base_path in files.items():
        base_names = {name for file, name in base_ids if file == base_path}
        names = {
            name
            for file, name in collected
            if file == head_path and name not in base_names
        }
        if names:
            result[head_path] = names
    return result


def _collect_layers(
    files: Mapping[str, str], total_by_node: Counter[tuple[str, str]]
) -> dict[str, set[tuple[str, str]]]:
    """
    Collect marker layers: exemption (slow/capacity) and budget overrides.

    A test escapes via slow/capacity only when every parameter case is marked.
    """
    marked_by_node = Counter(
        node
        for raw in collect_ids(sorted(files), _EXEMPT_MARKER_EXPR)
        if (node := normalize_node(raw))
    )
    exempt = {
        node
        for node, count in total_by_node.items()
        if marked_by_node.get(node, 0) == count
    }
    unit = _node_set(collect_ids(sorted(files), "unit"))
    integration = _node_set(collect_ids(sorted(files), "integration"))
    return {"exempt": exempt, "unit": unit, "integration": integration}


def main(argv: list[str] | None = None) -> int:
    """Run the gate; exit 0 when compliant, 1 when blocking or unevaluable."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--junit-glob", required=True, help="glob of junit XML artifacts"
    )
    parser.add_argument(
        "--base", default="origin/main", help="base ref for the new-test diff"
    )
    parser.add_argument("--root", default=".", help="repository root")
    args = parser.parse_args(argv)

    root = Path(args.root)
    base_sha = resolve_base(args.base, root)
    files = changed_test_files(base_sha, root)
    if not files:
        print("[slow-test-gate] no changed test files; pass")
        return 0

    raw_collected = collect_ids(sorted(files))
    total_by_node = Counter(
        node for raw in raw_collected if (node := normalize_node(raw))
    )
    collected = set(total_by_node)
    base_ids = collect_base_ids(base_sha, files.values(), root)
    new_tests = new_tests_at_head(files, collected, base_ids)
    if not new_tests:
        count = len(files)
        print(f"[slow-test-gate] {count} file(s) changed, no new tests; pass")
        return 0

    junit_paths = sorted(root.glob(args.junit_glob))
    if not junit_paths:
        print(f"[slow-test-gate] FAIL: no junit XML matches {args.junit_glob}")
        print("[slow-test-gate] cannot evaluate new tests without shard evidence")
        return 1

    durations = parse_junit(junit_paths, root)
    layers = _collect_layers(files, total_by_node)
    violations = find_violations(
        new_tests, durations, layers["exempt"], layers["unit"], layers["integration"]
    )

    marked_new = [
        (file, name)
        for file, names in new_tests.items()
        for name in names
        if (file, name) in layers["exempt"]
    ]
    ungated = [
        (file, name)
        for file, names in new_tests.items()
        for name in names
        if durations.get(file, {}).get(name) is None
        and (file, name) not in layers["exempt"]
    ]
    total_new = sum(len(names) for names in new_tests.values())
    evaluated = total_new - len(ungated) - len(marked_new)
    if ungated:
        count = len(ungated)
        print(
            f"[slow-test-gate] note: {count} new test(s) absent from junit; not gated"
        )
    if marked_new:
        count = len(marked_new)
        print(
            f"[slow-test-gate] note: {count} new test(s) marked slow/capacity; exempt"
        )

    if not violations:
        if evaluated:
            print(f"[slow-test-gate] {evaluated} new test(s) within thresholds; pass")
        else:
            print("[slow-test-gate] no shard junit evidence for new tests; not gated")
        return 0

    count = len(violations)
    print(f"[slow-test-gate] FAIL: {count} new test(s) exceed duration thresholds:")
    for file, name, measured, limit in violations:
        print(f"  {measured:.2f}s > {limit:.1f}s  {file}::{name}")
    print("")
    print("修复出路: 优化测试, 或为确属慢的测试打 @pytest.mark.slow /")
    print(
        "@pytest.mark.capacity 进慢车道(见 docs/engineering/testing.md 测试时长治理)."
    )
    print("存量测试不受本门限制.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
