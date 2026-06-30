"""Root package public API contract checks."""

import ast
import re
from pathlib import Path

_PUBLIC_API_MANIFEST = Path("docs/architecture/public-api.md")
_ROOT_API_SECTION = "### Root Package API Surface"


def _declares_all(init_file: Path) -> bool:
    tree = ast.parse(init_file.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "__all__"
            for target in node.targets
        ):
            return True
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "__all__"
        ):
            return True
    return False


def _literal_all(init_file: Path) -> list[str]:
    tree = ast.parse(init_file.read_text(encoding="utf-8"))
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "__all__"
                for target in node.targets
            )
        ) or (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "__all__"
        ):
            value = node.value
            if value is None:
                continue
            symbols = ast.literal_eval(value)
            return list(symbols)
    msg = f"{init_file} does not declare __all__"
    raise AssertionError(msg)


def _root_public_api_entries() -> dict[str, list[str]]:
    lines = _PUBLIC_API_MANIFEST.read_text(encoding="utf-8").splitlines()
    start = next(index for index, line in enumerate(lines) if line == _ROOT_API_SECTION)
    entries: dict[str, list[str]] = {}
    for line in lines[start + 1 :]:
        if line.startswith("### "):
            break
        if not line.startswith("| `"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) != 4:
            continue
        package = cells[0].strip("`")
        symbols = re.findall(r"`([^`]+)`", cells[1])
        entries[package] = [] if symbols == ["[]"] else symbols
    return entries


def test_all_root_packages_declare_explicit_all() -> None:
    root = Path.cwd()
    missing = [
        init_file.relative_to(root).as_posix()
        for init_file in sorted(root.glob("packages/*/src/ditto_*/__init__.py"))
        if not _declares_all(init_file)
    ]

    assert missing == [], "\n".join(missing)


def test_root_public_api_manifest_matches_package_all() -> None:
    """Stable root exports should be reviewer-visible and drift-guarded."""
    root = Path.cwd()
    actual = {
        init_file.parent.name: _literal_all(init_file)
        for init_file in sorted(root.glob("packages/*/src/ditto_*/__init__.py"))
    }

    manifest = _root_public_api_entries()

    assert manifest == actual
