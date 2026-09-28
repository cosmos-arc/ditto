"""The entry-consistency checker proves stability and catches legacy drift."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tooling.quality import entry_consistency

REPO_ROOT = Path(__file__).resolve().parents[3]


def _with_repo_on_pythonpath(monkeypatch: pytest.MonkeyPatch) -> None:
    existing = os.environ.get("PYTHONPATH")
    value = str(REPO_ROOT) if not existing else f"{REPO_ROOT}{os.pathsep}{existing}"
    monkeypatch.setenv("PYTHONPATH", value)


_TREE_FILES = {
    "packages/alpha/tests/unit/test_a.py": "def test_one():\n    assert True\n",
    "packages/alpha/tests/integration/test_b.py": (
        "def test_two():\n    assert True\n"
    ),
    "packages/beta/tests/unit/test_g_integration.py": (
        "def test_three():\n    assert True\n"
    ),
    "apps/backend/tests/contract/test_d.py": ("def test_four():\n    assert True\n"),
    "tooling/demo/tests/test_f.py": "def test_six():\n    assert True\n",
}

_ROOT_CONFTEST = 'pytest_plugins = ["tooling.quality.pytest_layering"]\n'

# 旧式近端钩子：relative_to 失败时按绝对路径子串给外国 item 加标（#330 B1
# 移除的缺陷形态）。beta 的 test_g_integration 只在合并入口被它加上 serial。
_LEGACY_ALPHA_CONFTEST = """\
import pytest
from pathlib import Path

_ROOT = Path(__file__).parent


def pytest_collection_modifyitems(items):
    for item in items:
        try:
            rel = item.path.relative_to(_ROOT)
        except ValueError:
            rel = None
        path = str(rel) if rel else str(item.fspath)
        if "integration" in path:
            item.add_marker(pytest.mark.serial)
"""

# 静默缩集形态：alpha 的钩子在合并入口直接 deselect 外国 item——checker 必须
# 以成员关系失败报警，而不是只看幸存 nodeid 的标记一致性。
_DESELECT_ALPHA_CONFTEST = """\
import pytest
from pathlib import Path

_ROOT = Path(__file__).parent


def pytest_collection_modifyitems(items):
    items[:] = [
        item
        for item in items
        if _ROOT in item.path.parents or "beta" not in item.path.parts
    ]
"""

# 反向缩集形态：钩子只在"本树单独跑"时 deselect 自己的 integration 项
# （全仓入口因存在外国 item 而保留）——owner 成员关系必须双向核对。
_DESELECT_OWN_ALPHA_CONFTEST = """\
import pytest
from pathlib import Path

_ROOT = Path(__file__).parent


def pytest_collection_modifyitems(items):
    if all(_ROOT in item.path.parents for item in items):
        items[:] = [
            item
            for item in items
            if "integration" not in item.path.parts
        ]
"""


def _make_tree(root: Path, *, alpha_conftest: str | None) -> None:
    (root / "conftest.py").write_text(_ROOT_CONFTEST, encoding="utf-8")
    for relative, body in _TREE_FILES.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    if alpha_conftest is not None:
        (root / "packages/alpha/tests/conftest.py").write_text(
            alpha_conftest, encoding="utf-8"
        )


def test_checker_passes_when_entries_agree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    _make_tree(root, alpha_conftest=None)
    _with_repo_on_pythonpath(monkeypatch)

    code = entry_consistency.main(["--root", str(root)])

    assert code == 0
    assert "stable" in capsys.readouterr().out


def test_checker_flags_foreign_marker_drift_from_a_near_conftest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    _make_tree(root, alpha_conftest=_LEGACY_ALPHA_CONFTEST)
    _with_repo_on_pythonpath(monkeypatch)

    code = entry_consistency.main(["--root", str(root)])

    assert code == 1
    out = capsys.readouterr().out
    assert "test_g_integration.py" in out
    assert "entry drift" in out


def test_checker_flags_a_near_conftest_silently_dropping_foreign_items(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    _make_tree(root, alpha_conftest=_DESELECT_ALPHA_CONFTEST)
    _with_repo_on_pythonpath(monkeypatch)

    code = entry_consistency.main(["--root", str(root)])

    assert code == 1
    out = capsys.readouterr().out
    assert "membership failure" in out
    assert "owner:packages/beta/tests" in out


def test_checker_flags_an_owner_entry_dropping_its_own_items(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """反向缩集：owner 单独入口丢自己、全仓保留——成员关系双向核对。"""
    root = tmp_path / "repo"
    root.mkdir()
    _make_tree(root, alpha_conftest=_DESELECT_OWN_ALPHA_CONFTEST)
    _with_repo_on_pythonpath(monkeypatch)

    code = entry_consistency.main(["--root", str(root)])

    assert code == 1
    out = capsys.readouterr().out
    assert "membership failure" in out
    assert "dropped 1 of its own nodeids" in out
    assert "owner:packages/alpha/tests" in out


def test_marker_names_containing_and_survive_exclusion() -> None:
    """sandbox_live 含 "and" 子串——排除判定不得按 "and" 切表达式字符串。"""
    assert (
        entry_consistency._expr_allows(
            ["integration", "sandbox_live", "serial"],
            entry_consistency.SHARD_EXCLUDED_MARKERS,
        )
        is False
    )
    assert (
        entry_consistency._expr_allows(
            ["unit"], entry_consistency.SHARD_EXCLUDED_MARKERS
        )
        is True
    )
    assert (
        entry_consistency.SHARD_EXPR
        == "not snapshot and not sandbox_live and not capacity"
    )
