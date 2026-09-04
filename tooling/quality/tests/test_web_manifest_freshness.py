import json
from pathlib import Path

import pytest

from tooling.quality.web_manifest_freshness import (
    ManifestFreshnessError,
    refresh_manifest,
    validate_manifest,
)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


@pytest.fixture
def web_root(tmp_path: Path) -> Path:
    _write(tmp_path / "PRODUCT.md", "product\n")
    _write(tmp_path / "src/routes/index.tsx", "export const route = '/';\n")
    _write(
        tmp_path / ".arch-manifest.json",
        json.dumps(
            {
                "version": 1,
                "status": "completed",
                "freshness": {
                    "schemaVersion": 1,
                    "algorithm": "sha256",
                    "inputs": ["PRODUCT.md", "src/routes/**/*.tsx"],
                    "digest": "stale",
                },
            }
        ),
    )
    return tmp_path


def test_refresh_then_validate_is_zero_diff(web_root: Path) -> None:
    manifest = web_root / ".arch-manifest.json"

    refresh_manifest(web_root, manifest)

    assert validate_manifest(web_root, manifest) == []


def test_content_change_invalidates_manifest(web_root: Path) -> None:
    manifest = web_root / ".arch-manifest.json"
    refresh_manifest(web_root, manifest)
    _write(web_root / "PRODUCT.md", "changed\n")

    violations = validate_manifest(web_root, manifest)

    assert any("digest" in violation for violation in violations)


def test_new_globbed_file_invalidates_manifest(web_root: Path) -> None:
    manifest = web_root / ".arch-manifest.json"
    refresh_manifest(web_root, manifest)
    _write(web_root / "src/routes/new.tsx", "export const route = '/new';\n")

    assert validate_manifest(web_root, manifest)


def test_missing_glob_match_fails_closed(web_root: Path) -> None:
    manifest = web_root / ".arch-manifest.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["freshness"]["inputs"] = ["missing/**/*.json"]
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ManifestFreshnessError, match="matched no files"):
        refresh_manifest(web_root, manifest)


@pytest.mark.parametrize("unsafe", ["../outside", "/absolute/path"])
def test_inputs_cannot_escape_web_root(web_root: Path, unsafe: str) -> None:
    manifest = web_root / ".arch-manifest.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["freshness"]["inputs"] = [unsafe]
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ManifestFreshnessError, match="relative"):
        validate_manifest(web_root, manifest)
