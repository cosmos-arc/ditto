"""Validate Web architecture/discovery manifests against their declared inputs."""

from __future__ import annotations

import argparse
import hashlib
import json
import stat
import sys
from pathlib import Path, PurePosixPath
from typing import cast

_DEFAULT_MANIFESTS = (".arch-manifest.json", ".discovery-manifest.json")
_ARCHITECTURE_KIND = "architecture-inventory"
_DISCOVERY_KIND = "discovery-inventory"


class ManifestFreshnessError(ValueError):
    """Raised when a freshness declaration is incomplete or unsafe."""


def _object(value: object, *, source: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ManifestFreshnessError(f"{source} must be a JSON object")
    return cast("dict[str, object]", value)


def _load(path: Path) -> dict[str, object]:
    with path.open(encoding="utf-8") as file:
        return _object(json.load(file), source=path.as_posix())


def _freshness(document: dict[str, object], *, source: str) -> dict[str, object]:
    freshness = _object(document.get("freshness"), source=f"{source}.freshness")
    if freshness.get("schemaVersion") != 1:
        raise ManifestFreshnessError(f"{source}: freshness.schemaVersion must be 1")
    if freshness.get("algorithm") != "sha256":
        raise ManifestFreshnessError(f"{source}: freshness.algorithm must be 'sha256'")
    return freshness


def _input_patterns(freshness: dict[str, object], *, source: str) -> tuple[str, ...]:
    raw_patterns = freshness.get("inputs")
    if not isinstance(raw_patterns, list) or not raw_patterns:
        raise ManifestFreshnessError(
            f"{source}: freshness.inputs must be a non-empty list"
        )
    patterns: list[str] = []
    for raw_pattern in raw_patterns:
        if not isinstance(raw_pattern, str) or not raw_pattern:
            raise ManifestFreshnessError(
                f"{source}: every freshness input must be a non-empty string"
            )
        path = PurePosixPath(raw_pattern)
        if path.is_absolute() or ".." in path.parts:
            raise ManifestFreshnessError(
                f"{source}: freshness inputs must be relative to the Web root"
            )
        patterns.append(raw_pattern)
    if len(patterns) != len(set(patterns)):
        raise ManifestFreshnessError(
            f"{source}: freshness inputs must not contain duplicates"
        )
    return tuple(patterns)


def _matched_files(
    root: Path, patterns: tuple[str, ...], *, source: str
) -> tuple[Path, ...]:
    root = root.resolve()
    matched: set[Path] = set()
    for pattern in patterns:
        candidates = sorted(path for path in root.glob(pattern) if path.is_file())
        if not candidates:
            raise ManifestFreshnessError(
                f"{source}: freshness input {pattern!r} matched no files"
            )
        for candidate in candidates:
            if candidate.is_symlink():
                raise ManifestFreshnessError(
                    f"{source}: freshness input cannot be a symlink: {candidate}"
                )
            try:
                candidate.resolve().relative_to(root)
            except ValueError as error:
                raise ManifestFreshnessError(
                    f"{source}: freshness input escaped the Web root: {candidate}"
                ) from error
            matched.add(candidate)
    return tuple(sorted(matched, key=lambda path: path.relative_to(root).as_posix()))


def _digest(root: Path, paths: tuple[Path, ...]) -> str:
    root = root.resolve()
    digest = hashlib.sha256()
    for path in paths:
        relative = path.relative_to(root).as_posix().encode()
        mode = oct(stat.S_IMODE(path.stat().st_mode)).encode()
        content_hash = hashlib.sha256(path.read_bytes()).hexdigest().encode()
        for field in (relative, mode, content_hash):
            digest.update(len(field).to_bytes(8, "big"))
            digest.update(field)
    return digest.hexdigest()


def _architecture_facts(root: Path) -> dict[str, int]:
    routes = tuple(
        path
        for path in (root / "src" / "routes").rglob("*.tsx")
        if path.is_file() and not path.name.endswith(".test.tsx")
    )
    page_contracts = tuple(
        path
        for path in (root / "docs" / "contracts" / "pages").glob("*.contract.json")
        if path.is_file()
    )

    def public_api_count(parent: Path) -> int:
        if not parent.is_dir():
            return 0
        return sum(
            1
            for child in parent.iterdir()
            if child.is_dir() and (child / "index.ts").is_file()
        )

    return {
        "routeModuleCount": len(routes),
        "pageContractCount": len(page_contracts),
        "featurePublicApiCount": public_api_count(root / "src" / "features"),
        "workflowPublicApiCount": public_api_count(root / "src" / "workflows"),
    }


def _declared_relative_file(root: Path, raw: object, *, source: str) -> Path:
    if not isinstance(raw, str) or not raw:
        raise ManifestFreshnessError(f"{source} must be a non-empty relative path")
    relative = PurePosixPath(raw)
    if relative.is_absolute() or ".." in relative.parts:
        raise ManifestFreshnessError(f"{source} must stay inside the Web root")
    path = root / Path(*relative.parts)
    if path.is_symlink() or not path.is_file():
        raise ManifestFreshnessError(f"{source} does not identify a regular file")
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError as error:
        raise ManifestFreshnessError(f"{source} escaped the Web root") from error
    return path


def _discovery_facts(
    root: Path,
    document: dict[str, object],
    *,
    source: str,
) -> dict[str, int]:
    artifacts = _object(document.get("artifacts"), source=f"{source}.artifacts")
    if not artifacts:
        raise ManifestFreshnessError(f"{source}.artifacts must not be empty")
    for name, raw in artifacts.items():
        _declared_relative_file(root, raw, source=f"{source}.artifacts.{name}")
    source_specs = document.get("sourceSpecs")
    if not isinstance(source_specs, list) or not source_specs:
        raise ManifestFreshnessError(f"{source}.sourceSpecs must be a non-empty list")
    if len(source_specs) != len(set(map(str, source_specs))):
        raise ManifestFreshnessError(
            f"{source}.sourceSpecs must not contain duplicates"
        )
    for index, raw in enumerate(source_specs):
        _declared_relative_file(
            root,
            raw,
            source=f"{source}.sourceSpecs[{index}]",
        )
    return {
        "artifactCount": len(artifacts),
        "sourceSpecCount": len(source_specs),
    }


def _expected_facts(
    root: Path,
    document: dict[str, object],
    *,
    source: str,
) -> dict[str, int]:
    if document.get("schemaVersion") != 1:
        raise ManifestFreshnessError(f"{source}.schemaVersion must be 1")
    kind = document.get("kind")
    if kind == _ARCHITECTURE_KIND:
        return _architecture_facts(root)
    if kind == _DISCOVERY_KIND:
        return _discovery_facts(root, document, source=source)
    raise ManifestFreshnessError(
        f"{source}.kind must be {_ARCHITECTURE_KIND!r} or {_DISCOVERY_KIND!r}"
    )


def _fact_violations(
    document: dict[str, object],
    expected: dict[str, int],
    *,
    source: str,
) -> list[str]:
    actual = _object(document.get("facts"), source=f"{source}.facts")
    violations = [
        f"{source}: facts.{name} must be {value}, found {actual.get(name)!r}"
        for name, value in expected.items()
        if actual.get(name) != value
    ]
    unexpected = sorted(set(actual) - set(expected))
    if unexpected:
        violations.append(f"{source}: facts contains unexpected keys {unexpected!r}")
    return violations


def validate_manifest(root: Path, manifest: Path) -> list[str]:
    """Return violations when a manifest no longer describes its declared inputs."""
    root = root.resolve()
    manifest = manifest.resolve()
    source = manifest.relative_to(root).as_posix()
    document = _load(manifest)
    expected_facts = _expected_facts(root, document, source=source)
    freshness = _freshness(document, source=source)
    patterns = _input_patterns(freshness, source=source)
    files = _matched_files(root, patterns, source=source)
    actual_digest = _digest(root, files)
    violations: list[str] = []
    violations.extend(_fact_violations(document, expected_facts, source=source))
    if freshness.get("digest") != actual_digest:
        violations.append(
            f"{source}: freshness digest does not match declared source inputs"
        )
    if freshness.get("inputCount") != len(files):
        violations.append(
            "".join(
                (
                    f"{source}: freshness inputCount must be {len(files)}, ",
                    f"found {freshness.get('inputCount')!r}",
                )
            )
        )
    return violations


def refresh_manifest(root: Path, manifest: Path) -> None:
    """Update one manifest's content-addressed freshness receipt."""
    root = root.resolve()
    manifest = manifest.resolve()
    source = manifest.relative_to(root).as_posix()
    document = _load(manifest)
    document["facts"] = _expected_facts(root, document, source=source)
    freshness = _freshness(document, source=source)
    patterns = _input_patterns(freshness, source=source)
    files = _matched_files(root, patterns, source=source)
    freshness["inputCount"] = len(files)
    freshness["digest"] = _digest(root, files)
    manifest.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "apps" / "web",
        help="Web root containing the manifests",
    )
    parser.add_argument("--write", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Check or refresh both canonical Web manifests."""
    arguments = _parser().parse_args(argv)
    violations: list[str] = []
    try:
        for name in _DEFAULT_MANIFESTS:
            manifest = arguments.root / name
            if arguments.write:
                refresh_manifest(arguments.root, manifest)
            violations.extend(validate_manifest(arguments.root, manifest))
    except (ManifestFreshnessError, OSError, json.JSONDecodeError) as error:
        sys.stderr.write(f"Web manifest freshness error: {error}\n")
        return 2
    if violations:
        sys.stderr.write("Web manifest freshness violations:\n")
        sys.stderr.write("\n".join(f"- {item}" for item in violations) + "\n")
        return 1
    action = "refreshed" if arguments.write else "current"
    sys.stdout.write(f"Web architecture/discovery manifests are {action}.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
