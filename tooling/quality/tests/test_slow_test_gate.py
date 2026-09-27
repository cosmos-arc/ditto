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


def test_test_names_collects_class_qualified_ids() -> None:
    source = """
def helper(): ...

def test_module(): ...

async def test_async(): ...

class TestSubject:
    def test_method(self): ...
    def utility(self): ...

class TestOuter:
    class TestInner:
        def test_nested(self): ...
"""
    assert gate.test_names(source) == {
        "test_module",
        "test_async",
        "TestSubject.test_method",
        "TestOuter.TestInner.test_nested",
    }


def test_new_test_names_distinguishes_classes() -> None:
    base = "class TestA:\n    def test_valid(self): ...\n"
    head = (
        "class TestA:\n    def test_valid(self): ...\n\n"
        "class TestB:\n    def test_valid(self): ...\n"
    )
    assert gate.new_test_names(base, head) == {"TestB.test_valid"}
    assert gate.new_test_names(None, head) == {
        "TestA.test_valid",
        "TestB.test_valid",
    }


def test_parse_junit_keeps_class_identity_and_merges_params(tmp_path: Path) -> None:
    module = tmp_path / "x/tests/unit/a.py"
    module.parent.mkdir(parents=True)
    module.write_text("", encoding="utf-8")
    xml = tmp_path / "junit-0-0.xml"
    xml.write_text(
        """<testsuite>
        <testcase classname="x.tests.unit.a" name="test_fast" time="0.10"/>
        <testcase classname="x.tests.unit.a" name="test_slow[p1]" time="0.40"/>
        <testcase classname="x.tests.unit.a" name="test_slow[p2]" time="0.60"/>
        <testcase classname="x.tests.unit.a.TestSubject" name="test_m" time="0.20"/>
        <testcase classname="x.tests.unit.a.TestOther" name="test_m" time="0.90"/>
        <testcase classname="x.tests.unit.a" name="test_missing_time"/>
        <testcase classname="nowhere.on.disk" name="test_ghost" time="9.00"/>
        </testsuite>""",
        encoding="utf-8",
    )
    durations = gate.parse_junit([xml], tmp_path)
    assert durations == {
        "x/tests/unit/a.py": {
            "test_fast": 0.10,
            "test_slow": 0.60,
            "TestSubject.test_m": 0.20,
            "TestOther.test_m": 0.90,
        },
    }


def test_parse_name_status_maps_renames_to_base_path() -> None:
    raw = "R100\0old/test_a.py\0new/test_a.py\0M\0mod/test_b.py\0A\0added.py\0"
    assert gate.parse_name_status(raw) == {
        "new/test_a.py": "old/test_a.py",
        "mod/test_b.py": "mod/test_b.py",
        "added.py": "added.py",
    }


def test_new_tests_at_head_ignores_base_of_non_test_rename() -> None:
    files = {"x/tests/unit/test_helpers.py": "x/tests/unit/helpers.py"}
    collected = {("x/tests/unit/test_helpers.py", "test_activated")}
    base_source = "def test_activated(): ...  # 非测试文件的既有函数"
    new = gate.new_tests_at_head(
        "base", files, collected, Path(), show=lambda b, p, r: base_source
    )
    assert new == {"x/tests/unit/test_helpers.py": {"test_activated"}}


def test_new_tests_at_head_subtracts_test_rename_base() -> None:
    files = {"x/tests/unit/test_new.py": "x/tests/unit/test_old.py"}
    collected = {("x/tests/unit/test_new.py", "test_kept")}
    base_source = "def test_kept(): ...\n"
    new = gate.new_tests_at_head(
        "base", files, collected, Path(), show=lambda b, p, r: base_source
    )
    assert new == {}


def test_find_violations_blocks_only_new_unmarked_over_threshold() -> None:
    new_tests = {
        "x/tests/unit/a.py": {"test_new_slow", "test_new_fast", "test_new_marked"}
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


def test_legacy_class_duration_never_blocks_new_same_name_class() -> None:
    new_tests = {"x/tests/unit/a.py": {"TestB.test_valid"}}
    durations = {
        "x/tests/unit/a.py": {
            "TestA.test_valid": 2.0,
            "TestB.test_valid": 0.1,
        }
    }
    assert gate.find_violations(new_tests, durations, set()) == []


def test_marked_class_exemption_does_not_leak_to_other_class() -> None:
    new_tests = {"x/tests/unit/a.py": {"TestOther.test_marked"}}
    durations = {"x/tests/unit/a.py": {"TestOther.test_marked": 9.0}}
    exempt = {("x/tests/unit/a.py", "TestSubject.test_marked")}
    violations = gate.find_violations(new_tests, durations, exempt)
    assert violations == [
        ("x/tests/unit/a.py", "TestOther.test_marked", 9.0, gate.UNIT_THRESHOLD),
    ]


def test_integration_paths_get_integration_threshold() -> None:
    new_tests = {"x/tests/integration/f.py": {"test_flow"}}
    durations = {"x/tests/integration/f.py": {"test_flow": 6.0}}
    violations = gate.find_violations(new_tests, durations, set())
    assert violations == [
        ("x/tests/integration/f.py", "test_flow", 6.0, gate.INTEGRATION_THRESHOLD),
    ]


def test_new_tests_absent_from_junit_are_noted_not_blocked() -> None:
    new_tests = {"tooling/quality/tests/test_gate.py": {"test_local"}}
    violations = gate.find_violations(new_tests, {}, set())
    assert violations == []


class _Script:
    """Replace the git/collect subprocess layers with canned fixtures."""

    def __init__(
        self,
        files: dict[str, str],
        new_names: dict[str, set[str]],
        marked: set[tuple[str, str]],
    ) -> None:
        self.files = files
        self.new_names = new_names
        self.marked = marked

    def changed_test_files(self, base: str, root: Path) -> dict[str, str]:
        return self.files

    def collect_ids(
        self, changed_files: list[str], marker_expr: str | None = None
    ) -> set[tuple[str, str]]:
        return set(self.marked) if marker_expr else set()

    def new_tests_at_head(
        self,
        base: str,
        files: dict[str, str],
        collected: set[tuple[str, str]],
        root: Path,
        show=gate._git_show,
    ) -> dict[str, set[str]]:
        return self.new_names


def _run_main(
    monkeypatch: pytest.MonkeyPatch, script: _Script, tmp_path: Path, junit: str | None
) -> int:
    if junit is not None:
        module = tmp_path / "x/tests/unit/a.py"
        module.parent.mkdir(parents=True, exist_ok=True)
        module.write_text("", encoding="utf-8")
        (tmp_path / "junit-0-0.xml").write_text(junit, encoding="utf-8")
    monkeypatch.setattr(gate, "changed_test_files", script.changed_test_files)
    monkeypatch.setattr(gate, "collect_ids", script.collect_ids)
    monkeypatch.setattr(gate, "new_tests_at_head", script.new_tests_at_head)
    return gate.main(["--junit-glob", "junit-*.xml", "--root", str(tmp_path)])


def _files() -> dict[str, str]:
    return {"x/tests/unit/a.py": "x/tests/unit/a.py"}


def test_exit_zero_when_no_changed_test_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    assert _run_main(monkeypatch, _Script({}, {}, set()), tmp_path, None) == 0


def test_exit_zero_when_new_tests_within_threshold(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    script = _Script(_files(), {"x/tests/unit/a.py": {"test_ok"}}, set())
    junit = """<testsuite>
    <testcase classname="x.tests.unit.a" name="test_ok" time="0.20"/>
    </testsuite>"""
    assert _run_main(monkeypatch, script, tmp_path, junit) == 0


def test_exit_one_when_new_test_exceeds_threshold(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    script = _Script(_files(), {"x/tests/unit/a.py": {"test_bad"}}, set())
    junit = """<testsuite>
    <testcase classname="x.tests.unit.a" name="test_bad" time="1.50"/>
    </testsuite>"""
    assert _run_main(monkeypatch, script, tmp_path, junit) == 1


def test_exit_one_when_new_class_test_exceeds_threshold(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    script = _Script(_files(), {"x/tests/unit/a.py": {"TestSubject.test_bad"}}, set())
    junit = """<testsuite>
    <testcase classname="x.tests.unit.a.TestSubject" name="test_bad" time="1.50"/>
    </testsuite>"""
    assert _run_main(monkeypatch, script, tmp_path, junit) == 1


def test_exit_zero_when_over_threshold_new_test_is_marked(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    script = _Script(
        _files(),
        {"x/tests/unit/a.py": {"TestSubject.test_marked"}},
        {("x/tests/unit/a.py", "TestSubject.test_marked")},
    )
    junit = """<testsuite>
    <testcase classname="x.tests.unit.a.TestSubject" name="test_marked" time="9.00"/>
    </testsuite>"""
    assert _run_main(monkeypatch, script, tmp_path, junit) == 0


def test_exit_one_when_junit_missing_but_new_tests_exist(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    script = _Script(_files(), {"x/tests/unit/a.py": {"test_any"}}, set())
    assert _run_main(monkeypatch, script, tmp_path, None) == 1


def test_existing_over_threshold_tests_do_not_block(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    script = _Script(_files(), {"x/tests/unit/a.py": {"test_new_ok"}}, set())
    junit = """<testsuite>
    <testcase classname="x.tests.unit.a" name="test_new_ok" time="0.10"/>
    <testcase classname="x.tests.unit.a" name="test_legacy" time="60.00"/>
    </testsuite>"""
    assert _run_main(monkeypatch, script, tmp_path, junit) == 0
