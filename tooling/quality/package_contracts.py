"""Validate product package metadata against the root uv/Bun workspace."""

from __future__ import annotations

import json
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from packaging.requirements import InvalidRequirement, Requirement
from packaging.specifiers import SpecifierSet
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version


@dataclass(frozen=True)
class LeafPackage:
    """A local Python distribution and its declared project contract."""

    path: str
    name: str
    version: str
    dependencies: tuple[str, ...]


def _table(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    return cast("dict[str, object]", value)


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str))


def _load_toml(path: Path) -> dict[str, object]:
    with path.open("rb") as file:
        return cast("dict[str, object]", tomllib.load(file))


def _javascript_version_violations(root: Path, product_version: str) -> list[str]:
    """Keep both Bun manifests in the same product-version cohort as Python."""
    violations: list[str] = []
    for relative in ("package.json", "apps/web/package.json"):
        path = root / relative
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            violations.append(f"{relative}: cannot read a valid JSON manifest: {error}")
            continue
        if not isinstance(document, dict):
            violations.append(f"{relative}: manifest must contain a JSON object")
            continue
        version = document.get("version")
        if version != product_version:
            violations.append(
                f"{relative}: version {version!r} must equal product version "
                f"{product_version!r}"
            )
    return violations


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).parent.as_posix()


def _discover_leaves(root: Path) -> tuple[LeafPackage, ...]:
    manifests = sorted((root / "packages").glob("*/pyproject.toml"))
    backend = root / "apps/backend/pyproject.toml"
    if backend.is_file():
        manifests.append(backend)

    leaves: list[LeafPackage] = []
    for manifest in manifests:
        project = _table(_load_toml(manifest).get("project"))
        name = project.get("name")
        version = project.get("version")
        if not isinstance(name, str) or not isinstance(version, str):
            continue
        leaves.append(
            LeafPackage(
                path=_relative(root, manifest),
                name=canonicalize_name(name),
                version=version,
                dependencies=_strings(project.get("dependencies")),
            )
        )
    return tuple(leaves)


def _root_local_packages(root: Path, document: dict[str, object]) -> dict[str, str]:
    uv = _table(_table(document.get("tool")).get("uv"))
    sources = _table(uv.get("sources"))
    members = _strings(_table(uv.get("workspace")).get("members"))
    packages: dict[str, str] = {}
    for member in members:
        for directory in root.glob(member):
            project = _table(_load_toml(directory / "pyproject.toml").get("project"))
            name = project.get("name")
            if (
                isinstance(name, str)
                and _table(sources.get(name)).get("workspace") is True
            ):
                packages[directory.relative_to(root).as_posix()] = canonicalize_name(
                    name
                )
    return packages


def _root_constraints(document: dict[str, object]) -> dict[str, SpecifierSet]:
    declarations = _strings(_table(document.get("project")).get("dependencies"))
    return {
        canonicalize_name(requirement.name): requirement.specifier
        for declaration in declarations
        if (requirement := Requirement(declaration))
    }


def _load_lock(path: Path) -> tuple[dict[str, str], dict[str, set[str]]]:
    document = _load_toml(path)
    entries = document.get("package")
    if not isinstance(entries, list):
        return {}, {}
    local: dict[str, str] = {}
    resolved: dict[str, set[str]] = {}
    for raw_entry in entries:
        entry = _table(raw_entry)
        name, version = entry.get("name"), entry.get("version")
        if not isinstance(name, str) or not isinstance(version, str):
            continue
        source = _table(entry.get("source"))
        editable = source.get("editable")
        if isinstance(editable, str):
            local[editable] = canonicalize_name(name)
        elif "registry" in source:
            resolved.setdefault(canonicalize_name(name), set()).add(version)
    return local, resolved


def _dependency_violations(
    leaves: tuple[LeafPackage, ...],
    local_names: set[str],
    root_constraints: dict[str, SpecifierSet],
    resolved: dict[str, set[str]],
) -> list[str]:
    violations: list[str] = []
    for leaf in leaves:
        for declaration in leaf.dependencies:
            try:
                requirement = Requirement(declaration)
            except InvalidRequirement:
                violations.append(
                    f"{leaf.path}: invalid dependency requirement {declaration!r}"
                )
                continue
            name = canonicalize_name(requirement.name)
            if name in local_names:
                continue
            versions = resolved.get(name, set())
            if not versions:
                violations.append(
                    f"{leaf.path}: dependency {declaration!r} is absent from uv.lock"
                )
                continue
            combined = requirement.specifier
            root_specifier = root_constraints.get(name)
            for raw_version in sorted(versions):
                try:
                    version = Version(raw_version)
                except InvalidVersion:
                    violations.append(
                        " ".join(
                            (
                                f"uv.lock: dependency {name!r} has invalid version",
                                repr(raw_version),
                            )
                        )
                    )
                    continue
                if version not in combined or (
                    root_specifier is not None and version not in root_specifier
                ):
                    violations.append(
                        " ".join(
                            (
                                f"{leaf.path}: dependency {declaration!r}",
                                f"conflicts with resolved {name} {raw_version}",
                            )
                        )
                    )
    return violations


def _mapping_violations(
    *, source: str, actual: dict[str, str], expected: dict[str, str]
) -> list[str]:
    violations = [
        f"{source} is missing local package {path}"
        for path in sorted(expected.keys() - actual.keys())
    ]
    violations.extend(
        f"{source} contains unknown local package path {path}"
        for path in sorted(actual.keys() - expected.keys())
    )
    for path in sorted(expected.keys() & actual.keys()):
        if actual[path] != expected[path]:
            violations.append(
                " ".join(
                    (
                        f"{source} local package {path} is named {actual[path]!r};",
                        f"expected {expected[path]!r}",
                    )
                )
            )
    return violations


def validate_workspace(root: Path, *, expected_local_count: int = 13) -> list[str]:
    """Return deterministic package-contract violations for ``root``."""
    root = root.resolve()
    document = _load_toml(root / "pyproject.toml")
    root_project = _table(document.get("project"))
    product_version = root_project.get("version")
    violations: list[str] = []
    if not isinstance(product_version, str):
        violations.append("pyproject.toml: [project].version is required")
        product_version = ""
    violations.extend(_javascript_version_violations(root, product_version))

    leaves = _discover_leaves(root)
    if len(leaves) != expected_local_count:
        violations.append(
            " ".join(
                (
                    f"expected {expected_local_count} local Python packages,",
                    f"discovered {len(leaves)}",
                )
            )
        )
    expected = {leaf.path: leaf.name for leaf in leaves}
    for leaf in leaves:
        if leaf.version != product_version:
            violations.append(
                " ".join(
                    (
                        f"{leaf.path}: version {leaf.version!r}",
                        f"must equal product version {product_version!r}",
                    )
                )
            )

    declared = _root_local_packages(root, document)
    violations.extend(
        _mapping_violations(
            source="pyproject.toml [tool.uv.sources]",
            actual=declared,
            expected=expected,
        )
    )

    locked, resolved = _load_lock(root / "uv.lock")
    violations.extend(
        _mapping_violations(source="uv.lock", actual=locked, expected=expected)
    )

    violations.extend(
        _dependency_violations(
            leaves,
            set(expected.values()),
            _root_constraints(document),
            resolved,
        )
    )
    return sorted(set(violations))


def main() -> int:
    """Run the package contract gate for the repository containing this file."""
    root = Path(__file__).resolve().parents[2]
    violations = validate_workspace(root)
    if violations:
        sys.stderr.write("Product package contract violations:\n")
        sys.stderr.write("\n".join(f"- {item}" for item in violations) + "\n")
        return 1
    sys.stdout.write("Product package contracts are consistent.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
