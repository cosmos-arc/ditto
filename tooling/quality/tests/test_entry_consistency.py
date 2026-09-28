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


def _make_tree(root: Path, *, legacy_alpha_hook: bool) -> None:
    (root / "conftest.py").write_text(_ROOT_CONFTEST, encoding="utf-8")
    for relative, body in _TREE_FILES.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    if legacy_alpha_hook:
        (root / "packages/alpha/tests/conftest.py").write_text(
            _LEGACY_ALPHA_CONFTEST, encoding="utf-8"
        )


def test_checker_passes_when_entries_agree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    _make_tree(root, legacy_alpha_hook=False)
    _with_repo_on_pythonpath(monkeypatch)

    code = entry_consistency.main(["--root", str(root)])

    assert code == 0
    assert "stable" in capsys.readouterr().out


def test_checker_flags_foreign_marker_drift_from_a_near_conftest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    _make_tree(root, legacy_alpha_hook=True)
    _with_repo_on_pythonpath(monkeypatch)

    code = entry_consistency.main(["--root", str(root)])

    assert code == 1
    out = capsys.readouterr().out
    assert "test_g_integration.py" in out
    assert "entry drift" in out
