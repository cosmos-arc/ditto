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


def test_fast_lane_expression_is_shared_and_layer_free(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--fast 与 harness 探针同一表达式，且不含 unit/integration 层级（#330 B1）。"""
    from tooling.quality.test_selection import FAST_LANE_EXPR

    monkeypatch.setattr(sys, "argv", ["test.py", "--fast"])
    command = build_pytest_command()
    marker_index = command.index("-m")
    assert command[marker_index + 1] == FAST_LANE_EXPR
    assert "integration" not in FAST_LANE_EXPR
    assert "unit" not in FAST_LANE_EXPR
    assert "not serial" in FAST_LANE_EXPR
