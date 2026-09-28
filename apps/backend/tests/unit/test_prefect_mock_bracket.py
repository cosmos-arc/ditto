"""Prefect mock 只在 backend unit 模块导入期间生效（#330 B1 导入期隔离）。"""

from __future__ import annotations

from ditto_apps import prefect_mock

pytest_plugins = ["pytester"]

_UNIT_CONFTEST = """
from pathlib import Path

from ditto_apps import prefect_mock
from tooling.quality.pytest_layering import register_import_bracket

register_import_bracket(
    Path(__file__).resolve().parent, prefect_mock.apply, prefect_mock.restore
)
"""

_UNIT_SIDE = """
from ditto_apps import prefect_mock

APPLIED_AT_IMPORT = prefect_mock.is_applied()


def test_unit_module_import_saw_the_mock():
    assert APPLIED_AT_IMPORT


def test_mock_is_restored_after_collection():
    assert not prefect_mock.is_applied()
"""

_FOREIGN_SIDE = """
from ditto_apps import prefect_mock

APPLIED_AT_IMPORT = prefect_mock.is_applied()


def test_foreign_module_import_saw_real_prefect():
    assert not APPLIED_AT_IMPORT
"""


def test_prefect_mock_brackets_backend_unit_imports(pytester) -> None:
    """合并收集下：unit 模块导入见 mock，外国模块见真实，结束恢复。"""
    unit_dir = pytester.path / "apps" / "backend" / "tests" / "unit"
    foreign_dir = pytester.path / "packages" / "other" / "tests" / "unit"
    unit_dir.mkdir(parents=True)
    foreign_dir.mkdir(parents=True)
    (unit_dir / "conftest.py").write_text(_UNIT_CONFTEST, encoding="utf-8")
    (unit_dir / "test_unit_side.py").write_text(_UNIT_SIDE, encoding="utf-8")
    (foreign_dir / "test_foreign_side.py").write_text(_FOREIGN_SIDE, encoding="utf-8")

    result = pytester.runpytest(
        "-q", "-p", "no:cacheprovider", "-p", "tooling.quality.pytest_layering"
    )

    result.assert_outcomes(passed=3)
    assert not prefect_mock.is_applied()
