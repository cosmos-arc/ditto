"""Default-construction and Windows runtime fallback edges for XDG paths."""

from __future__ import annotations

from pathlib import Path

import pytest
from ditto_platform.foundation.config import XDGPaths


def test_paths_without_base_override_honor_explicit_data_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_root = tmp_path / "data"
    monkeypatch.setenv("DITTO_DATA_DIR", str(data_root))

    paths = XDGPaths()

    assert paths.data_home == data_root


def test_windows_runtime_fallback_uses_user_temp_when_temp_is_unset(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DITTO_RUNTIME_DIR", raising=False)
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.delenv("TEMP", raising=False)
    paths = XDGPaths(base_dir=tmp_path)
    paths._platform = "win32"

    runtime = paths.runtime_dir

    assert runtime.parts[-3:] == ("ditto", "temp", "ditto")
