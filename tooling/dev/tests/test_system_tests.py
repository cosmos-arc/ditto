from __future__ import annotations

import http.client
import json
from hashlib import sha256
from pathlib import Path

import pytest
from tooling.dev import system_tests
from tooling.dev.supervisor import (
    available_port,
    spawn_managed,
    terminate_managed,
    wait_until_listening,
)
from tooling.dev.system_tests import (
    _acceptance_api_command,
    _blackhole_command,
    _cohort_environment,
    _FixtureAcceptance,
    _incompatible_cohort_api_command,
    _isolated_system_environment,
    _playwright_command,
    _preview_command,
    _research_acceptance_api_command,
    _write_runtime_config,
)


def test_blackhole_phase_is_a_real_socket_timeout_not_a_mock(tmp_path: Path) -> None:
    port = available_port(0)
    process = spawn_managed(_blackhole_command(port), tmp_path, {})
    try:
        wait_until_listening("127.0.0.1", port, process, timeout=5)
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=0.1)
        try:
            connection.request("GET", "/api/v1/status")
            with pytest.raises(TimeoutError):
                connection.getresponse()
        finally:
            connection.close()
    finally:
        terminate_managed(process)
    assert process.poll() is not None


def test_system_commands_use_only_frozen_workspace_binaries(tmp_path: Path) -> None:
    bun = "/toolchain/bun"

    assert _preview_command(tmp_path, bun, web_port=18121) == [
        bun,
        str(tmp_path / "apps" / "web" / "node_modules" / "vite" / "bin" / "vite.js"),
        "preview",
        "--host",
        "127.0.0.1",
        "--port",
        "18121",
        "--strictPort",
    ]
    assert _playwright_command(tmp_path, bun, "cohort.spec.ts") == [
        bun,
        str(tmp_path / "node_modules" / "@playwright" / "test" / "cli.js"),
        "test",
        "--config",
        str(tmp_path / "tests" / "system" / "playwright.config.ts"),
        "cohort.spec.ts",
    ]
    assert _acceptance_api_command(18131)[2:] == [
        "ditto_apps.server",
        "tests.system.fixtures.agent_approval_app:app",
        "--interface",
        "asgi",
        "--host",
        "127.0.0.1",
        "--port",
        "18131",
    ]


def test_agent_fixture_acceptance_serves_the_production_web(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "root"
    web_root = root / "apps" / "web"
    web_root.mkdir(parents=True)
    environment = {"DITTO_SYSTEM_OUTPUT_ROOT": str(tmp_path / "browser")}
    api_process = object()
    web_process = object()
    spawned: list[tuple[list[str], Path, int, str]] = []
    terminated: list[object] = []
    written: list[tuple[Path, int]] = []
    played: list[str] = []

    def fake_spawn(
        command: list[str],
        cwd: Path,
        _environment: dict[str, str],
        *,
        port: int,
        path: str,
        timeout: float,
    ) -> object:
        del timeout
        spawned.append((command, cwd, port, path))
        return api_process if len(spawned) == 1 else web_process

    monkeypatch.setattr(system_tests, "_spawn_ready", fake_spawn)
    monkeypatch.setattr(
        system_tests,
        "_write_runtime_config",
        lambda path, port: written.append((path, port)),
    )
    monkeypatch.setattr(
        system_tests,
        "_run_playwright",
        lambda _root, _bun, spec, _environment: played.append(spec),
    )
    monkeypatch.setattr(system_tests, "terminate_managed", terminated.append)

    system_tests._run_fixture_acceptance(
        root,
        "/toolchain/bun",
        18131,
        environment,
        acceptance=_FixtureAcceptance(
            command=["agent-api"],
            prefix="ditto-system-agent-",
            spec="agent-approval.spec.ts",
            web_root=web_root,
            web_port=18132,
        ),
    )

    assert written == [(web_root, 18131)]
    assert spawned == [
        (["agent-api"], root, 18131, "/healthz"),
        (_preview_command(root, "/toolchain/bun", 18132), web_root, 18132, "/"),
    ]
    assert played == ["agent-approval.spec.ts"]
    assert terminated == [web_process, api_process]
    assert _research_acceptance_api_command(18132)[2:] == [
        "ditto_apps.server",
        "tests.system.fixtures.governed_research_app:app",
        "--interface",
        "asgi",
        "--host",
        "127.0.0.1",
        "--port",
        "18132",
    ]
    assert _incompatible_cohort_api_command(18133)[2:] == [
        "ditto_apps.server",
        "tests.system.fixtures.incompatible_cohort_app:app",
        "--interface",
        "asgi",
        "--host",
        "127.0.0.1",
        "--port",
        "18133",
    ]


def test_cohort_environment_binds_web_and_api_to_the_same_commit(
    tmp_path: Path,
) -> None:
    (tmp_path / "contracts" / "openapi").mkdir(parents=True)
    contract = b'{"openapi":"3.1.0"}\n'
    (tmp_path / "contracts" / "openapi" / "v1.json").write_bytes(contract)
    (tmp_path / "package.json").write_text(
        '{"name":"@ditto/workspace","version":"1.2.3"}\n',
        encoding="utf-8",
    )
    git_sha = "a" * 40

    values = _cohort_environment(tmp_path, git_sha=git_sha)

    assert values == {
        "DITTO_PRODUCT_VERSION": "1.2.3",
        "DITTO_GIT_SHA": git_sha,
        "DITTO_API_CONTRACT_VERSION": "v1",
        "DITTO_API_CONTRACT_SHA256": sha256(contract).hexdigest(),
    }


def test_system_environment_is_live_loopback_without_build_time_api_switches(
    tmp_path: Path,
) -> None:
    root = tmp_path / "worktree"
    runtime = tmp_path / "runtime"
    root.mkdir()
    runtime.mkdir()

    environment = _isolated_system_environment(
        root,
        runtime,
        api_port=18101,
        web_port=18102,
        source={
            "PATH": "/usr/bin",
            "VITE_API_BASE_URL": "https://remote.invalid/api",
            "VITE_USE_MOCK": "true",
            "OPENAI_API_KEY": "secret",
            "DATA_ROOT": "/real/user/data",
            "DITTO_DATA_ROOT": "/real/user/state",
            "DITTO_TRADING_SQLITE_PATH": "/real/user/trading.sqlite",
            "DUCKDB_PATH": "/real/user/market.duckdb",
            "LOG_DIR": "/real/user/logs",
            "SQLITE_PATH": "/real/user/metadata.sqlite",
        },
    )

    assert environment["DITTO_SYSTEM_API_ORIGIN"] == "http://127.0.0.1:18101"
    assert environment["DITTO_SYSTEM_WEB_ORIGIN"] == "http://127.0.0.1:18102"
    assert environment["DITTO_CORS_ORIGINS"] == "http://127.0.0.1:18102"
    assert environment["ENVIRONMENT"] == "testing"
    assert "VITE_API_BASE_URL" not in environment
    assert "VITE_USE_MOCK" not in environment
    assert "OPENAI_API_KEY" not in environment
    for name in (
        "DATA_ROOT",
        "DITTO_DATA_ROOT",
        "DITTO_TRADING_SQLITE_PATH",
        "DUCKDB_PATH",
        "LOG_DIR",
        "SQLITE_PATH",
    ):
        assert name not in environment
    assert environment["PYTHON_KEYRING_BACKEND"] == "keyring.backends.null.Keyring"
    assert environment["OTEL_SDK_DISABLED"] == "false"
    for name in ("DITTO_CONFIG_ROOT", "DITTO_STATE_ROOT", "DITTO_CACHE_ROOT"):
        assert Path(environment[name]).is_relative_to(runtime)
    observability = (
        Path(environment["DITTO_CONFIG_ROOT"])
        / "config"
        / "testing"
        / "observability.env"
    ).read_text(encoding="utf-8")
    assert "TRACING_ENABLED=true" in observability
    assert "TRACING_EXPORTER=none" in observability
    assert "METRICS_ENABLED=false" in observability
    data_source = (
        Path(environment["DITTO_CONFIG_ROOT"])
        / "config"
        / "testing"
        / "data_source.env"
    ).read_text(encoding="utf-8")
    assert "TUSHARE_TOKEN=ditto-isolated-placeholder" in data_source
    assert "HTTP_BASE_URL=http://127.0.0.1:9/disabled" in data_source


def test_system_environment_keeps_browser_evidence_outside_ephemeral_state(
    tmp_path: Path,
) -> None:
    root = tmp_path / "worktree"
    runtime = tmp_path / "runtime"
    evidence = root / "build" / "system-e2e"
    root.mkdir()
    runtime.mkdir()

    environment = _isolated_system_environment(
        root,
        runtime,
        api_port=18101,
        web_port=18102,
        source={"PATH": "/usr/bin"},
        output_root=evidence,
    )

    assert environment["DITTO_SYSTEM_OUTPUT_ROOT"] == str(evidence)
    assert not evidence.is_relative_to(runtime)


def test_runtime_config_uses_the_validated_production_schema(tmp_path: Path) -> None:
    web_root = tmp_path / "web"
    (web_root / "dist").mkdir(parents=True)

    _write_runtime_config(web_root, api_port=18111)

    payload = json.loads(
        (web_root / "dist" / "ditto-runtime-config.json").read_text(encoding="utf-8")
    )
    assert payload == {
        "schemaVersion": 1,
        "runtime": "live",
        "apiOrigin": "http://127.0.0.1:18111",
    }


@pytest.mark.parametrize(
    "field",
    [None, "gitSha", "productVersion", "apiContractVersion", "apiContractSha256"],
)
def test_reused_production_build_requires_exact_cohort(
    tmp_path: Path, field: str | None
) -> None:
    from tooling.dev.system_tests import _verify_reused_web_build

    environment = {
        "DITTO_GIT_SHA": "a" * 40,
        "DITTO_PRODUCT_VERSION": "1.0.0",
        "DITTO_API_CONTRACT_VERSION": "v1",
        "DITTO_API_CONTRACT_SHA256": "b" * 64,
    }
    metadata = {
        "gitSha": "a" * 40,
        "productVersion": "1.0.0",
        "apiContractVersion": "v1",
        "apiContractSha256": "b" * 64,
    }
    if field:
        metadata[field] = "stale"
    dist = tmp_path / "apps/web/dist"
    dist.mkdir(parents=True)
    (dist / "ditto-build-metadata.json").write_text(json.dumps(metadata))
    if field:
        with pytest.raises(ValueError, match="current cohort"):
            _verify_reused_web_build(tmp_path, environment)
    else:
        _verify_reused_web_build(tmp_path, environment)
