"""
Block new tests exceeding duration thresholds unless marked slow/capacity.

Durations come from shard junit XML artifacts. Identity is case-level —
``Class.method[param]`` or a bare function — on both sides: head and base
identities come from pytest collection, the base collected inside a
temporary worktree pinned to the immutable merge-base SHA, so inherited
tests, ``__test__`` activation, renames and newly added parameter cases
resolve exactly as pytest would. Exemptions and marker budgets apply at
function level and only when every collected case carries the marker; a
new, non-exempt case with no junit evidence under the managed test paths
fails closed. A legitimately slow new test escapes via
``@pytest.mark.slow``/``@pytest.mark.capacity``.
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
_MIN_PACKAGE_PATH_SLASHES = 2
_MANAGED_TEST_PREFIXES = ("packages/", "apps/")


def threshold_for(path: str) -> float:
    """Return the path-fallback duration budget for a test file by layer."""
    if "/tests/integration/" in path or "/tests/e2e/" in path:
        return INTEGRATION_THRESHOLD
    return UNIT_THRESHOLD


def function_of(case: str) -> str:
    """Reduce a case identity to its function identity."""
    return case.split("[", 1)[0]


def layer_budget(
    file: str,
    case: str,
    unit_functions: set[str],
    integration_functions: set[str],
) -> float:
    """
    Return the budget for one case: function-level markers first.

    ``unit_functions``/``integration_functions`` hold bare function names for
    THIS file whose every collected case carries the marker; markers beat
    the path fallback so a ``unit``-marked helper under ``tests/e2e`` gets
    the unit budget here and in the analyzer alike.
    """
    name = function_of(case)
    if name in unit_functions:
        return UNIT_THRESHOLD
    if name in integration_functions:
        return INTEGRATION_THRESHOLD
    return threshold_for(file)


def normalize_case(raw: str) -> tuple[str, str] | None:
    """
    Normalize a collected node id to (file, case identity).

    The bracketed parameter suffix is set aside before splitting on ``::``
    so parameter ids containing ``::`` stay inside the parameter part, then
    re-attached to the case identity.
    """
    head, _, param = raw.partition("[")
    file_part, *rest = head.split("::")
    if not file_part.endswith(".py") or not rest:
        return None
    case = ".".join(rest) + (f"[{param}" if param else "")
    return file_part, case


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
    Map file path -> case identity -> observed duration in seconds.

    Case identities keep the class chain and the parameter id, so a legacy
    ``TestA.test_valid`` can never lend its duration to a new
    ``TestB.test_valid`` and per-case durations stay attributable.
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
            if case.find("skipped") is not None:
                # 未执行的用例不构成时长证据（fail closed：托管路径缺证据即拦）
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
            case_id = ".".join([*classes, name])
            by_case = durations.setdefault(module, {})
            by_case[case_id] = max(by_case.get(case_id, 0.0), seconds)
    return durations


_COLLECT_TIMEOUT_SECONDS = 120


def collect_ids(
    changed_files: Sequence[str] | None,
    marker_expr: str | None = None,
    *,
    cwd: Path | None = None,
    tolerate_collection_errors: bool = False,
    extra_env: Mapping[str, str] | None = None,
) -> set[str]:
    """
    Collect raw node ids from pytest, optionally filtered by a marker.

    ``changed_files=None`` collects the configured testpaths (whole suite);
    ``cwd`` collects inside another checkout (e.g. a base worktree);
    ``tolerate_collection_errors`` keeps partial identities when collection
    of some files fails (dependency migrations collect old code in the HEAD
    environment) — the resulting under-count can only over-block.
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
    if tolerate_collection_errors:
        command.append("--continue-on-collection-errors")
    if changed_files:
        command += list(changed_files)
    env = dict(
        os.environ,
        PYTHON_KEYRING_BACKEND="keyring.backends.null.Keyring",
        **(extra_env or {}),
    )
    try:
        result = subprocess.run(  # noqa: S603 - venv 内固定 pytest 参数
            command,
            capture_output=True,
            text=True,
            check=False,
            env=env,
            cwd=cwd,
            timeout=_COLLECT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as error:
        message = f"collect-only timed out after {_COLLECT_TIMEOUT_SECONDS}s"
        raise SystemExit(message) from error
    # pytest 9 exits 1 (execution short-circuited) or 2 (internal) for
    # collection errors under --continue-on-collection-errors; 5 = nothing
    # collected. Tolerated mode accepts the partial identities.
    accepted = (0, 1, 2, 5) if tolerate_collection_errors else (0, 5)
    if result.returncode not in accepted:
        message = f"collect-only failed ({result.returncode})"
        raise SystemExit(f"{message}:\n{result.stdout}\n{result.stderr}")
    collected: set[str] = set()
    for raw in result.stdout.splitlines():
        line = raw.strip()
        if not line or line.startswith(("=", "!", " ")):
            continue
        if normalize_case(line) is None:
            continue
        collected.add(line)
    return collected


def collect_base_ids(
    base: str, base_paths: Sequence[str] | None, root: Path
) -> set[tuple[str, str]]:
    """
    Collect pytest case identities at the base revision inside a worktree.

    Collection semantics (inheritance, ``__test__``, parametrization) resolve
    exactly as they did at base. Only paths that were themselves test
    modules or whole ``tests`` directories (owner scope) are collected —
    an explicitly passed file collects its ``test_*`` functions regardless
    of its name, which would wrongly shelter tests activated by a rename
    away from a non-test helper.
    """
    collectable = [
        path
        for path in sorted(set(base_paths or []))
        if (
            path.endswith("/tests")
            or (Path(path).name.startswith("test_") and path.endswith(".py"))
        )
        and "/" in path
    ]
    if base_paths is None:
        collectable = []
    if not collectable and base_paths is not None:
        return set()
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
                path
                for path in collectable
                if (worktree / path).is_file() or (worktree / path).is_dir()
            ]
            if not existing and base_paths is not None:
                return set()
            # editable 安装会把 import 劫持到 HEAD 检出——PYTHONPATH 前插
            # worktree 的 src 目录，基线收集解析到基线源码（含参数化定义）。
            src_dirs = [
                *sorted(worktree.glob("packages/*/src")),
                worktree / "apps/backend/src",
            ]
            prepend = os.pathsep.join(str(p) for p in src_dirs)
            existing_path = os.environ.get("PYTHONPATH", "")
            combined = prepend + (os.pathsep + existing_path if existing_path else "")
            raw = collect_ids(
                existing,
                cwd=worktree,
                tolerate_collection_errors=True,
                extra_env={"PYTHONPATH": combined},
            )
        finally:
            subprocess.run(  # noqa: S603 - git 固定参数
                [_GIT, "-C", str(root), "worktree", "remove", "--force", str(worktree)],
                capture_output=True,
                check=False,
            )
    return {case for line in raw if (case := normalize_case(line)) is not None}


def find_violations(
    new_cases: Mapping[str, set[str]],
    durations: Mapping[str, Mapping[str, float]],
    exempt_functions: set[tuple[str, str]],
    unit_functions_by_file: Mapping[str, set[str]] | None = None,
    integration_functions_by_file: Mapping[str, set[str]] | None = None,
) -> list[tuple[str, str, float, float]]:
    """Return over-threshold new cases as tuples, slowest first."""
    violations: list[tuple[str, str, float, float]] = []
    unit_by_file = unit_functions_by_file or {}
    integration_by_file = integration_functions_by_file or {}
    for file, cases in new_cases.items():
        for case in cases:
            if (file, function_of(case)) in exempt_functions:
                continue
            measured = durations.get(file, {}).get(case)
            if measured is None:
                measured = durations.get(file, {}).get(function_of(case))
            if measured is None:
                continue
            limit = layer_budget(
                file,
                case,
                unit_by_file.get(file, set()),
                integration_by_file.get(file, set()),
            )
            if measured > limit:
                violations.append((file, case, measured, limit))
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


def _owner_of(path: str) -> str | None:
    """Backend owner of a path (``packages/<pkg>`` or ``apps/backend``)."""
    if path.startswith("packages/") and path.count("/") >= _MIN_PACKAGE_PATH_SLASHES:
        return "/".join(path.split("/")[:2])
    if path.startswith("apps/backend"):
        return "apps/backend"
    return None


def gate_scope(name_status: Mapping[str, str]) -> dict[str, str] | None:
    """
    Gate scope for the head-vs-base collection diff; None = whole suite.

    Changed test files and conftests bring their owner's whole ``tests``
    directory into the diff; any change outside a tests directory (i.e.
    production code) can parametrize tests in ANY package — such changes
    diff the entire collected suite so cross-package generated cases
    (e.g. a strategy seed spec consumed by application tests) are seen.
    """
    scope: dict[str, str] = {}
    owners: set[str] = set()
    for head, base_path in name_status.items():
        if "/tests/" not in head and not head.endswith("/tests"):
            return None
        owner = _owner_of(head)
        if owner is not None:
            owners.add(owner)
        if Path(head).name.startswith("test_") and head.endswith(".py"):
            scope[head] = base_path
    for owner in sorted(owners):
        scope.setdefault(f"{owner}/tests", f"{owner}/tests")
    return scope


def changed_test_files(
    base: str, root: Path
) -> tuple[dict[str, str] | None, dict[str, str]]:
    """
    Gate scope and test-module renames for the head-vs-base diff.

    Deletions count: removing a conftest that suppressed collection exposes
    cases at HEAD. Renames of test modules are returned separately so the
    whole-suite mode can still subtract legacy identities at the old path.
    """
    raw = subprocess.run(  # noqa: S603 - git 固定参数
        [
            _GIT,
            "-C",
            str(root),
            "diff",
            "--name-status",
            "-z",
            "-M",
            "--diff-filter=ACMRD",
            f"{base}..HEAD",
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    mapping = parse_name_status(raw)
    renames = {
        head: base_path
        for head, base_path in mapping.items()
        if head != base_path
        and Path(head).name.startswith("test_")
        and head.endswith(".py")
    }
    return gate_scope(mapping), renames


def new_tests_at_head(
    files: Mapping[str, str],
    collected_cases: set[tuple[str, str]],
    base_cases: set[tuple[str, str]],
) -> dict[str, set[str]]:
    """
    Map each changed test file to head cases absent at base.

    Both sides are pytest collection case identities, so inherited tests,
    ``__test__`` activation, dormant definitions and newly added parameter
    cases resolve exactly; base identities are matched at each file's base
    (renamed) path.
    """

    def _matches(path: str, scope_path: str) -> bool:
        if path == scope_path:
            return True
        return scope_path.endswith("/tests") and path.startswith(scope_path + "/")

    # 结果按收集产出的具体文件路径键控（junit/标记/托管路径判定均用具体路径）；
    # 目录范围条目的基线侧同样按前缀聚合到具体基线文件。
    result: dict[str, set[str]] = {}
    for file, case in collected_cases:
        entry = next(((hp, bp) for hp, bp in files.items() if _matches(file, hp)), None)
        if entry is None:
            continue  # 范围外（scoped 模式）的收集用例不参与差集
        _, base_path = entry
        # 目录范围条目是恒等映射：基线侧只与同路径的具体文件比对，
        # 其他基线模块的同名用例不得为新用例提供庇护。
        candidate_files = {file} if base_path.endswith("/tests") else {base_path}
        base_names = {
            base_case
            for base_file, base_case in base_cases
            if base_file in candidate_files
        }
        if case in base_names:
            continue
        result.setdefault(file, set()).add(case)
    return result


def _case_set(raw_ids: set[str]) -> set[tuple[str, str]]:
    """Normalize a raw collect result into (file, case) pairs."""
    return {case for raw in raw_ids if (case := normalize_case(raw)) is not None}


def all_marked_functions(
    raw_total: set[str], raw_marked: set[str]
) -> set[tuple[str, str]]:
    """Function identities whose every collected case carries the marker."""
    total_by_function: Counter[tuple[str, str]] = Counter()
    marked_by_function: Counter[tuple[str, str]] = Counter()
    for file, case in _case_set(raw_total):
        total_by_function[(file, function_of(case))] += 1
    for file, case in _case_set(raw_marked):
        marked_by_function[(file, function_of(case))] += 1
    return {
        function
        for function, count in total_by_function.items()
        if marked_by_function.get(function, 0) == count
    }


def _is_managed_test_path(path: str) -> bool:
    """Whether the shard lanes owe junit evidence for this path."""
    return path.startswith(_MANAGED_TEST_PREFIXES) and "/tests/" in path


def _report_outcome(
    new_cases: Mapping[str, set[str]],
    durations: Mapping[str, Mapping[str, float]],
    exempt_functions: set[tuple[str, str]],
    violations: list[tuple[str, str, float, float]],
) -> int:
    """Print the gate outcome and return the exit code (fail closed)."""
    marked_new = [
        (file, case)
        for file, cases in new_cases.items()
        for case in cases
        if (file, function_of(case)) in exempt_functions
    ]
    unmeasured = [
        (file, case)
        for file, cases in new_cases.items()
        for case in cases
        if durations.get(file, {}).get(case) is None
        and durations.get(file, {}).get(function_of(case)) is None
        and (file, function_of(case)) not in exempt_functions
    ]
    hard_unmeasured = [item for item in unmeasured if _is_managed_test_path(item[0])]
    blind_unmeasured = [
        item for item in unmeasured if not _is_managed_test_path(item[0])
    ]
    total_new = sum(len(cases) for cases in new_cases.values())
    if marked_new:
        count = len(marked_new)
        print(
            f"[slow-test-gate] note: {count} new case(s) marked slow/capacity; exempt"
        )
    if blind_unmeasured:
        count = len(blind_unmeasured)
        print(
            f"[slow-test-gate] note: {count} new case(s) outside managed test paths;"
            " no junit evidence by design; not gated"
        )
    if hard_unmeasured:
        count = len(hard_unmeasured)
        print(
            f"[slow-test-gate] FAIL: {count} new case(s) have no junit evidence"
            " from the shard lanes:"
        )
        for file, case in sorted(hard_unmeasured):
            print(f"  {file}::{case}")
        print("分片车道未提供时长证据即视为未验证(fail closed).")
        return 1

    evaluated = total_new - len(marked_new) - len(unmeasured)
    if not violations:
        if evaluated:
            print(f"[slow-test-gate] {evaluated} new case(s) within thresholds; pass")
        else:
            print("[slow-test-gate] no shard junit evidence for new tests; not gated")
        return 0

    count = len(violations)
    print(f"[slow-test-gate] FAIL: {count} new case(s) exceed duration thresholds:")
    for file, case, measured, limit in violations:
        print(f"  {measured:.2f}s > {limit:.1f}s  {file}::{case}")
    print("")
    print("修复出路: 优化测试, 或为确属慢的测试打 @pytest.mark.slow /")
    print(
        "@pytest.mark.capacity 进慢车道(见 docs/engineering/testing.md 测试时长治理)."
    )
    print("存量测试不受本门限制.")
    return 1


def main(argv: list[str] | None = None) -> int:
    """Run the gate; exit 0 when compliant, 1 when blocking or unevaluable."""
    parser = argparse.ArgumentParser(
        description=__doc__,
    )
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
    scope, renames = changed_test_files(base_sha, root)
    files = scope
    if files is not None and not files:
        print("[slow-test-gate] no changed test files or touched owners; pass")
        return 0

    if files is None:
        raw_collected = collect_ids(None)
        collected_cases = _case_set(raw_collected)
        base_cases = collect_base_ids(base_sha, None, root)
        files = {file: renames.get(file, file) for file, _ in collected_cases}
    else:
        raw_collected = collect_ids(sorted(files))
        collected_cases = _case_set(raw_collected)
        base_cases = collect_base_ids(base_sha, files.values(), root)
    new_cases = new_tests_at_head(files, collected_cases, base_cases)
    if not new_cases:
        count = len(files)
        print(f"[slow-test-gate] {count} file(s) changed, no new tests; pass")
        return 0

    junit_paths = sorted(root.glob(args.junit_glob))
    if not junit_paths:
        print(f"[slow-test-gate] FAIL: no junit XML matches {args.junit_glob}")
        print("[slow-test-gate] cannot evaluate new tests without shard evidence")
        return 1

    durations = parse_junit(junit_paths, root)
    raw_slow_marked = collect_ids(sorted(files), _EXEMPT_MARKER_EXPR)
    exempt_functions = all_marked_functions(raw_collected, raw_slow_marked)
    unit_functions = all_marked_functions(
        raw_collected, collect_ids(sorted(files), "unit")
    )
    integration_functions = all_marked_functions(
        raw_collected, collect_ids(sorted(files), "integration")
    )
    unit_by_file: dict[str, set[str]] = {}
    integration_by_file: dict[str, set[str]] = {}
    for file, name in unit_functions:
        unit_by_file.setdefault(file, set()).add(name)
    for file, name in integration_functions:
        integration_by_file.setdefault(file, set()).add(name)
    violations = find_violations(
        new_cases,
        durations,
        exempt_functions,
        unit_by_file,
        integration_by_file,
    )

    return _report_outcome(new_cases, durations, exempt_functions, violations)


if __name__ == "__main__":
    raise SystemExit(main())
