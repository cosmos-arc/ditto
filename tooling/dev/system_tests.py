#!/usr/bin/env python3
"""Run Playwright against a production Web build and an isolated real API."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from tooling.dev.supervisor import (
    backend_command,
    isolated_runtime_environment,
    service_ports,
    spawn_managed,
    terminate_managed,
    wait_until_listening,
    wait_until_ready,
    write_isolated_data_source_configuration,
)
from tooling.dev.toolchain import node_executable, validate_toolchain

_ISOLATED_OBSERVABILITY_CONFIG = """\
LOG_LEVEL=WARNING
LOG_FORMAT=console
LOG_TO_CONSOLE=true
LOG_TO_FILE=true
TRACING_ENABLED=true
TRACING_EXPORTER=none
TRACING_SAMPLE_RATE=1
METRICS_ENABLED=false
METRICS_EXPORTER=none
VM_ENDPOINT=http://127.0.0.1:9/disabled
"""
_FULL_GIT_SHA_LENGTH = 40


@dataclass(frozen=True, slots=True)
class _FixtureAcceptance:
    command: list[str]
    prefix: str
    spec: str
    web_root: Path | None = None
    web_port: int | None = None


def _cohort_environment(root: Path, *, git_sha: str | None = None) -> dict[str, str]:
    """Resolve one exact build/runtime cohort from tracked root facts."""
    workspace = json.loads((root / "package.json").read_text(encoding="utf-8"))
    if not isinstance(workspace, dict):
        raise ValueError("root package.json must contain an object")
    product_version = workspace.get("version")
    if not isinstance(product_version, str) or not product_version.strip():
        raise ValueError("root package.json must declare a product version")
    if git_sha is None:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            check=False,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError("could not resolve the system-test Git SHA")
        git_sha = result.stdout.strip()
    if len(git_sha) != _FULL_GIT_SHA_LENGTH or any(
        character not in "0123456789abcdef" for character in git_sha
    ):
        raise ValueError(
            "system-test Git SHA must be 40 lowercase hexadecimal characters"
        )
    contract = (root / "contracts" / "openapi" / "v1.json").read_bytes()
    return {
        "DITTO_PRODUCT_VERSION": product_version,
        "DITTO_GIT_SHA": git_sha,
        "DITTO_API_CONTRACT_VERSION": "v1",
        "DITTO_API_CONTRACT_SHA256": hashlib.sha256(contract).hexdigest(),
    }


def _run(command: list[str], root: Path, environment: dict[str, str]) -> None:
    result = subprocess.run(command, cwd=root, env=environment, check=False)
    if result.returncode != 0:
        raise RuntimeError(
            f"command failed with exit code {result.returncode}: {' '.join(command)}"
        )


def _isolated_system_environment(
    root: Path,
    temporary_root: Path,
    api_port: int,
    web_port: int,
    *,
    source: Mapping[str, str] | None = None,
    output_root: Path | None = None,
) -> dict[str, str]:
    environment = isolated_runtime_environment(root, source or os.environ)
    for name, leaf in (
        ("DITTO_CONFIG_ROOT", "config"),
        ("DITTO_STATE_ROOT", "state"),
        ("DITTO_CACHE_ROOT", "cache"),
        ("DITTO_LOG_DIR", "logs"),
    ):
        path = temporary_root / leaf
        path.mkdir(parents=True, exist_ok=True)
        environment[name] = str(path)
    config_file = (
        Path(environment["DITTO_CONFIG_ROOT"])
        / "config"
        / "testing"
        / "observability.env"
    )
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(_ISOLATED_OBSERVABILITY_CONFIG, encoding="utf-8")
    write_isolated_data_source_configuration(
        Path(environment["DITTO_CONFIG_ROOT"]),
        "testing",
    )
    api_origin = f"http://127.0.0.1:{api_port}"
    web_origin = f"http://127.0.0.1:{web_port}"
    browser_output_root = output_root or temporary_root / "browser"
    browser_output_root.mkdir(parents=True, exist_ok=True)
    environment.update(
        {
            "CORS_ORIGINS": web_origin,
            "DITTO_CORS_ORIGINS": web_origin,
            "DITTO_SYSTEM_API_ORIGIN": api_origin,
            "DITTO_SYSTEM_OUTPUT_ROOT": str(browser_output_root),
            "DITTO_SYSTEM_WEB_ORIGIN": web_origin,
            "ENVIRONMENT": "testing",
        }
    )
    # Runtime selection is an external production artifact, never a Vite build
    # switch. Drop inherited legacy values so a caller cannot silently build a
    # mock or remote-API bundle and then claim live system evidence.
    environment.pop("VITE_API_BASE_URL", None)
    environment.pop("VITE_USE_MOCK", None)
    return environment


def _write_runtime_config(web_root: Path, api_port: int) -> None:
    target = web_root / "dist" / "ditto-runtime-config.json"
    target.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "runtime": "live",
                "apiOrigin": f"http://127.0.0.1:{api_port}",
            },
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )


def _preview_command(root: Path, node: str, web_port: int) -> list[str]:
    """Use the already-installed workspace Vite binary without package resolution."""
    return [
        node,
        str(root / "apps" / "web" / "node_modules" / "vite" / "bin" / "vite.js"),
        "preview",
        "--host",
        "127.0.0.1",
        "--port",
        str(web_port),
        "--strictPort",
    ]


def _playwright_command(root: Path, node: str, spec: str) -> list[str]:
    """Use the pinned root Playwright CLI and one explicit lifecycle phase."""
    return [
        node,
        str(root / "node_modules" / "@playwright" / "test" / "cli.js"),
        "test",
        "--config",
        str(root / "tests" / "system" / "playwright.config.ts"),
        spec,
    ]


def _blackhole_command(port: int) -> list[str]:
    """Build a deterministic loopback server command for timeout evidence."""
    return [
        sys.executable,
        str(Path(__file__).with_name("blackhole.py")),
        "--port",
        str(port),
    ]


def _fixture_api_command(target: str, port: int) -> list[str]:
    return [
        sys.executable,
        "-m",
        "ditto_apps.server",
        target,
        "--interface",
        "asgi",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
    ]


def _acceptance_api_command(port: int) -> list[str]:
    """Run the production Agent router over its credential-free SQLite fixture."""
    return _fixture_api_command("tests.system.fixtures.agent_approval_app:app", port)


def _research_acceptance_api_command(port: int) -> list[str]:
    """Run real research and governance handlers over isolated SQLite evidence."""
    return _fixture_api_command("tests.system.fixtures.governed_research_app:app", port)


def _incompatible_cohort_api_command(port: int) -> list[str]:
    """Run a real HTTP peer that truthfully declares an unsupported API major."""
    return _fixture_api_command(
        "tests.system.fixtures.incompatible_cohort_app:app",
        port,
    )


def _run_playwright(
    root: Path,
    node: str,
    spec: str,
    environment: dict[str, str],
) -> None:
    phase_environment = dict(environment)
    output_root = Path(environment["DITTO_SYSTEM_OUTPUT_ROOT"])
    phase_environment["DITTO_SYSTEM_OUTPUT_ROOT"] = str(output_root / Path(spec).stem)
    _run(_playwright_command(root, node, spec), root, phase_environment)


def _spawn_ready(
    command: list[str],
    root: Path,
    environment: dict[str, str],
    *,
    port: int,
    path: str,
    timeout: float,
) -> subprocess.Popen[bytes]:
    process = spawn_managed(command, root, environment)
    try:
        wait_until_ready("127.0.0.1", port, path, process, timeout)
    except BaseException:
        terminate_managed(process)
        raise
    return process


def _run_primary_cohort(
    root: Path,
    web_root: Path,
    node: str,
    api_port: int,
    web_port: int,
    environment: dict[str, str],
) -> None:
    """Exercise one production artifact through normal and failure lifecycles."""
    api_process: subprocess.Popen[bytes] | None = None
    web_process: subprocess.Popen[bytes] | None = None
    try:
        api_process = _spawn_ready(
            backend_command(api_port),
            root,
            environment,
            port=api_port,
            path="/readyz",
            timeout=60,
        )
        web_process = _spawn_ready(
            _preview_command(root, node, web_port),
            web_root,
            environment,
            port=web_port,
            path="/",
            timeout=30,
        )
        _run_playwright(root, node, "cohort.spec.ts", environment)

        # A refused connection proves the built Web does not fall back to mocks.
        terminate_managed(api_process)
        api_process = None
        _run_playwright(root, node, "outage.spec.ts", environment)

        # A connected peer that never produces HTTP bytes separately proves a
        # finite transport deadline.
        api_process = spawn_managed(_blackhole_command(api_port), root, environment)
        try:
            wait_until_listening("127.0.0.1", api_port, api_process, timeout=5)
            _run_playwright(root, node, "timeout.spec.ts", environment)
        finally:
            terminate_managed(api_process)
            api_process = None

        # Use a real ASGI peer with an incompatible declared major; the normal
        # production app intentionally refuses to start with unsupported build
        # metadata, so this fixture is the honest network-boundary test double.
        api_process = _spawn_ready(
            _incompatible_cohort_api_command(api_port),
            root,
            environment,
            port=api_port,
            path="/readyz",
            timeout=60,
        )
        _run_playwright(
            root,
            node,
            "compatibility.spec.ts",
            environment,
        )

        # Restart on the same test-owned state root and prove durable recovery.
        terminate_managed(api_process)
        api_process = _spawn_ready(
            backend_command(api_port),
            root,
            environment,
            port=api_port,
            path="/readyz",
            timeout=60,
        )
        _run_playwright(root, node, "restart.spec.ts", environment)
    finally:
        if api_process is not None:
            terminate_managed(api_process)
        if web_process is not None:
            terminate_managed(web_process)


def _run_fixture_acceptance(
    root: Path,
    node: str,
    api_port: int,
    environment: dict[str, str],
    *,
    acceptance: _FixtureAcceptance,
) -> None:
    """Run one real-router, real-SQLite fixture in a disposable /tmp root."""
    if (acceptance.web_root is None) != (acceptance.web_port is None):
        raise ValueError("fixture Web root and port must be configured together")
    with tempfile.TemporaryDirectory(
        prefix=acceptance.prefix,
        dir="/tmp",
    ) as fixture_root:
        fixture_environment = dict(environment)
        fixture_environment.update(
            {
                "DITTO_ACCEPTANCE_DATA_ROOT": fixture_root,
                "DITTO_ENVIRONMENT": "testing",
            }
        )
        api_process = _spawn_ready(
            acceptance.command,
            root,
            fixture_environment,
            port=api_port,
            path="/healthz",
            timeout=30,
        )
        web_process: subprocess.Popen[bytes] | None = None
        try:
            if acceptance.web_root is not None and acceptance.web_port is not None:
                _write_runtime_config(acceptance.web_root, api_port)
                web_process = _spawn_ready(
                    _preview_command(root, node, acceptance.web_port),
                    acceptance.web_root,
                    fixture_environment,
                    port=acceptance.web_port,
                    path="/",
                    timeout=30,
                )
            _run_playwright(root, node, acceptance.spec, fixture_environment)
        finally:
            if web_process is not None:
                terminate_managed(web_process)
            terminate_managed(api_process)


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    web_root = root / "apps" / "web"
    bun = shutil.which("bun")
    if bun is None:
        print("System tests require Bun.", file=sys.stderr)
        return 1
    try:
        validate_toolchain(root)
        node = node_executable(root)
        api_port, web_port = service_ports(0, 0)
        cache_root = root / ".cache" / "ditto-system"
        cache_root.mkdir(parents=True, exist_ok=True)
        browser_output_root = root / "build" / "system-e2e"
        shutil.rmtree(browser_output_root, ignore_errors=True)
        browser_output_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=cache_root) as temporary:
            environment = _isolated_system_environment(
                root,
                Path(temporary),
                api_port,
                web_port,
                output_root=browser_output_root,
            )
            environment.update(_cohort_environment(root))
            _run([bun, "run", "build"], web_root, environment)
            _write_runtime_config(web_root, api_port)
            _run_primary_cohort(root, web_root, node, api_port, web_port, environment)

            # The normal product profile keeps Agent disabled. This fixture
            # mounts the production router over real SQLite and pre-issued,
            # fictional actions without a model, credentials, or write tool.
            _run_fixture_acceptance(
                root,
                node,
                api_port,
                environment,
                acceptance=_FixtureAcceptance(
                    command=_acceptance_api_command(api_port),
                    prefix="ditto-system-agent-",
                    spec="agent-approval.spec.ts",
                    web_root=web_root,
                    web_port=web_port,
                ),
            )

            # Certified research inputs are deterministic test evidence, while
            # the routers, application handlers, governance state machine, and
            # both persistence stores are the production implementations.
            _run_fixture_acceptance(
                root,
                node,
                api_port,
                environment,
                acceptance=_FixtureAcceptance(
                    command=_research_acceptance_api_command(api_port),
                    prefix="ditto-system-research-",
                    spec="research-governance.spec.ts",
                    web_root=web_root,
                    web_port=web_port,
                ),
            )
    except (OSError, RuntimeError, TimeoutError, ValueError) as error:
        print(f"System tests failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
