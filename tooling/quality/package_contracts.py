"""Validate product package metadata against the root Pixi/Bun workspace."""

from __future__ import annotations

import json
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from re import compile as compile_pattern
from typing import cast
from urllib.parse import urlparse

import yaml
from packaging.requirements import InvalidRequirement, Requirement
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

_CONDA_ARTIFACT = compile_pattern(
    r"^(?P<name>.+)-(?P<version>\d[^-]*)-[^-]+\.(?:conda|tar\.bz2)$"
)


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


def _root_local_packages(pixi: dict[str, object]) -> dict[str, str]:
    declarations = _table(pixi.get("pypi-dependencies"))
    packages: dict[str, str] = {}
    for raw_name, raw_value in declarations.items():
        value = _table(raw_value)
        path = value.get("path")
        if isinstance(path, str):
            packages[path.removeprefix("./").rstrip("/")] = canonicalize_name(raw_name)
    return packages


def _root_constraints(pixi: dict[str, object]) -> dict[str, SpecifierSet]:
    constraints: dict[str, SpecifierSet] = {}
    for table_name in ("dependencies", "pypi-dependencies"):
        for raw_name, raw_value in _table(pixi.get(table_name)).items():
            if not isinstance(raw_value, str):
                continue
            try:
                constraints[canonicalize_name(raw_name)] = SpecifierSet(raw_value)
            except InvalidSpecifier:
                continue
    return constraints


def _load_lock(path: Path) -> tuple[dict[str, str], dict[str, set[str]]]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    document = _table(raw)
    entries = document.get("packages")
    if not isinstance(entries, list):
        return {}, {}

    local: dict[str, str] = {}
    resolved: dict[str, set[str]] = {}
    for raw_entry in entries:
        entry = _table(raw_entry)
        name = entry.get("name")
        version = entry.get("version")
        conda_source = entry.get("conda")
        if (
            (not isinstance(name, str) or not isinstance(version, str))
            and isinstance(conda_source, str)
            and (
                match := _CONDA_ARTIFACT.fullmatch(
                    Path(urlparse(conda_source).path).name
                )
            )
        ):
            name = match.group("name")
            version = match.group("version")
        if not isinstance(name, str):
            continue
        canonical_name = canonicalize_name(name)
        source = entry.get("pypi")
        if isinstance(source, str) and source.startswith("./"):
            local[source.removeprefix("./").rstrip("/")] = canonical_name
            continue
        if isinstance(version, str):
            resolved.setdefault(canonical_name, set()).add(version)
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
                    f"{leaf.path}: dependency {declaration!r} is absent from pixi.lock"
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
                                f"pixi.lock: dependency {name!r} has invalid version",
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
    root_project = _table(_load_toml(root / "pyproject.toml").get("project"))
    pixi = _load_toml(root / "pixi.toml")
    workspace = _table(pixi.get("workspace"))
    product_version = root_project.get("version")
    pixi_version = workspace.get("version")
    violations: list[str] = []
    if not isinstance(product_version, str):
        violations.append("pyproject.toml: [project].version is required")
        product_version = ""
    if pixi_version != product_version:
        violations.append(
            "pixi.toml: [workspace].version must equal pyproject.toml [project].version"
        )
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

    declared = _root_local_packages(pixi)
    violations.extend(
        _mapping_violations(
            source="pixi.toml [pypi-dependencies]",
            actual=declared,
            expected=expected,
        )
    )

    locked, resolved = _load_lock(root / "pixi.lock")
    violations.extend(
        _mapping_violations(source="pixi.lock", actual=locked, expected=expected)
    )

    violations.extend(
        _dependency_violations(
            leaves,
            set(expected.values()),
            _root_constraints(pixi),
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
