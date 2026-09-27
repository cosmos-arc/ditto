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


def test_normalize_node_isolates_parameter_suffix_first() -> None:
    assert gate.normalize_node(
        "x/tests/unit/a.py::TestSubject::test_m[slow::case]"
    ) == (
        "x/tests/unit/a.py",
        "TestSubject.test_m",
    )
    assert gate.normalize_node("x/tests/unit/a.py::test_plain") == (
        "x/tests/unit/a.py",
        "test_plain",
    )
    assert gate.normalize_node("warning: some noisy line") is None


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


def test_new_tests_at_head_subtracts_base_collection_identities() -> None:
    files = {"x/tests/unit/test_new.py": "x/tests/unit/test_old.py"}
    collected = {
        ("x/tests/unit/test_new.py", "test_kept"),
        ("x/tests/unit/test_new.py", "TestActivated.test_slow"),
        ("x/tests/unit/test_new.py", "TestChild.test_inherited"),
    }
    base_ids = {
        ("x/tests/unit/test_old.py", "test_kept"),
        ("x/tests/unit/test_old.py", "TestChild.test_inherited"),
    }
    assert gate.new_tests_at_head(files, collected, base_ids) == {
        "x/tests/unit/test_new.py": {"TestActivated.test_slow"}
    }


def test_new_tests_at_head_counts_non_test_rename_as_fully_new() -> None:
    files = {"x/tests/unit/test_helpers.py": "x/tests/unit/helpers.py"}
    collected = {("x/tests/unit/test_helpers.py", "test_activated")}
    base_ids = set()  # 基线收集对非测试路径收集不到任何身份
    assert gate.new_tests_at_head(files, collected, base_ids) == {
        "x/tests/unit/test_helpers.py": {"test_activated"}
    }


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


def test_unit_marker_beats_e2e_path_budget() -> None:
    new_tests = {"x/tests/e2e/reporter.py": {"test_unit_marked_helper"}}
    durations = {"x/tests/e2e/reporter.py": {"test_unit_marked_helper": 1.5}}
    unit_nodes = {("x/tests/e2e/reporter.py", "test_unit_marked_helper")}
    violations = gate.find_violations(new_tests, durations, set(), unit_nodes, set())
    assert violations == [
        (
            "x/tests/e2e/reporter.py",
            "test_unit_marked_helper",
            1.5,
            gate.UNIT_THRESHOLD,
        ),
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
    """Replace the git/collect subprocess layers with canned raw fixtures."""

    def __init__(
        self,
        files: dict[str, str],
        new_names: dict[str, set[str]],
        raw_all: set[str],
        raw_marked: set[str],
        base_ids: set[tuple[str, str]] | None = None,
    ) -> None:
        self.files = files
        self.new_names = new_names
        self.raw_all = raw_all
        self.raw_marked = raw_marked
        self.base_ids: set[tuple[str, str]] = base_ids or set()

    def changed_test_files(self, base: str, root: Path) -> dict[str, str]:
        return self.files

    def resolve_base(self, base: str, root: Path) -> str:
        return "base0000"

    def collect_ids(
        self,
        changed_files: list[str] | None,
        marker_expr: str | None = None,
        *,
        cwd: Path | None = None,
    ) -> set[str]:
        return set(self.raw_marked) if marker_expr else set(self.raw_all)

    def collect_base_ids(
        self, base: str, base_paths, root: Path
    ) -> set[tuple[str, str]]:
        return self.base_ids


def _run_main(
    monkeypatch: pytest.MonkeyPatch, script: _Script, tmp_path: Path, junit: str | None
) -> int:
    if junit is not None:
        module = tmp_path / "x/tests/unit/a.py"
        module.parent.mkdir(parents=True, exist_ok=True)
        module.write_text("", encoding="utf-8")
        (tmp_path / "junit-0-0.xml").write_text(junit, encoding="utf-8")
    monkeypatch.setattr(gate, "resolve_base", script.resolve_base)
    monkeypatch.setattr(gate, "changed_test_files", script.changed_test_files)
    monkeypatch.setattr(gate, "collect_ids", script.collect_ids)
    monkeypatch.setattr(gate, "collect_base_ids", script.collect_base_ids)
    return gate.main(["--junit-glob", "junit-*.xml", "--root", str(tmp_path)])


def _raw(pair_id: str) -> set[str]:
    return {f"x/tests/unit/a.py::{pair_id}"}


def _files() -> dict[str, str]:
    return {"x/tests/unit/a.py": "x/tests/unit/a.py"}


def _script(
    new_names: dict[str, set[str]],
    marked: set[str] | None = None,
    raw_all: set[str] | None = None,
) -> _Script:
    derived = {
        rid for names in new_names.values() for name in names for rid in _raw(name)
    }
    return _Script(_files(), new_names, raw_all or derived, marked or set())


def test_exit_zero_when_no_changed_test_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    assert _run_main(monkeypatch, _Script({}, {}, set(), set()), tmp_path, None) == 0


def test_exit_zero_when_new_tests_within_threshold(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    script = _script({"x/tests/unit/a.py": {"test_ok"}})
    junit = """<testsuite>
    <testcase classname="x.tests.unit.a" name="test_ok" time="0.20"/>
    </testsuite>"""
    assert _run_main(monkeypatch, script, tmp_path, junit) == 0


def test_exit_one_when_new_test_exceeds_threshold(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    script = _script({"x/tests/unit/a.py": {"test_bad"}})
    junit = """<testsuite>
    <testcase classname="x.tests.unit.a" name="test_bad" time="1.50"/>
    </testsuite>"""
    assert _run_main(monkeypatch, script, tmp_path, junit) == 1


def test_exit_one_when_new_class_test_exceeds_threshold(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    script = _script({"x/tests/unit/a.py": {"TestSubject.test_bad"}})
    junit = """<testsuite>
    <testcase classname="x.tests.unit.a.TestSubject" name="test_bad" time="1.50"/>
    </testsuite>"""
    assert _run_main(monkeypatch, script, tmp_path, junit) == 1


def test_exit_zero_when_every_parameter_case_is_marked(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    script = _script(
        {"x/tests/unit/a.py": {"test_marked"}},
        marked=_raw("test_marked[case]"),
    )
    junit = """<testsuite>
    <testcase classname="x.tests.unit.a" name="test_marked[case]" time="9.00"/>
    </testsuite>"""
    assert _run_main(monkeypatch, script, tmp_path, junit) == 0


def test_exit_one_when_only_some_parameter_cases_are_marked(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    script = _script(
        {"x/tests/unit/a.py": {"test_partial"}},
        marked=_raw("test_partial[marked]"),
        raw_all={*_raw("test_partial[marked]"), *_raw("test_partial[unmarked]")},
    )
    junit = """<testsuite>
    <testcase classname="x.tests.unit.a" name="test_partial[marked]" time="0.10"/>
    <testcase classname="x.tests.unit.a" name="test_partial[unmarked]" time="9.00"/>
    </testsuite>"""
    assert _run_main(monkeypatch, script, tmp_path, junit) == 1


def test_exit_one_when_junit_missing_but_new_tests_exist(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    script = _script({"x/tests/unit/a.py": {"test_any"}})
    assert _run_main(monkeypatch, script, tmp_path, None) == 1


def test_existing_over_threshold_tests_do_not_block(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    script = _script({"x/tests/unit/a.py": {"test_new_ok"}})
    junit = """<testsuite>
    <testcase classname="x.tests.unit.a" name="test_new_ok" time="0.10"/>
    <testcase classname="x.tests.unit.a" name="test_legacy" time="60.00"/>
    </testsuite>"""
    assert _run_main(monkeypatch, script, tmp_path, junit) == 0
