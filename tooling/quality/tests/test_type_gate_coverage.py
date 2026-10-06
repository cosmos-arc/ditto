"""Pin type-gate coverage to on-disk reality (#539).

单星 glob 在 basedpyright 的 include 中不展开——`packages/*/tests` 曾让 12 个包
的 1020 个测试文件静默落在类型门外。本守卫钉死四件事：

1. tests include 是字面目录清单且与磁盘 tests 目录集合完全一致（新包/新
   tooling tests 目录不登记即红）；
2. include 不含任何通配符（杜绝再次静默失效的写法）；
3. 生产门 include 显式覆盖 ``apps/backend/src``（曾长期两腿门外）；
4. tests 门不挂 baselineFile（#540 清零后防存量债悄悄回潮）。
"""

import json
import tomllib
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_TESTS_CONFIG = _REPO_ROOT / "pyright.tests.json"
_PYPROJECT = _REPO_ROOT / "pyproject.toml"

# 与仓库布局约定的不可枚举目录保持一致（vendor/生成物/运行数据）。
_SKIP_ANY_PART = {"__pycache__", "node_modules", ".venv", ".git"}
_SKIP_TOP_LEVEL = {
    "build",
    "dist",
    "data",
    "artifacts",
    ".cache",
    ".codex",
    ".zcode",
    ".hypothesis",
    ".pytest_cache",
    ".ruff_cache",
    "test-results",
    "logs",
    ".importlinter_cache",
    ".github",
}


def _on_disk_test_roots() -> set[str]:
    roots = set()
    for path in _REPO_ROOT.rglob("tests"):
        if not path.is_dir():
            continue
        relative = path.relative_to(_REPO_ROOT)
        if relative.parts[0] in _SKIP_TOP_LEVEL or any(
            part in _SKIP_ANY_PART for part in relative.parts
        ):
            continue
        if any(item.suffix == ".py" for item in path.rglob("*.py")):
            roots.add(relative.as_posix())
    return roots


def _tests_include() -> list[str]:
    config = json.loads(_TESTS_CONFIG.read_text(encoding="utf-8"))
    return [str(entry) for entry in config["include"]]


def test_tests_include_matches_on_disk_test_roots_exactly() -> None:
    """include == 磁盘现实：新 tests 目录必须显式登记，删除目录必须同步摘除."""
    assert set(_tests_include()) == _on_disk_test_roots()


def test_tests_include_entries_are_literal_directories() -> None:
    """通配符写法整体禁用（单星静默不展开、双星语义随工具版本漂移）."""
    for entry in _tests_include():
        assert "*" not in entry, entry
        assert (_REPO_ROOT / entry).is_dir(), entry


def test_tests_gate_runs_without_baseline() -> None:
    """#540 清零后 tests 门不得再挂 baselineFile（防存量债悄悄回潮）."""
    config = json.loads(_TESTS_CONFIG.read_text(encoding="utf-8"))
    assert "baselineFile" not in config, "tests 类型门已清零, 不得重新引入 baseline"


def test_prod_include_covers_backend_source() -> None:
    """apps/backend/src 必须显式在生产门 include 里（曾仅是 extraPaths）."""
    with _PYPROJECT.open("rb") as handle:
        pyproject = tomllib.load(handle)
    include = pyproject["tool"]["basedpyright"]["include"]
    assert "apps/backend/src" in include
    for entry in include:
        assert "*" not in entry or "**" in entry, f"单星 glob 不可用: {entry}"


def test_guard_self_check_disk_enumeration_is_non_trivial() -> None:
    """守卫自身的枚举必须看见真实规模，防止跳过逻辑误伤成空集."""
    roots = _on_disk_test_roots()
    assert len(roots) >= 19
    assert "packages/data/tests" in roots
    assert "tests" in roots
