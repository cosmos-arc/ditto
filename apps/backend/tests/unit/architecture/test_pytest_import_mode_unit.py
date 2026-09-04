"""Pytest collection must use importlib mode for duplicate test basenames."""

import runpy
from collections.abc import Callable
from pathlib import Path
from typing import cast


def test_pytest_addopts_enforces_importlib_import_mode() -> None:
    text = Path("pyproject.toml").read_text(encoding="utf-8")
    assert '"--import-mode=importlib"' in text


def test_test_wrapper_enforces_importlib_import_mode() -> None:
    text = Path("scripts/test.py").read_text(encoding="utf-8")
    assert '"--import-mode=importlib"' in text


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
