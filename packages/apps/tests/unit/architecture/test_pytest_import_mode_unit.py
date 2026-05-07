"""Pytest collection must use importlib mode for duplicate test basenames."""

from pathlib import Path


def test_pytest_addopts_enforces_importlib_import_mode() -> None:
    text = Path("pyproject.toml").read_text(encoding="utf-8")
    assert '"--import-mode=importlib"' in text


def test_test_wrapper_enforces_importlib_import_mode() -> None:
    text = Path("scripts/test.py").read_text(encoding="utf-8")
    assert '"--import-mode=importlib"' in text
