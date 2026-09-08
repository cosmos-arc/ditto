"""Test CLI options must reach pytest without losing option values."""

import sys

import pytest
from scripts.test import build_pytest_command


def test_pytest_options_and_paths_are_forwarded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "test.py",
            "--fast",
            "packages/data/tests",
            "-k",
            "empty or missing",
            "-n",
            "0",
            "--maxfail=1",
        ],
    )
    command = build_pytest_command()
    assert command[-6:] == [
        "packages/data/tests",
        "-k",
        "empty or missing",
        "-n",
        "0",
        "--maxfail=1",
    ]
    assert "--fast" not in command
