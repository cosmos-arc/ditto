"""Prove the new-test duration gate classifies, exempts, and exits as specified."""

from pathlib import Path

import pytest

from tooling.quality import slow_test_gate as gate


def test_threshold_follows_test_layer() -> None:
    assert (
        gate.threshold_for("packages/kernel/tests/unit/test_a.py")
        == gate.UNIT_THRESHOLD
    )
    assert (
        gate.threshold_for("apps/backend/tests/integration/test_b.py")
        == gate.INTEGRATION_THRESHOLD
    )
    assert (
        gate.threshold_for("apps/backend/tests/e2e/test_c.py")
        == gate.INTEGRATION_THRESHOLD
    )
    assert (
        gate.threshold_for("tooling/quality/tests/test_gate.py") == gate.UNIT_THRESHOLD
    )


def test_test_names_collects_module_and_class_tests_only() -> None:
    source = """
def helper(): ...

def test_module(): ...

async def test_async(): ...

class TestSubject:
    def test_method(self): ...
    def utility(self): ...

class NotATest:
    def test_ignored_by_naming(self): ...  # still a test function by name rule
"""
    assert gate.test_names(source) == {
        "test_module",
        "test_async",
        "test_method",
        "test_ignored_by_naming",
    }


def test_new_test_names_subtracts_base() -> None:
    base = "def test_old(): ...\ndef test_kept(): ...\n"
    head = "def test_kept(): ...\ndef test_new(): ...\n"
    assert gate.new_test_names(base, head) == {"test_new"}
    assert gate.new_test_names(None, head) == {"test_kept", "test_new"}


def test_parse_junit_takes_slowest_param_and_strips_ids(tmp_path: Path) -> None:
    xml = tmp_path / "junit-0-0.xml"
    xml.write_text(
        """<testsuite>
        <testcase classname="x.tests.unit.a" name="test_fast" time="0.10"/>
        <testcase classname="x.tests.unit.a" name="test_slow[p1]" time="0.40"/>
        <testcase classname="x.tests.unit.a" name="test_slow[p2]" time="0.60"/>
        <testcase classname="x.tests.unit.a" name="test_missing_time"/>
        </testsuite>""",
        encoding="utf-8",
    )
    durations = gate.parse_junit([xml])
    assert durations == {
        "x/tests/unit/a.py": {"test_fast": 0.10, "test_slow": 0.60},
    }


def test_find_violations_blocks_only_new_unmarked_over_threshold() -> None:
    new_tests = {
        "x/tests/unit/a.py": {
            "test_new_slow",
            "test_new_fast",
            "test_new_marked",
        }
    }
    durations = {
        "x/tests/unit/a.py": {
            "test_new_slow": 2.0,
            "test_new_fast": 0.1,
            "test_new_marked": 9.0,
            "test_existing_slow": 30.0,
        }
    }
    exempt = {("x/tests/unit/a.py", "test_new_marked")}
    violations = gate.find_violations(new_tests, durations, exempt)
    assert violations == [
        ("x/tests/unit/a.py", "test_new_slow", 2.0, gate.UNIT_THRESHOLD),
    ]


def test_integration_paths_get_integration_threshold() -> None:
    new_tests = {"x/tests/integration/f.py": {"test_flow"}}
    durations = {"x/tests/integration/f.py": {"test_flow": 6.0}}
    violations = gate.find_violations(new_tests, durations, set())
    assert violations == [
        (
            "x/tests/integration/f.py",
            "test_flow",
            6.0,
            gate.INTEGRATION_THRESHOLD,
        ),
    ]


def test_new_tests_absent_from_junit_are_noted_not_blocked() -> None:
    new_tests = {"tooling/quality/tests/test_gate.py": {"test_local"}}
    violations = gate.find_violations(new_tests, {}, set())
    assert violations == []


class _Script:
    """Replace the git/collect subprocess layers with canned fixtures."""

    def __init__(
        self,
        files: list[str],
        new_names: dict[str, set[str]],
        marked: set[tuple[str, str]],
    ) -> None:
        self.files = files
        self.new_names = new_names
        self.marked = marked

    def changed_test_files(self, base: str, root: Path) -> list[str]:
        return self.files

    def new_tests_at_head(
        self, base: str, files: list[str], root: Path
    ) -> dict[str, set[str]]:
        return self.new_names

    def run_collect(self, files: list[str]) -> set[tuple[str, str]]:
        return self.marked


def _run_main(
    monkeypatch: pytest.MonkeyPatch, script: _Script, tmp_path: Path, junit: str | None
) -> int:
    if junit is not None:
        (tmp_path / "junit-0-0.xml").write_text(junit, encoding="utf-8")
    monkeypatch.setattr(gate, "changed_test_files", script.changed_test_files)
    monkeypatch.setattr(gate, "new_tests_at_head", script.new_tests_at_head)
    monkeypatch.setattr(gate, "run_collect", script.run_collect)
    return gate.main(["--junit-glob", "junit-*.xml", "--root", str(tmp_path)])


def test_exit_zero_when_no_changed_test_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    assert _run_main(monkeypatch, _Script([], {}, set()), tmp_path, None) == 0


def test_exit_zero_when_new_tests_within_threshold(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    script = _Script(
        ["x/tests/unit/a.py"],
        {"x/tests/unit/a.py": {"test_ok"}},
        set(),
    )
    junit = """<testsuite>
    <testcase classname="x.tests.unit.a" name="test_ok" time="0.20"/>
    </testsuite>"""
    assert _run_main(monkeypatch, script, tmp_path, junit) == 0


def test_exit_one_when_new_test_exceeds_threshold(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    script = _Script(
        ["x/tests/unit/a.py"],
        {"x/tests/unit/a.py": {"test_bad"}},
        set(),
    )
    junit = """<testsuite>
    <testcase classname="x.tests.unit.a" name="test_bad" time="1.50"/>
    </testsuite>"""
    assert _run_main(monkeypatch, script, tmp_path, junit) == 1


def test_exit_zero_when_over_threshold_new_test_is_marked(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    script = _Script(
        ["x/tests/unit/a.py"],
        {"x/tests/unit/a.py": {"test_marked"}},
        {("x/tests/unit/a.py", "test_marked")},
    )
    junit = """<testsuite>
    <testcase classname="x.tests.unit.a" name="test_marked" time="9.00"/>
    </testsuite>"""
    assert _run_main(monkeypatch, script, tmp_path, junit) == 0


def test_exit_one_when_junit_missing_but_new_tests_exist(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    script = _Script(
        ["x/tests/unit/a.py"],
        {"x/tests/unit/a.py": {"test_any"}},
        set(),
    )
    assert _run_main(monkeypatch, script, tmp_path, None) == 1


def test_existing_over_threshold_tests_do_not_block(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    script = _Script(
        ["x/tests/unit/a.py"],
        {"x/tests/unit/a.py": {"test_new_ok"}},
        set(),
    )
    junit = """<testsuite>
    <testcase classname="x.tests.unit.a" name="test_new_ok" time="0.10"/>
    <testcase classname="x.tests.unit.a" name="test_legacy" time="60.00"/>
    </testsuite>"""
    assert _run_main(monkeypatch, script, tmp_path, junit) == 0
