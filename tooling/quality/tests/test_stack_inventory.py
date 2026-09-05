import json
from pathlib import Path

import pytest

from tooling.quality.stack_inventory import (
    InventoryError,
    render_inventory,
    synchronize_readme,
)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    _write(
        tmp_path / "pyproject.toml",
        '[project]\nname = "workspace"\nversion = "1.2.3"\n',
    )
    _write(
        tmp_path / "pixi.toml",
        """\
[workspace]
requires-pixi = ">=0.73,<0.74"

[dependencies]
python = "3.13.*"
fastapi = ">=0.115,<0.137"
polars = ">=1.9,<2"
""",
    )
    _write(
        tmp_path / "package.json",
        json.dumps({"packageManager": "bun@1.3.14"}),
    )
    _write(
        tmp_path / "apps/web/package.json",
        json.dumps(
            {
                "dependencies": {"react": "^19.2.4"},
                "devDependencies": {
                    "typescript": "~6.0.2",
                    "vite": "^8.0.2",
                },
            }
        ),
    )
    _write(
        tmp_path / "README.md",
        "before\n<!-- stack-inventory:start -->\nstale\n"
        "<!-- stack-inventory:end -->\nafter\n",
    )
    return tmp_path


def test_render_inventory_reads_only_declared_manifest_versions(
    workspace: Path,
) -> None:
    inventory = render_inventory(workspace)

    assert "| 产品版本 | `pyproject.toml` | `1.2.3` |" in inventory
    assert "| Pixi | `pixi.toml` | `>=0.73,<0.74` |" in inventory
    assert "| Bun | `package.json` | `1.3.14` |" in inventory
    assert "| React | `apps/web/package.json` | `^19.2.4` |" in inventory


def test_check_reports_drift_without_mutating_readme(workspace: Path) -> None:
    readme = workspace / "README.md"
    original = readme.read_text(encoding="utf-8")

    assert synchronize_readme(workspace, write=False) is False
    assert readme.read_text(encoding="utf-8") == original


def test_write_then_check_is_zero_diff(workspace: Path) -> None:
    assert synchronize_readme(workspace, write=True) is True
    assert synchronize_readme(workspace, write=False) is True
    assert "stale" not in (workspace / "README.md").read_text(encoding="utf-8")


def test_missing_manifest_key_fails_closed(workspace: Path) -> None:
    web_package = workspace / "apps/web/package.json"
    web_package.write_text(json.dumps({"dependencies": {"react": "^19.2.4"}}))

    with pytest.raises(InventoryError, match="typescript"):
        render_inventory(workspace)


def test_duplicate_markers_fail_closed(workspace: Path) -> None:
    readme = workspace / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8")
        + "<!-- stack-inventory:start --><!-- stack-inventory:end -->"
    )

    with pytest.raises(InventoryError, match="exactly once"):
        synchronize_readme(workspace, write=True)
