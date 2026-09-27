"""
Block new tests exceeding duration thresholds unless marked slow/capacity.

Durations come from shard junit XML artifacts, so no second pytest run is
needed. Identity is class-qualified (``Class.method`` or bare function) and
rename-aware: head identities come from pytest collection (so inherited
tests are seen), the base set from lexical AST of the original path, and
junit keys from the classname class chain. A legitimately slow new test
escapes via ``@pytest.mark.slow``/``@pytest.mark.capacity``.
"""

from __future__ import annotations

import argparse
import ast
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

UNIT_THRESHOLD = 0.5
INTEGRATION_THRESHOLD = 5.0
_EXEMPT_MARKER_EXPR = "slow or capacity"
_DUAL_PATH_COUNT = 2
_SINGLE_PATH_COUNT = 1
_GIT = shutil.which("git") or "git"


def threshold_for(path: str) -> float:
    """Return the duration budget for a test file by layer."""
    if "/tests/integration/" in path or "/tests/e2e/" in path:
        return INTEGRATION_THRESHOLD
    return UNIT_THRESHOLD


class _TestCollector(ast.NodeVisitor):
    """Collect class-qualified test names (``Class.method`` or bare ``name``)."""

    def __init__(self) -> None:
        self.names: set[str] = set()
        self._classes: list[str] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._classes.append(node.name)
        self.generic_visit(node)
        self._classes.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._record(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._record(node)

    def _record(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        if node.name.startswith("test_"):
            self.names.add(".".join([*self._classes, node.name]))


def test_names(source: str) -> set[str]:
    """Collect class-qualified ``test_*`` names from module source."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    collector = _TestCollector()
    collector.visit(tree)
    return collector.names


def new_test_names(base_source: str | None, head_source: str) -> set[str]:
    """Diff qualified names between base and head; absent base means all new."""
    return test_names(head_source) - test_names(base_source or "")


def _bare_name(display: str) -> str:
    """Reduce a junit/collect display name to its bare final identifier."""
    segment = display.split("[", 1)[0]
    return segment.rsplit("::", 1)[-1]


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
    changed_files: Sequence[str], marker_expr: str | None = None
) -> set[tuple[str, str]]:
    """Collect (file, qualified name) pairs from pytest, optionally filtered."""
    if not changed_files:
        return set()
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
    env = dict(os.environ, PYTHON_KEYRING_BACKEND="keyring.backends.null.Keyring")
    result = subprocess.run(  # noqa: S603 - venv 内固定 pytest 参数
        [*command, *changed_files], capture_output=True, text=True, check=False, env=env
    )
    # 5 = nothing collected (e.g. marker expression matches nothing)
    if result.returncode not in (0, 5):
        message = f"collect-only failed ({result.returncode})"
        raise SystemExit(f"{message}:\n{result.stdout}\n{result.stderr}")
    collected: set[tuple[str, str]] = set()
    for raw in result.stdout.splitlines():
        line = raw.strip()
        if "::" not in line or line.startswith(("=", "!", " ")):
            continue
        file_part, *rest = line.split("::")
        if not file_part.endswith(".py") or not rest:
            continue
        collected.add((file_part, ".".join(_bare_name(segment) for segment in rest)))
    return collected


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


def changed_test_files(base: str, root: Path) -> dict[str, str]:
    """Map changed test modules to their base path (rename-aware)."""
    merge_base = subprocess.run(  # noqa: S603 - git 固定参数
        [_GIT, "-C", str(root), "merge-base", "HEAD", base],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
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
            f"{merge_base}..HEAD",
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


def _git_show(base: str, path: str, root: Path) -> str | None:
    """Return the base revision content of a path, or None when absent."""
    return (
        subprocess.run(  # noqa: S603 - git 固定参数
            [_GIT, "-C", str(root), "show", f"{base}:{path}"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout
        or None
    )


def new_tests_at_head(
    base: str,
    files: Mapping[str, str],
    collected: set[tuple[str, str]],
    root: Path,
    show: Callable[[str, str, Path], str | None] = _git_show,
) -> dict[str, set[str]]:
    """
    Map each changed test file to collected identities absent at base.

    Head identities come from pytest collection (inherited tests included);
    the base set is the lexical AST of the original path, and only when that
    path was itself a test module — a rename from a non-test helper counts
    as fully new. Base under-counts inherited identities, so the diff can
    only over-block, never miss.
    """
    result: dict[str, set[str]] = {}
    for head_path, base_path in files.items():
        base_source: str | None = None
        if Path(base_path).name.startswith("test_") and base_path.endswith(".py"):
            base_source = show(base, base_path, root)
        base_names = test_names(base_source or "")
        names = {
            qualname for file, qualname in collected if file == head_path
        } - base_names
        if names:
            result[head_path] = names
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

    collected = collect_ids(sorted(files))
    new_tests = new_tests_at_head(args.base, files, collected, root)
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
    exempt = collect_ids(sorted(files), _EXEMPT_MARKER_EXPR)
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
