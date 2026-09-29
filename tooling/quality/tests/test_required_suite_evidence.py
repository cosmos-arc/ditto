"""Required-suite evidence must fail closed on any missing proof (#350)."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from tooling.quality.required_suite_evidence import (
    EvidenceError,
    _load_inventories,
    _required,
    run_checks,
)


def _write_tree(tmp_path: Path, *, pit: bool = False) -> None:
    inventory = [
        ["a/test_pure.py::test_one", False, False],
        ["a/test_pit.py::test_pit_edge", False, pit],
        [
            "apps/backend/tests/contract/test_conformance.py::test_conforms[/healthz]",
            False,
            False,
        ],
        ["a/test_serial.py::test_slow_lane", True, False],
    ]
    (tmp_path / "inventory-0.json").write_text(json.dumps(inventory) + "\n")
    (tmp_path / "inventory-1.json").write_text(json.dumps(inventory) + "\n")
    selected = [
        "a/test_pure.py::test_one",
        "a/test_pit.py::test_pit_edge",
        "apps/backend/tests/contract/test_conformance.py::test_conforms[/healthz]",
    ]
    (tmp_path / "nodes-0-False.txt").write_text("\n".join(selected[:2]) + "\n")
    (tmp_path / "nodes-1-False.txt").write_text(selected[2] + "\n")
    (tmp_path / "nodes-0-True.txt").write_text("a/test_serial.py::test_slow_lane\n")
    for name, count in (
        ("junit-0-False.xml", 2),
        ("junit-1-False.xml", 1),
        ("junit-0-True.xml", 1),
    ):
        root = ET.Element(
            "testsuites",
        )
        suite = ET.SubElement(
            root, "testsuite", {"tests": str(count), "errors": "0", "failures": "0"}
        )
        for i in range(count):
            ET.SubElement(suite, "testcase", {"classname": "x", "name": f"t{i}"})
        Path(tmp_path / name).write_text(ET.tostring(root, encoding="unicode"))


def _core_globs(tmp_path: Path) -> tuple[str, str, str]:
    return (
        str(tmp_path / "inventory-*.json"),
        str(tmp_path / "nodes-*.txt"),
        str(tmp_path / "junit-*.xml"),
    )


def _options(*, pit: bool) -> dict[str, object]:
    if pit:
        return {"pit_marker": True, "path": None}
    return {
        "pit_marker": False,
        "path": "apps/backend/tests/contract/test_conformance.py",
    }


def test_happy_path_proves_exactly_once_for_pit_and_path(tmp_path: Path) -> None:
    _write_tree(tmp_path, pit=True)
    assert run_checks(*_core_globs(tmp_path), **_options(pit=True)) == {
        "required": 1,
        "selection": "exactly-once",
        "junit": "lanes-consistent",
        "suite": "pit",
    }
    result = run_checks(*_core_globs(tmp_path), **_options(pit=False))
    assert result["required"] == 1


def test_empty_required_suite_fails_closed(tmp_path: Path) -> None:
    """缺清单：标记或路径不再匹配任何收集项时必须失败。"""
    _write_tree(tmp_path, pit=False)
    inventory = _load_inventories(str(tmp_path / "inventory-*.json"))
    with pytest.raises(EvidenceError, match="selected no tests"):
        _required(inventory, pit_marker=True, path=None)


def test_missing_required_nodeid_fails_closed(tmp_path: Path) -> None:
    """漏用例：清单里有、分片选择里没有必须失败。"""
    _write_tree(tmp_path, pit=True)
    (tmp_path / "nodes-0-False.txt").write_text("a/test_pure.py::test_one\n")
    (tmp_path / "junit-0-False.xml").write_text(
        ET.tostring(
            ET.fromstring(  # noqa: S314 - 测试内固定字面量
                '<testsuites><testsuite tests="1" errors="0" failures="0">'
                '<testcase classname="x" name="t0"/></testsuite></testsuites>'
            ),
            encoding="unicode",
        )
    )
    with pytest.raises(EvidenceError):
        run_checks(*_core_globs(tmp_path), **_options(pit=True))


def test_duplicated_selection_fails_closed(tmp_path: Path) -> None:
    """错误身份：同一 nodeid 被两片选择必须失败。"""
    _write_tree(tmp_path, pit=True)
    (tmp_path / "nodes-1-False.txt").write_text(
        (tmp_path / "nodes-0-False.txt").read_text(), encoding="utf-8"
    )
    with pytest.raises(EvidenceError):
        run_checks(*_core_globs(tmp_path), **_options(pit=True))


def test_short_junit_fails_closed(tmp_path: Path) -> None:
    """失败/取消：junit 计数少于选择数（例未真正执行）必须失败。"""
    _write_tree(tmp_path, pit=True)
    (tmp_path / "junit-0-False.xml").write_text(
        '<testsuites><testsuite tests="1" errors="0" failures="0">'
        '<testcase classname="x" name="t0"/></testsuite></testsuites>'
    )
    with pytest.raises(EvidenceError):
        run_checks(*_core_globs(tmp_path), **_options(pit=True))


def test_inventory_drift_across_shards_fails_closed(tmp_path: Path) -> None:
    """不同分片清单不一致（过期/异构）必须失败。"""
    _write_tree(tmp_path, pit=True)
    drifted = json.loads((tmp_path / "inventory-1.json").read_text())
    drifted[0][1] = True
    (tmp_path / "inventory-1.json").write_text(json.dumps(drifted) + "\n")
    with pytest.raises(EvidenceError, match="differs from the first shard"):
        _load_inventories(str(tmp_path / "inventory-*.json"))
