from __future__ import annotations

import json
from pathlib import Path

import pytest
from tooling.dev.toolchain import ToolchainError, validate_toolchain


def _workspace(tmp_path: Path) -> Path:
    (tmp_path / ".node-version").write_text("24.20.0\n", encoding="utf-8")
    (tmp_path / "package.json").write_text(
        json.dumps({"packageManager": "bun@1.3.14"}), encoding="utf-8"
    )
    (tmp_path / ".python-version").write_text("cpython-3.13.14\n", encoding="utf-8")
    (tmp_path / ".task-version").write_text("3.53.1\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        '[tool.uv]\nrequired-version = "==0.12.7"\n', encoding="utf-8"
    )
    return tmp_path


def test_declared_and_actual_toolchains_match(tmp_path: Path) -> None:
    root = _workspace(tmp_path)

    validate_toolchain(
        root,
        actual={
            "bun": "1.3.14",
            "python": "3.13.14",
            "uv": "uv 0.12.7",
            "task": "3.53.1",
            "node": "v24.20.0",
        },
    )


def test_uv_version_mismatch_fails_closed(tmp_path: Path) -> None:
    root = _workspace(tmp_path)

    with pytest.raises(ToolchainError, match="uv mismatch"):
        validate_toolchain(
            root,
            actual={
                "bun": "1.3.14",
                "python": "3.13.14",
                "uv": "uv 0.12.8",
                "task": "3.53.1",
            },
        )


@pytest.mark.parametrize(
    ("actual", "message"),
    [
        (
            {
                "bun": "1.3.13",
                "python": "3.13.14",
                "uv": "uv 0.12.7",
                "task": "3.53.1",
                "node": "v24.20.0",
            },
            "Bun",
        ),
        (
            {
                "bun": "1.3.14",
                "python": "3.12.9",
                "uv": "uv 0.12.7",
                "task": "3.53.1",
                "node": "v24.20.0",
            },
            "Python",
        ),
        (
            {"bun": "1.3.14", "python": "3.13.14", "uv": "uv 0.12.6", "task": "3.53.1"},
            "uv",
        ),
    ],
)
def test_toolchain_mismatch_fails_closed(
    tmp_path: Path, actual: dict[str, str], message: str
) -> None:
    root = _workspace(tmp_path)

    with pytest.raises(ToolchainError, match=message):
        validate_toolchain(root, actual=actual)


@pytest.mark.parametrize("node", [None, "v22.19.0", "v24.18.0"])
def test_node_mismatch_fails_closed(tmp_path: Path, node: str | None) -> None:
    actual = {"bun": "1.3.14", "python": "3.13.14", "uv": "uv 0.12.7", "task": "3.53.1"}
    if node is not None:
        actual["node"] = node
    with pytest.raises(ToolchainError, match="Node mismatch"):
        validate_toolchain(_workspace(tmp_path), actual=actual)
