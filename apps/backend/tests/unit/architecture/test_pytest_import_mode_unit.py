"""Pytest collection must use importlib mode for duplicate test basenames."""

import runpy
import tomllib
from collections.abc import Callable
from pathlib import Path
from typing import cast


def test_pytest_addopts_enforces_importlib_import_mode() -> None:
    text = Path("pyproject.toml").read_text(encoding="utf-8")
    assert '"--import-mode=importlib"' in text


def test_test_wrapper_enforces_importlib_import_mode() -> None:
    text = Path("scripts/test.py").read_text(encoding="utf-8")
    assert '"--import-mode=importlib"' in text


def test_coverage_uses_official_subprocess_patch() -> None:
    """Python child processes must contribute to the combined pytest-cov report."""
    with Path("pyproject.toml").open("rb") as pyproject:
        coverage_run = tomllib.load(pyproject)["tool"]["coverage"]["run"]

    assert coverage_run["patch"] == ["subprocess"]


def test_pytest_declares_the_monorepo_root_for_cross_package_test_support() -> None:
    """Focused test selection must not depend on another suite mutating sys.path."""
    with Path("pyproject.toml").open("rb") as pyproject:
        pytest_options = tomllib.load(pyproject)["tool"]["pytest"]["ini_options"]

    assert "." in pytest_options["pythonpath"]


def test_default_test_wrapper_excludes_physical_sandbox_acceptance(
    monkeypatch,
) -> None:
    build_pytest_command = cast(
        "Callable[[], list[str]]",
        runpy.run_path("scripts/test.py")["build_pytest_command"],
    )
    for arguments in (["--cov-xml"], ["--fast"]):
        monkeypatch.setattr("sys.argv", ["scripts/test.py", *arguments])
        command = build_pytest_command()

        marker_expression = command[command.index("-m") + 1]
        assert "not sandbox_live" in marker_expression
