"""OpenAPI 快照集成用例（自 unit 目录按性质归位 integration，2026-09-27）。"""

from __future__ import annotations

import stat
from pathlib import Path

import pytest
from apps.backend.tests.unit.api.test_openapi_snapshot_unit import (
    _DEBUG_PATH,
    _SNAPSHOT_PATH,
    exporter,
)
from ditto_apps.openapi_contract import canonical_openapi_bytes, create_openapi_app


@pytest.mark.integration  # 集成性质(真入口/容器/子进程/重数据), 2026-09-27 分层归位
@pytest.mark.slow  # CI 实测超集成预算(2026-09-27 CI 9-13s), 进慢车道
def test_static_openapi_matches_canonical_runtime_contract() -> None:
    """Static OpenAPI is exactly the exporter's runtime projection."""
    expected = exporter.canonical_runtime_openapi_bytes()

    assert _SNAPSHOT_PATH.read_bytes() == expected
    assert _DEBUG_PATH not in exporter.runtime_openapi_schema()["paths"]


@pytest.mark.integration  # 集成性质(真入口/容器/子进程/重数据), 2026-09-27 分层归位
@pytest.mark.slow  # CI 实测超集成预算(2026-09-27 CI 9-13s), 进慢车道
def test_exporter_writes_canonical_bytes_through_real_entrypoint(
    tmp_path: Path,
) -> None:
    """The production exporter writes the same canonical contract to any target."""
    output_path = tmp_path / "nested" / "v1.json"

    exported_path = exporter.export_openapi(output_path)

    expected = exporter.canonical_runtime_openapi_bytes()
    assert exported_path == output_path
    assert output_path.read_bytes() == expected
    assert stat.S_IMODE(output_path.stat().st_mode) == 0o644


@pytest.mark.integration  # 集成性质(真入口/容器/子进程/重数据), 2026-09-27 分层归位
@pytest.mark.slow  # CI 实测超集成预算(2026-09-27 CI 9-13s), 进慢车道
def test_factory_debug_surface_is_explicit_and_environment_independent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ENVIRONMENT cannot alter the canonical app; only include_debug can."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    production_named = create_openapi_app(include_debug=False)
    monkeypatch.setenv("ENVIRONMENT", "testing")
    testing_named = create_openapi_app(include_debug=False)
    debug_app = create_openapi_app(include_debug=True)

    assert canonical_openapi_bytes(
        production_named.openapi()
    ) == canonical_openapi_bytes(testing_named.openapi())
    assert _DEBUG_PATH not in production_named.openapi()["paths"]
    assert _DEBUG_PATH not in testing_named.openapi()["paths"]
    assert _DEBUG_PATH in debug_app.openapi()["paths"]
    assert not hasattr(production_named.state, "dishka_container")
