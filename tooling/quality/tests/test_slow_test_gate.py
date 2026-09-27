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


def test_normalize_case_keeps_parameter_identity() -> None:
    assert gate.normalize_case(
        "x/tests/unit/a.py::TestSubject::test_m[slow::case]"
    ) == (
        "x/tests/unit/a.py",
        "TestSubject.test_m[slow::case]",
    )
    assert gate.normalize_case("x/tests/unit/a.py::test_plain") == (
        "x/tests/unit/a.py",
        "test_plain",
    )
    assert gate.normalize_case("warning: some noisy line") is None


def test_function_of_strips_parameter_suffix() -> None:
    assert gate.function_of("TestSubject.test_m[case]") == "TestSubject.test_m"
    assert gate.function_of("test_plain") == "test_plain"


def test_parse_junit_keeps_case_level_identity(tmp_path: Path) -> None:
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
            "test_slow[p1]": 0.40,
            "test_slow[p2]": 0.60,
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


def test_new_tests_at_head_detects_added_parameter_case() -> None:
    files = {"x/tests/unit/test_q.py": "x/tests/unit/test_q.py"}
    collected_cases = {
        ("x/tests/unit/test_q.py", "test_query[old]"),
        ("x/tests/unit/test_q.py", "test_query[new]"),
    }
    base_cases = {("x/tests/unit/test_q.py", "test_query[old]")}
    assert gate.new_tests_at_head(files, collected_cases, base_cases) == {
        "x/tests/unit/test_q.py": {"test_query[new]"}
    }


def test_new_tests_at_head_subtracts_base_collection_identities() -> None:
    files = {"x/tests/unit/test_new.py": "x/tests/unit/test_old.py"}
    collected_cases = {
        ("x/tests/unit/test_new.py", "test_kept"),
        ("x/tests/unit/test_new.py", "TestActivated.test_slow"),
        ("x/tests/unit/test_new.py", "TestChild.test_inherited"),
    }
    base_cases = {
        ("x/tests/unit/test_old.py", "test_kept"),
        ("x/tests/unit/test_old.py", "TestChild.test_inherited"),
    }
    assert gate.new_tests_at_head(files, collected_cases, base_cases) == {
        "x/tests/unit/test_new.py": {"TestActivated.test_slow"}
    }


def test_all_marked_functions_requires_every_case_marked() -> None:
    raw_total = {"x/a.py::test_m[p1]", "x/a.py::test_m[p2]", "x/a.py::test_plain"}
    raw_marked = {"x/a.py::test_m[p1]"}
    assert gate.all_marked_functions(raw_total, raw_marked) == set()
    raw_marked_all = {"x/a.py::test_m[p1]", "x/a.py::test_m[p2]"}
    assert gate.all_marked_functions(raw_total, raw_marked_all) == {
        ("x/a.py", "test_m")
    }


def test_find_violations_blocks_only_new_unmarked_over_threshold() -> None:
    new_cases = {
        "x/tests/unit/a.py": {
            "test_new_slow",
            "test_new_fast",
            "TestSubject.test_marked",
        }
    }
    durations = {
        "x/tests/unit/a.py": {
            "test_new_slow": 2.0,
            "test_new_fast": 0.1,
            "TestSubject.test_marked": 9.0,
            "test_legacy": 30.0,
        }
    }
    exempt = {("x/tests/unit/a.py", "TestSubject.test_marked")}
    violations = gate.find_violations(new_cases, durations, exempt)
    assert violations == [
        ("x/tests/unit/a.py", "test_new_slow", 2.0, gate.UNIT_THRESHOLD),
    ]


def test_find_violations_falls_back_to_function_duration_for_new_case() -> None:
    new_cases = {"x/tests/unit/a.py": {"test_query[new]"}}
    durations = {"x/tests/unit/a.py": {"test_query": 2.0}}
    violations = gate.find_violations(new_cases, durations, set())
    assert violations == [
        ("x/tests/unit/a.py", "test_query[new]", 2.0, gate.UNIT_THRESHOLD),
    ]


def test_partial_layer_marker_does_not_relax_budget() -> None:
    new_cases = {"x/tests/mix/test_mix.py": {"test_m[unmarked]"}}
    durations = {"x/tests/mix/test_mix.py": {"test_m[unmarked]": 2.0}}
    integration_by_file = {"x/tests/mix/test_mix.py": {"test_other"}}
    violations = gate.find_violations(
        new_cases, durations, set(), {}, integration_by_file
    )
    assert violations == [
        ("x/tests/mix/test_mix.py", "test_m[unmarked]", 2.0, gate.UNIT_THRESHOLD),
    ]


def test_unit_marker_beats_e2e_path_budget() -> None:
    new_cases = {"x/tests/e2e/reporter.py": {"test_unit_marked_helper"}}
    durations = {"x/tests/e2e/reporter.py": {"test_unit_marked_helper": 1.5}}
    unit_by_file = {"x/tests/e2e/reporter.py": {"test_unit_marked_helper"}}
    violations = gate.find_violations(new_cases, durations, set(), unit_by_file, {})
    assert violations == [
        (
            "x/tests/e2e/reporter.py",
            "test_unit_marked_helper",
            1.5,
            gate.UNIT_THRESHOLD,
        ),
    ]


def test_gate_scope_whole_suite_for_production_changes() -> None:
    seeds = "packages/application/src/ditto_application/seeds.py"
    kernel_test = "packages/kernel/tests/unit/test_unchanged.py"
    name_status = {
        seeds: seeds,
        kernel_test: kernel_test,
        "docs/README.md": "docs/README.md",
    }
    assert gate.gate_scope(name_status) is None


def test_gate_scope_owner_dir_for_conftest_changes() -> None:
    conftest = "packages/strategy/tests/conftest.py"
    assert gate.gate_scope({conftest: conftest}) == {
        "packages/strategy/tests": "packages/strategy/tests"
    }


def test_new_tests_at_head_matches_directory_scope_by_prefix() -> None:
    files = {"packages/application/tests": "packages/application/tests"}
    collected = {
        ("packages/application/tests/unit/test_a.py", "test_new"),
        ("packages/application/tests/unit/test_a.py", "test_kept"),
        ("packages/kernel/tests/unit/test_b.py", "test_kernel"),
    }
    base = {("packages/application/tests/unit/test_a.py", "test_kept")}
    assert gate.new_tests_at_head(files, collected, base) == {
        "packages/application/tests": {"test_new"}
    }


def test_is_managed_test_path_distinguishes_blind_spots() -> None:
    assert gate._is_managed_test_path("packages/kernel/tests/unit/test_a.py")
    assert gate._is_managed_test_path("apps/backend/tests/e2e/test_b.py")
    assert not gate._is_managed_test_path("tooling/quality/tests/test_gate.py")


class _Script:
    """Replace the git/collect subprocess layers with canned raw fixtures."""

    def __init__(
        self,
        files: dict[str, str],
        new_cases: dict[str, set[str]],
        raw_all: set[str],
        raw_marked: set[str],
        base_cases: set[tuple[str, str]] | None = None,
    ) -> None:
        self.files = files
        self.new_cases = new_cases
        self.raw_all = raw_all
        self.raw_marked = raw_marked
        self.base_cases: set[tuple[str, str]] = base_cases or set()

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
        tolerate_collection_errors: bool = False,
    ) -> set[str]:
        return set(self.raw_marked) if marker_expr else set(self.raw_all)

    def collect_base_ids(
        self, base: str, base_paths, root: Path
    ) -> set[tuple[str, str]]:
        return self.base_cases


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


def _raw(case_id: str) -> set[str]:
    return {f"x/tests/unit/a.py::{case_id}"}


def _files() -> dict[str, str]:
    return {"x/tests/unit/a.py": "x/tests/unit/a.py"}


def _script(
    new_cases: dict[str, set[str]],
    marked: set[str] | None = None,
    raw_all: set[str] | None = None,
) -> _Script:
    derived = {
        rid for cases in new_cases.values() for case in cases for rid in _raw(case)
    }
    return _Script(_files(), new_cases, raw_all or derived, marked or set())


def _junit(entry: str) -> str:
    name, _, param = entry.partition("[")
    display = entry if param else name
    return f'<testcase classname="x.tests.unit.a" name="{display}" time="1.50"/>'


def test_exit_zero_when_no_changed_test_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    assert _run_main(monkeypatch, _Script({}, {}, set(), set()), tmp_path, None) == 0


def test_exit_zero_when_new_tests_within_threshold(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    script = _script({"x/tests/unit/a.py": {"test_ok"}})
    junit = f"""<testsuite>
    {_junit("test_ok")}
    </testsuite>""".replace('time="1.50"', 'time="0.20"')
    assert _run_main(monkeypatch, script, tmp_path, junit) == 0


def test_exit_one_when_new_test_exceeds_threshold(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    script = _script({"x/tests/unit/a.py": {"test_bad"}})
    junit = f"""<testsuite>
    {_junit("test_bad")}
    </testsuite>"""
    assert _run_main(monkeypatch, script, tmp_path, junit) == 1


def test_exit_one_when_new_parameter_case_exceeds_threshold(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    script = _script(
        {"x/tests/unit/a.py": {"test_query[new]"}},
        raw_all={*_raw("test_query[old]"), *_raw("test_query[new]")},
    )
    junit = """<testsuite>
    <testcase classname="x.tests.unit.a" name="test_query[new]" time="1.50"/>
    </testsuite>"""
    assert _run_main(monkeypatch, script, tmp_path, junit) == 1


def test_exit_one_when_managed_new_case_has_no_junit_evidence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    files = {"packages/x/tests/unit/a.py": "packages/x/tests/unit/a.py"}
    raw = {"packages/x/tests/unit/a.py::test_ghost"}
    script = _Script(files, {"packages/x/tests/unit/a.py": {"test_ghost"}}, raw, set())
    module = tmp_path / "packages/x/tests/unit/a.py"
    module.parent.mkdir(parents=True, exist_ok=True)
    module.write_text("", encoding="utf-8")
    monkeypatch.setattr(gate, "resolve_base", script.resolve_base)
    monkeypatch.setattr(gate, "changed_test_files", script.changed_test_files)
    monkeypatch.setattr(gate, "collect_ids", script.collect_ids)
    monkeypatch.setattr(gate, "collect_base_ids", script.collect_base_ids)
    code = gate.main(["--junit-glob", "junit-*.xml", "--root", str(tmp_path)])
    assert code == 1


def test_exit_zero_when_blind_spot_case_has_no_junit_evidence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    files = {"tooling/quality/tests/test_gate.py": "tooling/quality/tests/test_gate.py"}
    script = _Script(
        files, {"tooling/quality/tests/test_gate.py": {"test_local"}}, set(), set()
    )
    junit = """<testsuite>
    <testcase classname="x.tests.unit.a" name="test_other" time="0.10"/>
    </testsuite>"""
    assert _run_main(monkeypatch, script, tmp_path, junit) == 0


def test_exit_zero_when_every_parameter_case_is_marked(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    script = _script(
        {"x/tests/unit/a.py": {"test_marked[case]"}},
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
