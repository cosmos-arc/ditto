"""
Block new tests exceeding duration thresholds unless marked slow/capacity.

Durations come from shard junit XML artifacts, so no second pytest run is needed.
"New" means a test function present in a changed test file at HEAD but absent at
the merge base (AST name diff). Existing tests are exempt by design; a legitimately
slow new test escapes via ``@pytest.mark.slow``/``@pytest.mark.capacity``.
"""

from __future__ import annotations

import argparse
import ast
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections.abc import Mapping
from pathlib import Path

UNIT_THRESHOLD = 0.5
INTEGRATION_THRESHOLD = 5.0
_EXEMPT_MARKER_EXPR = "slow or capacity"
_GIT = shutil.which("git") or "git"


def threshold_for(path: str) -> float:
    """Return the duration budget for a test file by layer."""
    if "/tests/integration/" in path or "/tests/e2e/" in path:
        return INTEGRATION_THRESHOLD
    return UNIT_THRESHOLD


def test_names(source: str) -> set[str]:
    """Collect every ``test_*`` function or method name in a module source."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef)
        ) and node.name.startswith("test_"):
            names.add(node.name)
    return names


def new_test_names(base_source: str | None, head_source: str) -> set[str]:
    """Diff test names between base and head sources; absent base means all new."""
    return test_names(head_source) - test_names(base_source or "")


def _base_name(junit_name: str) -> str:
    """Reduce a junit display name to its bare test function name."""
    bare = junit_name.split("[", 1)[0]
    return bare.rsplit("::", 1)[-1]


def parse_junit(paths: list[Path]) -> dict[str, dict[str, float]]:
    """
    Map file path -> test name -> slowest observed duration in seconds.

    junit classnames are rootdir-relative dotted module names (e.g.
    ``tooling.quality.tests.test_x``); tests live outside ``src/`` layouts,
    so dots-to-slashes reproduces the repository path exactly.
    """
    durations: dict[str, dict[str, float]] = {}
    for path in paths:
        root = ET.parse(path).getroot()  # noqa: S314 - junit 来自本仓 CI 工件
        for case in root.iter("testcase"):
            classname = case.get("classname")
            name = case.get("name")
            time_attr = case.get("time")
            if not classname or not name or time_attr is None:
                continue
            try:
                seconds = float(time_attr)
            except ValueError:
                continue
            file_path = classname.replace(".", "/") + ".py"
            by_name = durations.setdefault(file_path, {})
            key = _base_name(name)
            by_name[key] = max(by_name.get(key, 0.0), seconds)
    return durations


def run_collect(changed_files: list[str]) -> set[tuple[str, str]]:
    """Collect (file, test name) pairs marked slow or capacity in changed files."""
    if not changed_files:
        return set()
    env = dict(os.environ, PYTHON_KEYRING_BACKEND="keyring.backends.null.Keyring")
    result = subprocess.run(  # noqa: S603 - venv 内固定 pytest 参数
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "-o",
            "addopts=",
            "-p",
            "no:cacheprovider",
            "-m",
            _EXEMPT_MARKER_EXPR,
            *changed_files,
        ],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    # 5 = nothing collected for this marker expression
    if result.returncode not in (0, 5):
        message = f"collect-only failed ({result.returncode})"
        raise SystemExit(f"{message}:\n{result.stdout}\n{result.stderr}")
    exempt: set[tuple[str, str]] = set()
    for raw in result.stdout.splitlines():
        line = raw.strip()
        if "::" not in line or line.startswith(("=", "!", " ")):
            continue
        file_part, *rest = line.split("::")
        if not file_part.endswith(".py") or not rest:
            continue
        exempt.add((file_part, _base_name(rest[-1])))
    return exempt


def find_violations(
    new_tests: Mapping[str, set[str]],
    durations: Mapping[str, Mapping[str, float]],
    exempt: set[tuple[str, str]],
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
            limit = threshold_for(file)
            if measured > limit:
                violations.append((file, name, measured, limit))
    return sorted(violations, key=lambda item: -item[2])


def changed_test_files(base: str, root: Path) -> list[str]:
    """List added/changed/renamed test modules between base and HEAD."""
    merge_base = subprocess.run(  # noqa: S603 - git 固定参数
        [_GIT, "-C", str(root), "merge-base", "HEAD", base],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    diff = subprocess.run(  # noqa: S603 - git 固定参数
        [
            _GIT,
            "-C",
            str(root),
            "diff",
            "--name-only",
            "--diff-filter=ACMR",
            f"{merge_base}..HEAD",
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return sorted(
        line
        for line in diff.splitlines()
        if Path(line).name.startswith("test_") and line.endswith(".py")
    )


def new_tests_at_head(base: str, files: list[str], root: Path) -> dict[str, set[str]]:
    """Map each changed test file to its test names that do not exist at base."""
    result: dict[str, set[str]] = {}
    for file in files:
        base_source = (
            subprocess.run(  # noqa: S603 - git 固定参数
                [_GIT, "-C", str(root), "show", f"{base}:{file}"],
                capture_output=True,
                text=True,
                check=False,
            ).stdout
            or None
        )
        head_source = (root / file).read_text(encoding="utf-8")
        names = new_test_names(base_source, head_source)
        if names:
            result[file] = names
    return result


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
    files = changed_test_files(args.base, root)
    if not files:
        print("[slow-test-gate] no changed test files; pass")
        return 0

    new_tests = new_tests_at_head(args.base, files, root)
    if not new_tests:
        count = len(files)
        print(f"[slow-test-gate] {count} file(s) changed, no new tests; pass")
        return 0

    junit_paths = sorted(root.glob(args.junit_glob))
    if not junit_paths:
        print(f"[slow-test-gate] FAIL: no junit XML matches {args.junit_glob}")
        print("[slow-test-gate] cannot evaluate new tests without shard evidence")
        return 1

    durations = parse_junit(junit_paths)
    exempt = run_collect(files)
    violations = find_violations(new_tests, durations, exempt)

    total_new = sum(len(names) for names in new_tests.values())
    ungated = [
        (file, name)
        for file, names in new_tests.items()
        for name in names
        if durations.get(file, {}).get(name) is None and (file, name) not in exempt
    ]
    evaluated = total_new - len(ungated)
    if ungated:
        count = len(ungated)
        print(
            f"[slow-test-gate] note: {count} new test(s) absent from junit; not gated"
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
