#!/usr/bin/env python3
"""Start and supervise an isolated API and Web development pair."""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from types import FrameType
from typing import Final

from ditto_apps.api.app_metadata import SUPPORTED_API_CONTRACT_VERSION

from tooling.dev.toolchain import node_executable

SECRET_NAMES = {
    "ANTHROPIC_API_KEY",
    "AWS_SECRET_ACCESS_KEY",
    "DATABASE_PASSWORD",
    "DATABASE_URL",
    "DEEPSEEK_API_KEY",
    "FRED_API_KEY",
    "GH_TOKEN",
    "GITHUB_TOKEN",
    "OPENAI_API_KEY",
    "SENTRY_DSN",
    "TUSHARE_TOKEN",
}
SECRET_NAME_FRAGMENTS: Final = (
    "CREDENTIAL",
    "PASSWORD",
    "PRIVATE_KEY",
    "SECRET",
)
LEGACY_RUNTIME_PATH_NAMES: Final = frozenset(
    {
        "DATA_ROOT",
        "DITTO_BASE_DIR",
        "DITTO_DATA_ROOT",
        "DITTO_RUNTIME_DIR",
        "DITTO_TRADING_SQLITE_PATH",
        "DUCKDB_PATH",
        "LOG_DIR",
        "SQLITE_PATH",
    }
)
HTTP_OK = 200
_MAX_PORT_SELECTION_ATTEMPTS = 32
_PROCESS_GROUP_GRACE_SECONDS = 5.0
_PROCESS_GROUP_KILL_WAIT_SECONDS = 5.0
_PROCESS_GROUP_POLL_SECONDS = 0.05
_FULL_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
type SignalHandler = (
    Callable[[int, FrameType | None], object] | int | signal.Handlers | None
)
_ISOLATED_OBSERVABILITY_CONFIG = """\
LOG_LEVEL=INFO
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
_ISOLATED_DATA_SOURCE_CONFIG = """\
TUSHARE_TOKEN=ditto-isolated-placeholder
FRED_API_KEY=
HTTP_BASE_URL=http://127.0.0.1:9/disabled
HTTP_TIMEOUT=1.0
RETRY_MAX_ATTEMPTS=1
RETRY_MULTIPLIER=1.0
RETRY_MIN_WAIT=0.1
RETRY_MAX_WAIT=1.0
RATE_LIMIT_PROFILE=free
TDX_PATH={tdx_path}
"""


class ShutdownRequested(Exception):
    """Internal control flow for a shell signal requesting orderly cleanup."""

    def __init__(self, signal_number: int) -> None:
        super().__init__(f"shutdown requested by signal {signal_number}")
        self.signal_number = signal_number


def _is_sensitive_environment_name(name: str) -> bool:
    normalized = name.upper()
    return (
        normalized in SECRET_NAMES
        or normalized.endswith("_API_KEY")
        or normalized.endswith("_TOKEN")
        or any(fragment in normalized for fragment in SECRET_NAME_FRAGMENTS)
    )


def write_isolated_data_source_configuration(
    config_root: Path,
    environment_name: str,
) -> None:
    """Write a startup-valid provider config that cannot reach real data."""
    target = config_root / "config" / environment_name / "data_source.env"
    target.parent.mkdir(parents=True, exist_ok=True)
    tdx_path = config_root / "unavailable-tdx"
    target.write_text(
        _ISOLATED_DATA_SOURCE_CONFIG.format(tdx_path=tdx_path),
        encoding="utf-8",
    )


def isolated_runtime_environment(
    workspace_root: Path, source: Mapping[str, str]
) -> dict[str, str]:
    """Create one credential-free mutable runtime root per Git worktree."""
    resolved = workspace_root.resolve()
    identity = hashlib.sha256(os.fsencode(resolved)).hexdigest()[:12]
    runtime_root = resolved / ".cache" / "ditto-dev" / identity
    roots = {
        "DITTO_CONFIG_ROOT": runtime_root / "config",
        "DITTO_STATE_ROOT": runtime_root / "state",
        "DITTO_CACHE_ROOT": runtime_root / "cache",
        "DITTO_LOG_DIR": runtime_root / "logs",
    }
    for path in roots.values():
        path.mkdir(parents=True, exist_ok=True)

    environment = {
        key: value
        for key, value in source.items()
        if not _is_sensitive_environment_name(key)
        and key not in LEGACY_RUNTIME_PATH_NAMES
    }
    environment.update({key: str(value) for key, value in roots.items()})
    environment.update(
        {
            "DITTO_ALLOW_REAL_DATA": "0",
            "DITTO_RUNTIME_PROFILE": "development-isolated",
            "ENVIRONMENT": "development",
            # Export is disabled in the local config, but the SDK remains active
            # so every response still receives a correlation trace identifier.
            "OTEL_SDK_DISABLED": "false",
            "PYTHON_KEYRING_BACKEND": "keyring.backends.null.Keyring",
            "PYTHONUNBUFFERED": "1",
        }
    )
    environment.pop("VITE_API_BASE_URL", None)
    environment.pop("VITE_USE_MOCK", None)
    config_file = (
        roots["DITTO_CONFIG_ROOT"] / "config" / "development" / "observability.env"
    )
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(_ISOLATED_OBSERVABILITY_CONFIG, encoding="utf-8")
    write_isolated_data_source_configuration(
        roots["DITTO_CONFIG_ROOT"],
        "development",
    )
    return environment


def _git_head_sha(workspace_root: Path) -> str:
    """Read one full immutable commit identity from the development checkout."""
    git = shutil.which("git")
    if git is None:
        raise RuntimeError("Git is unavailable for development cohort metadata")
    result = subprocess.run(
        [git, "rev-parse", "--verify", "HEAD^{commit}"],
        cwd=workspace_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or "no diagnostic output"
        raise RuntimeError(f"could not resolve development Git HEAD: {detail}")
    git_sha = result.stdout.strip()
    if _FULL_GIT_SHA.fullmatch(git_sha) is None:
        raise RuntimeError("development Git HEAD is not a full lowercase commit hash")
    return git_sha


def _workspace_product_version(workspace_root: Path) -> str:
    manifest_path = workspace_root / "package.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(
            f"could not read workspace product version from {manifest_path}"
        ) from error
    if not isinstance(manifest, dict):
        raise RuntimeError("workspace package.json must contain a JSON object")
    product_version = manifest.get("version")
    if not isinstance(product_version, str) or not product_version.strip():
        raise RuntimeError("workspace package.json must declare a product version")
    return product_version.strip()


def development_cohort_environment(workspace_root: Path) -> dict[str, str]:
    """Derive one exact cohort shared by both supervised development services."""
    contract_path = workspace_root / "contracts" / "openapi" / "v1.json"
    try:
        contract_bytes = contract_path.read_bytes()
    except OSError as error:
        raise RuntimeError(
            f"could not read canonical OpenAPI contract from {contract_path}"
        ) from error
    return {
        "DITTO_PRODUCT_VERSION": _workspace_product_version(workspace_root),
        "DITTO_GIT_SHA": _git_head_sha(workspace_root),
        "DITTO_API_CONTRACT_VERSION": SUPPORTED_API_CONTRACT_VERSION,
        "DITTO_API_CONTRACT_SHA256": hashlib.sha256(contract_bytes).hexdigest(),
    }


def available_port(requested: int) -> int:
    """Return an explicit port or ask the kernel for a loopback-only free port."""
    if requested:
        return requested
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def service_ports(requested_api: int, requested_web: int) -> tuple[int, int]:
    """Resolve distinct API/Web ports or reject an explicit collision."""
    if requested_api and requested_api == requested_web:
        raise ValueError("explicit API and Web ports must differ")
    api_port = available_port(requested_api)
    for _attempt in range(_MAX_PORT_SELECTION_ATTEMPTS):
        web_port = available_port(requested_web)
        if web_port != api_port:
            return api_port, web_port
        if requested_web:
            break
    raise RuntimeError("could not allocate distinct API and Web ports")


def wait_until_ready(
    host: str,
    port: int,
    path: str,
    process: subprocess.Popen[bytes],
    timeout: float,
) -> None:
    url = f"http://{host}:{port}{path}"
    deadline = time.monotonic() + timeout
    last_error = "not attempted"
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                f"process exited with {process.returncode} before readiness: {url}"
            )
        try:
            connection = http.client.HTTPConnection(host, port, timeout=0.5)
            try:
                connection.request("GET", path)
                response = connection.getresponse()
                if response.status == HTTP_OK:
                    return
                last_error = f"HTTP {response.status}"
            finally:
                connection.close()
        except (OSError, http.client.HTTPException) as error:
            last_error = str(error)
        time.sleep(0.1)
    raise TimeoutError(f"readiness timed out for {url}: {last_error}")


def wait_until_listening(
    host: str,
    port: int,
    process: subprocess.Popen[bytes],
    timeout: float,
) -> None:
    """Wait until a child owns a TCP port without requiring an HTTP response."""
    deadline = time.monotonic() + timeout
    last_error = "not attempted"
    while time.monotonic() < deadline:
        if process.poll() is not None:
            status = process.returncode
            raise RuntimeError(f"process {status} exited before {host}:{port} listened")
        try:
            with socket.create_connection((host, port), timeout=0.2):
                return
        except OSError as error:
            last_error = str(error)
        time.sleep(0.05)
    raise TimeoutError(f"listener timed out for {host}:{port}: {last_error}")


def spawn_managed(
    command: list[str], root: Path, environment: Mapping[str, str]
) -> subprocess.Popen[bytes]:
    if os.name == "nt":
        return subprocess.Popen(
            command,
            cwd=root,
            env=environment,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )
    return subprocess.Popen(command, cwd=root, env=environment, start_new_session=True)


def _process_group_exists(process_group: int) -> bool:
    try:
        os.killpg(process_group, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Darwin can report EPERM for a just-terminated session while its
        # leader is being reaped. Every managed group is created by this
        # process under the same user, so EPERM cannot identify a live child
        # that this supervisor is capable of signalling.
        return False
    return True


def _wait_for_process_group_exit(process_group: int, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while _process_group_exists(process_group):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        time.sleep(min(_PROCESS_GROUP_POLL_SECONDS, remaining))
    return True


def _resolve_windows_taskkill(environment: Mapping[str, str]) -> Path:
    system_root_raw = environment.get("SystemRoot") or environment.get("WINDIR")
    if (
        system_root_raw is None
        or not system_root_raw.strip()
        or "\0" in system_root_raw
    ):
        raise RuntimeError("Windows SystemRoot is unavailable for process-tree cleanup")
    system_root = Path(system_root_raw)
    if not system_root.is_absolute():
        raise RuntimeError("Windows SystemRoot must be an absolute path")
    try:
        system32 = (system_root / "System32").resolve(strict=True)
        taskkill = (system32 / "taskkill.exe").resolve(strict=True)
    except OSError as error:
        raise RuntimeError(
            "Windows system taskkill.exe is unavailable for process-tree cleanup"
        ) from error
    if taskkill.parent != system32 or not taskkill.is_file():
        raise RuntimeError("taskkill.exe is not the trusted System32 executable")
    return taskkill


def _terminate_windows_process_tree(process: subprocess.Popen[bytes]) -> None:
    process_id = process.pid
    if (
        isinstance(process_id, bool)
        or not isinstance(process_id, int)
        or process_id <= 0
    ):
        raise RuntimeError(f"unsafe Windows process identifier: {process_id!r}")
    taskkill = _resolve_windows_taskkill(os.environ)
    command = [str(taskkill), "/PID", str(process_id), "/T", "/F"]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        detail = "\n".join(
            output.strip()
            for output in (result.stdout, result.stderr)
            if output.strip()
        )
        if not detail:
            detail = "no diagnostic output"
        raise RuntimeError(
            f"taskkill failed for process tree {process_id} "
            + f"with exit code {result.returncode}: {detail}"
        )
    try:
        process.wait(timeout=_PROCESS_GROUP_KILL_WAIT_SECONDS)
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(
            f"process tree {process_id} remained live after successful taskkill"
        ) from error


def terminate_managed(process: subprocess.Popen[bytes]) -> None:
    if os.name == "nt":
        _terminate_windows_process_tree(process)
        return

    # ``start_new_session=True`` makes the leader PID the process-group ID. A
    # finished leader is not evidence that its descendants exited: they may
    # ignore SIGTERM and continue holding ports or inherited pipes.
    process_group = process.pid
    try:
        os.killpg(process_group, signal.SIGTERM)
    except ProcessLookupError:
        return
    if not _wait_for_process_group_exit(process_group, _PROCESS_GROUP_GRACE_SECONDS):
        try:
            os.killpg(process_group, signal.SIGKILL)
        except ProcessLookupError:
            pass
        if not _wait_for_process_group_exit(
            process_group, _PROCESS_GROUP_KILL_WAIT_SECONDS
        ):
            raise RuntimeError(
                f"process group {process_group} survived SIGKILL during cleanup"
            )
    if process.poll() is None:
        process.wait(timeout=_PROCESS_GROUP_KILL_WAIT_SECONDS)


def backend_command(api_port: int) -> list[str]:
    """Build the isolated single-process API command."""
    return [
        sys.executable,
        "-m",
        "ditto_apps.server",
        "ditto_apps.main:app",
        "--interface",
        "asgi",
        "--host",
        "127.0.0.1",
        "--port",
        str(api_port),
    ]


def development_commands(
    root: Path, api_port: int, web_port: int
) -> tuple[list[str], list[str]]:
    """Build the API and Vite commands for interactive development."""
    api = backend_command(api_port)
    web = [
        node_executable(root),
        str(root / "apps/web/node_modules/vite/bin/vite.js"),
        "--host",
        "127.0.0.1",
        "--port",
        str(web_port),
        "--strictPort",
    ]
    return api, web


def supervise(root: Path, api_port: int, web_port: int, timeout: float) -> int:
    """Run both services until interrupted or either child exits."""
    environment = isolated_runtime_environment(root, os.environ)
    environment.update(development_cohort_environment(root))
    environment["DITTO_API_ORIGIN"] = f"http://127.0.0.1:{api_port}"
    environment["VITE_DEV_API_TARGET"] = f"http://127.0.0.1:{api_port}"
    web_origin = f"http://127.0.0.1:{web_port}"
    environment["CORS_ORIGINS"] = web_origin
    environment["DITTO_CORS_ORIGINS"] = web_origin
    api_command, web_command = development_commands(root, api_port, web_port)
    processes: list[subprocess.Popen[bytes]] = []
    previous_handlers: dict[int, SignalHandler] = {}

    def request_shutdown(signal_number: int, _frame: FrameType | None) -> None:
        raise ShutdownRequested(signal_number)

    try:
        for signal_number in (signal.SIGINT, signal.SIGTERM):
            previous_handlers[signal_number] = signal.getsignal(signal_number)
            signal.signal(signal_number, request_shutdown)

        # Append one-by-one inside the cleanup boundary. A failed second spawn must
        # not orphan the already-running API process group.
        processes.append(spawn_managed(api_command, root, environment))
        processes.append(spawn_managed(web_command, root, environment))
        wait_until_ready("127.0.0.1", api_port, "/readyz", processes[0], timeout)
        wait_until_ready("127.0.0.1", web_port, "/", processes[1], timeout)
        api_url = f"http://127.0.0.1:{api_port}"
        web_url = f"http://127.0.0.1:{web_port}"
        print(f"Ditto ready: API {api_url}, Web {web_url}")
        while True:
            exited = [process for process in processes if process.poll() is not None]
            if exited:
                return next((process.returncode or 1 for process in exited), 1)
            time.sleep(0.2)
    except ShutdownRequested as request:
        return 128 + request.signal_number
    except KeyboardInterrupt:
        return 130
    finally:
        for process in reversed(processes):
            terminate_managed(process)
        for signal_number, previous in previous_handlers.items():
            signal.signal(signal_number, previous)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-port", type=int, default=0)
    parser.add_argument("--web-port", type=int, default=0)
    parser.add_argument("--readiness-timeout", type=float, default=60.0)
    arguments = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    api_port, web_port = service_ports(arguments.api_port, arguments.web_port)
    return supervise(root, api_port, web_port, arguments.readiness_timeout)


if __name__ == "__main__":
    raise SystemExit(main())
