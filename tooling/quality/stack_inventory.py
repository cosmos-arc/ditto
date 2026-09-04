"""Keep the README technology inventory synchronized with source manifests."""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from pathlib import Path
from typing import cast

_START = "<!-- stack-inventory:start -->"
_END = "<!-- stack-inventory:end -->"


class InventoryError(ValueError):
    """Raised when an inventory fact or README boundary is ambiguous."""


def _table(value: object, *, source: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise InventoryError(f"{source} must be a table/object")
    return cast("dict[str, object]", value)


def _required_str(table: dict[str, object], key: str, *, source: str) -> str:
    value = table.get(key)
    if not isinstance(value, str) or not value:
        raise InventoryError(f"{source}: required string {key!r} is missing")
    return value


def _load_toml(path: Path) -> dict[str, object]:
    with path.open("rb") as file:
        return cast("dict[str, object]", tomllib.load(file))


def _load_json(path: Path) -> dict[str, object]:
    with path.open(encoding="utf-8") as file:
        return _table(json.load(file), source=path.as_posix())


def _dependency(
    package: dict[str, object], name: str, *, source: str
) -> str:
    for group in ("dependencies", "devDependencies"):
        dependencies = package.get(group)
        if isinstance(dependencies, dict):
            value = dependencies.get(name)
            if isinstance(value, str) and value:
                return value
    raise InventoryError(f"{source}: dependency {name!r} is missing")


def render_inventory(root: Path) -> str:
    """Render the canonical README block from repository manifests."""
    root = root.resolve()
    pyproject = _load_toml(root / "pyproject.toml")
    pixi = _load_toml(root / "pixi.toml")
    root_package = _load_json(root / "package.json")
    web_package = _load_json(root / "apps/web/package.json")

    project = _table(pyproject.get("project"), source="pyproject.toml [project]")
    workspace = _table(pixi.get("workspace"), source="pixi.toml [workspace]")
    dependencies = _table(
        pixi.get("dependencies"), source="pixi.toml [dependencies]"
    )
    package_manager = _required_str(
        root_package, "packageManager", source="package.json"
    )
    if not package_manager.startswith("bun@") or package_manager.count("@") != 1:
        raise InventoryError(
            "package.json: packageManager must pin an exact bun@<version>"
        )
    bun_version = package_manager.removeprefix("bun@")
    if not bun_version or any(character in bun_version for character in "*^~<>=|"):
        raise InventoryError(
            "package.json: packageManager must pin an exact bun@<version>"
        )

    rows = (
        (
            "产品版本",
            "pyproject.toml",
            _required_str(project, "version", source="pyproject.toml [project]"),
        ),
        (
            "Python",
            "pixi.toml",
            _required_str(dependencies, "python", source="pixi.toml [dependencies]"),
        ),
        (
            "Pixi",
            "pixi.toml",
            _required_str(workspace, "requires-pixi", source="pixi.toml [workspace]"),
        ),
        ("Bun", "package.json", bun_version),
        (
            "FastAPI",
            "pixi.toml",
            _required_str(
                dependencies, "fastapi", source="pixi.toml [dependencies]"
            ),
        ),
        (
            "Polars",
            "pixi.toml",
            _required_str(dependencies, "polars", source="pixi.toml [dependencies]"),
        ),
        (
            "React",
            "apps/web/package.json",
            _dependency(web_package, "react", source="apps/web/package.json"),
        ),
        (
            "TypeScript",
            "apps/web/package.json",
            _dependency(web_package, "typescript", source="apps/web/package.json"),
        ),
        (
            "Vite",
            "apps/web/package.json",
            _dependency(web_package, "vite", source="apps/web/package.json"),
        ),
    )
    lines = [
        _START,
        "| 范围 | 事实源 | 声明 |",
        "| --- | --- | --- |",
        *(f"| {scope} | `{source}` | `{value}` |" for scope, source, value in rows),
        _END,
    ]
    return "\n".join(lines)


def synchronize_readme(root: Path, *, write: bool) -> bool:
    """Check or update the single inventory block; return whether it is current."""
    root = root.resolve()
    readme_path = root / "README.md"
    document = readme_path.read_text(encoding="utf-8")
    if document.count(_START) != 1 or document.count(_END) != 1:
        raise InventoryError(
            "README.md must contain each inventory marker exactly once"
        )
    start = document.index(_START)
    end = document.index(_END, start) + len(_END)
    expected = document[:start] + render_inventory(root) + document[end:]
    current = expected == document
    if write and not current:
        readme_path.write_text(expected, encoding="utf-8")
        return True
    return current


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="repository root (defaults to the repository containing this tool)",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="replace the canonical README block instead of checking it",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the stack-inventory zero-diff gate."""
    arguments = _parser().parse_args(argv)
    try:
        current = synchronize_readme(arguments.root, write=arguments.write)
    except (
        InventoryError,
        OSError,
        tomllib.TOMLDecodeError,
        json.JSONDecodeError,
    ) as error:
        sys.stderr.write(f"Stack inventory error: {error}\n")
        return 2
    if not current:
        sys.stderr.write(
            "".join(
                (
                    "README technology inventory is stale; run ",
                    "`python tooling/quality/stack_inventory.py --write`.\n",
                )
            )
        )
        return 1
    action = "updated" if arguments.write else "is current"
    sys.stdout.write(f"README technology inventory {action}.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
