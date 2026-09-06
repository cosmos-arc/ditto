"""Pytest collection must use importlib mode for duplicate test basenames."""

import os
import runpy
import subprocess
import sys
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


def test_wrapper_isolates_keyring_before_collection_and_in_workers(
    tmp_path: Path,
) -> None:
    probe = tmp_path / "pytest"
    probe.write_text(
        f"#!{sys.executable}\n"
        "import os, subprocess, sys\n"
        "assert os.environ['PYTHON_KEYRING_BACKEND'] "
        "== 'keyring.backends.null.Keyring'\n"
        "subprocess.run([sys.executable, '-c', "
        "\"import keyring; assert keyring.get_password('test', 'user') is None\"], "
        "check=True)\n"
        "sys.exit(23)\n"
    )
    probe.chmod(0o755)
    environment = {
        **os.environ,
        "PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}",
        "PYTHON_KEYRING_BACKEND": "unexpected.host.Backend",
    }
    result = subprocess.run(
        [sys.executable, "scripts/test.py", "--fast"],
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 23, result.stderr
