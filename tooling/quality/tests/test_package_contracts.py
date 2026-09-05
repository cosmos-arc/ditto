from pathlib import Path

import pytest
import yaml

from tooling.quality.package_contracts import validate_workspace


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    _write(
        tmp_path / "pyproject.toml",
        """\
[project]
name = "ditto-workspace"
version = "1.2.3"
requires-python = ">=3.13,<3.14"
""",
    )
    _write(
        tmp_path / "pixi.toml",
        """\
[workspace]
name = "ditto"
version = "1.2.3"

[dependencies]
python = "3.13.*"
pydantic = ">=2,<3"

[pypi-dependencies]
ditto-kernel = { path = "packages/kernel", editable = true }
ditto-apps = { path = "apps/backend", editable = true }
""",
    )
    _write(
        tmp_path / "package.json",
        '{"name":"@ditto/workspace","version":"1.2.3","private":true}\n',
    )
    _write(
        tmp_path / "apps/web/package.json",
        '{"name":"@ditto/web","version":"1.2.3","private":true}\n',
    )
    _write(
        tmp_path / "packages/kernel/pyproject.toml",
        """\
[project]
name = "ditto-kernel"
version = "1.2.3"
requires-python = ">=3.13"
""",
    )
    _write(
        tmp_path / "apps/backend/pyproject.toml",
        """\
[project]
name = "ditto-apps"
version = "1.2.3"
requires-python = ">=3.13"
dependencies = ["ditto-kernel", "pydantic>=2.10"]
""",
    )
    lock = {
        "version": 6,
        "packages": [
            {"pypi": "./packages/kernel", "name": "ditto-kernel"},
            {"pypi": "./apps/backend", "name": "ditto-apps"},
            {
                "conda": "https://example.invalid/pydantic.conda",
                "name": "pydantic",
                "version": "2.11.0",
            },
        ],
    }
    _write(tmp_path / "pixi.lock", yaml.safe_dump(lock, sort_keys=False))
    return tmp_path


def test_valid_workspace_has_no_contract_violations(workspace: Path) -> None:
    assert validate_workspace(workspace, expected_local_count=2) == []


def test_reports_product_version_drift(workspace: Path) -> None:
    leaf = workspace / "packages/kernel/pyproject.toml"
    leaf.write_text(leaf.read_text().replace('version = "1.2.3"', 'version = "9.9.9"'))

    violations = validate_workspace(workspace, expected_local_count=2)

    assert any("packages/kernel" in item and "version" in item for item in violations)


@pytest.mark.parametrize("manifest", ["package.json", "apps/web/package.json"])
def test_reports_javascript_product_version_drift(
    workspace: Path,
    manifest: str,
) -> None:
    path = workspace / manifest
    path.write_text(path.read_text().replace('"version":"1.2.3"', '"version":"9.9.9"'))

    violations = validate_workspace(workspace, expected_local_count=2)

    assert any(manifest in item and "product version" in item for item in violations)


def test_reports_missing_root_and_lock_path(workspace: Path) -> None:
    pixi = workspace / "pixi.toml"
    pixi.write_text(
        pixi.read_text().replace(
            'ditto-kernel = { path = "packages/kernel", editable = true }\n', ""
        )
    )

    violations = validate_workspace(workspace, expected_local_count=2)

    assert any(
        "pypi-dependencies" in item and "packages/kernel" in item for item in violations
    )


def test_reports_resolved_dependency_outside_leaf_constraint(workspace: Path) -> None:
    backend = workspace / "apps/backend/pyproject.toml"
    backend.write_text(backend.read_text().replace("pydantic>=2.10", "pydantic>=3"))

    violations = validate_workspace(workspace, expected_local_count=2)

    assert any("pydantic>=3" in item and "2.11.0" in item for item in violations)
