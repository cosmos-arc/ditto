from pathlib import Path

import pytest

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
dependencies = ["pydantic>=2,<3"]
[tool.uv.workspace]
members = ["packages/kernel", "apps/backend"]
[tool.uv.sources]
ditto-kernel = { workspace = true }
ditto-apps = { workspace = true }
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
    _write(
        tmp_path / "uv.lock",
        """
[[package]]
name = "ditto-kernel"
version = "1.2.3"
source = { editable = "packages/kernel" }
[[package]]
name = "ditto-apps"
version = "1.2.3"
source = { editable = "apps/backend" }
[[package]]
name = "pydantic"
version = "2.11.0"
source = { registry = "https://pypi.org/simple" }
""",
    )
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
    manifest = workspace / "pyproject.toml"
    manifest.write_text(
        manifest.read_text().replace("ditto-kernel = { workspace = true }\n", "")
    )

    violations = validate_workspace(workspace, expected_local_count=2)

    assert any(
        "tool.uv.sources" in item and "packages/kernel" in item for item in violations
    )


def test_reports_resolved_dependency_outside_leaf_constraint(workspace: Path) -> None:
    backend = workspace / "apps/backend/pyproject.toml"
    backend.write_text(backend.read_text().replace("pydantic>=2.10", "pydantic>=3"))

    violations = validate_workspace(workspace, expected_local_count=2)

    assert any("pydantic>=3" in item and "2.11.0" in item for item in violations)
