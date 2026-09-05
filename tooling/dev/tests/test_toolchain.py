from __future__ import annotations

import json
from pathlib import Path

import pytest
from tooling.dev.toolchain import ToolchainError, validate_toolchain


def _workspace(tmp_path: Path) -> Path:
    (tmp_path / "package.json").write_text(
        json.dumps({"packageManager": "bun@1.3.14"}), encoding="utf-8"
    )
    (tmp_path / "pixi.toml").write_text(
        (
            '[workspace]\nrequires-pixi = ">=0.73,<0.74"\n'
            '[dependencies]\npython = "3.13.*"\n'
        ),
        encoding="utf-8",
    )
    return tmp_path


def test_declared_and_actual_toolchains_match(tmp_path: Path) -> None:
    root = _workspace(tmp_path)

    validate_toolchain(
        root,
        actual={"bun": "1.3.14", "python": "3.13.14", "pixi": "0.73.0"},
    )


def test_pixi_at_manifest_upper_bound_fails_closed(tmp_path: Path) -> None:
    root = _workspace(tmp_path)

    with pytest.raises(ToolchainError, match=r"Pixi mismatch.*<0\.74"):
        validate_toolchain(
            root,
            actual={"bun": "1.3.14", "python": "3.13.14", "pixi": "0.74.0"},
        )


@pytest.mark.parametrize(
    ("actual", "message"),
    [
        ({"bun": "1.3.13", "python": "3.13.14", "pixi": "0.73.0"}, "Bun"),
        ({"bun": "1.3.14", "python": "3.12.9", "pixi": "0.73.0"}, "Python"),
        ({"bun": "1.3.14", "python": "3.13.14", "pixi": "0.72.0"}, "Pixi"),
    ],
)
def test_toolchain_mismatch_fails_closed(
    tmp_path: Path, actual: dict[str, str], message: str
) -> None:
    root = _workspace(tmp_path)

    with pytest.raises(ToolchainError, match=message):
        validate_toolchain(root, actual=actual)
