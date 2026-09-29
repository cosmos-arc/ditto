"""Required-suite evidence must fail closed on any missing proof (#350)."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from tooling.quality.required_suite_evidence import (
    EvidenceError,
    required_from_dump,
    run_checks,
)

_DUMP = {
    "a/test_pure.py::test_one": ["unit"],
    "a/test_pit.py::test_pit_edge": ["pit"],
    # P2：同时带 capacity 的 pit 用例在分片 inventory 的 -m 过滤下缺席，
    # 必备集必须从无过滤收集推导才不会静默漏掉它。
    "a/test_pit_capacity.py::test_capacity_pit": ["pit", "capacity"],
    "apps/backend/tests/contract/test_conformance.py::test_conforms[/healthz]": [
        "integration"
    ],
    "a/test_serial.py::test_slow_lane": ["integration", "serial"],
}


def _write_artifacts(tmp_path: Path, *, include_capacity_pit: bool = True) -> None:
    selected = [
        "a/test_pure.py::test_one",
        "a/test_pit.py::test_pit_edge",
        "apps/backend/tests/contract/test_conformance.py::test_conforms[/healthz]",
        "a/test_serial.py::test_slow_lane",
    ]
    if include_capacity_pit:
        # capacity 慢道另行执行；此处以节点选择文件表达"已在某道执行"
        selected.insert(2, "a/test_pit_capacity.py::test_capacity_pit")
    (tmp_path / "nodes-0-False.txt").write_text(
        "\n".join(n for n in selected if n != "a/test_serial.py::test_slow_lane")
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "nodes-0-True.txt").write_text(
        "a/test_serial.py::test_slow_lane\n", encoding="utf-8"
    )
    for name, count in (
        ("junit-0-False.xml", len(selected) - 1),
        ("junit-0-True.xml", 1),
    ):
        root = ET.Element("testsuites")
        suite = ET.SubElement(
            root, "testsuite", {"tests": str(count), "errors": "0", "failures": "0"}
        )
        for i in range(count):
            ET.SubElement(suite, "testcase", {"classname": "x", "name": f"t{i}"})
        (tmp_path / name).write_text(ET.tostring(root, encoding="unicode"))


def _globs(tmp_path: Path) -> dict[str, str]:
    return {
        "nodes_glob": str(tmp_path / "nodes-*.txt"),
        "junit_glob": str(tmp_path / "junit-*.xml"),
    }


def test_required_from_dump_unions_pit_and_path_and_keeps_capacity_overlap() -> None:
    """P2：无过滤收集使 pit+capacity 用例进入必备集。"""
    pit = required_from_dump(_DUMP, pit_marker=True, path=None)
    assert pit == [
        "a/test_pit.py::test_pit_edge",
        "a/test_pit_capacity.py::test_capacity_pit",
    ]
    conformance = required_from_dump(
        _DUMP,
        pit_marker=False,
        path="apps/backend/tests/contract/test_conformance.py",
    )
    assert conformance == [
        "apps/backend/tests/contract/test_conformance.py::test_conforms[/healthz]"
    ]


def test_empty_required_suite_fails_closed() -> None:
    """缺清单：标记或路径不再匹配任何收集项时必须失败。"""
    with pytest.raises(EvidenceError, match="selected no tests"):
        required_from_dump({"a.py::test_x": ["unit"]}, pit_marker=True, path=None)


def test_happy_path_proves_exactly_once(tmp_path: Path) -> None:
    _write_artifacts(tmp_path)
    required = required_from_dump(_DUMP, pit_marker=True, path=None)
    result = run_checks(required, **_globs(tmp_path))
    assert result == {
        "required": 2,
        "selection": "exactly-once",
        "junit": "lanes-consistent",
    }


def test_pit_test_excluded_from_shards_fails_closed(tmp_path: Path) -> None:
    """P2 反例：pit+capacity 用例若不在任何分片选择中必须失败（暴露而非忽略）。"""
    _write_artifacts(tmp_path, include_capacity_pit=False)
    (tmp_path / "junit-0-False.xml").write_text(
        '<testsuites><testsuite tests="3" errors="0" failures="0">'
        '<testcase classname="x" name="t0"/><testcase classname="x" name="t1"/>'
        '<testcase classname="x" name="t2"/></testsuite></testsuites>',
        encoding="utf-8",
    )
    required = required_from_dump(_DUMP, pit_marker=True, path=None)
    with pytest.raises(EvidenceError, match="missing from shard selection"):
        run_checks(required, **_globs(tmp_path))


def test_duplicated_selection_fails_closed(tmp_path: Path) -> None:
    """错误身份：同一 nodeid 被两道选择必须失败。"""
    _write_artifacts(tmp_path)
    (tmp_path / "nodes-1-False.txt").write_text(
        "a/test_pit.py::test_pit_edge\n", encoding="utf-8"
    )
    (tmp_path / "junit-1-False.xml").write_text(
        '<testsuites><testsuite tests="1" errors="0" failures="0">'
        '<testcase classname="x" name="t0"/></testsuite></testsuites>',
        encoding="utf-8",
    )
    required = required_from_dump(_DUMP, pit_marker=True, path=None)
    with pytest.raises(EvidenceError, match="duplicated across shard selection"):
        run_checks(required, **_globs(tmp_path))


def test_short_junit_fails_closed(tmp_path: Path) -> None:
    """失败/取消：junit 计数少于选择数（例未真正执行）必须失败。"""
    _write_artifacts(tmp_path)
    (tmp_path / "junit-0-False.xml").write_text(
        '<testsuites><testsuite tests="1" errors="0" failures="0">'
        '<testcase classname="x" name="t0"/></testsuite></testsuites>',
        encoding="utf-8",
    )
    required = required_from_dump(_DUMP, pit_marker=True, path=None)
    with pytest.raises(EvidenceError, match="junit records"):
        run_checks(required, **_globs(tmp_path))


def test_main_rejects_missing_selectors(tmp_path: Path) -> None:
    from tooling.quality.required_suite_evidence import main

    with pytest.raises(SystemExit):
        main(["--nodes-glob", "x", "--junit-glob", "y"])
