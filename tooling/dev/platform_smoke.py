#!/usr/bin/env python3
"""Start the real loopback API, verify operational endpoints, then clean up."""

from __future__ import annotations

import argparse
import http.client
import json
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from ditto_apps.api.app_metadata import BuildMetadata

from tooling.dev.supervisor import (
    available_port,
    backend_command,
    development_cohort_environment,
    isolated_runtime_environment,
    spawn_managed,
    terminate_managed,
    wait_until_ready,
)

_HOST = "127.0.0.1"
_REQUIRED_READY_CHECKS = frozenset(
    {"startup", "config_root", "state_root", "cache_root"}
)
_STATUS_COHORT_FIELDS = {
    "product_version": "DITTO_PRODUCT_VERSION",
    "git_sha": "DITTO_GIT_SHA",
    "api_contract_version": "DITTO_API_CONTRACT_VERSION",
    "api_contract_sha256": "DITTO_API_CONTRACT_SHA256",
}


def fetch_json(host: str, port: int, path: str, timeout: float) -> dict[str, object]:
    """Fetch one successful JSON object from the already-ready local API."""
    connection = http.client.HTTPConnection(host, port, timeout=timeout)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        body = response.read()
        if response.status != http.client.OK:
            raise RuntimeError(f"{path} returned HTTP {response.status}")
    except (OSError, http.client.HTTPException) as error:
        raise RuntimeError(f"could not query {path}: {error}") from error
    finally:
        connection.close()

    try:
        parsed = cast(object, json.loads(body))
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise RuntimeError(f"{path} did not return valid JSON") from error
    if not isinstance(parsed, dict) or not all(isinstance(key, str) for key in parsed):
        raise RuntimeError(f"{path} must return a JSON object with string keys")
    return cast(dict[str, object], parsed)


def validate_payload(
    path: str,
    payload: Mapping[str, object],
    cohort: Mapping[str, str],
) -> None:
    """Fail closed unless an operational response proves the expected state."""
    if path == "/healthz":
        _validate_health(payload)
        return

    if path == "/readyz":
        _validate_readiness(payload)
        return

    if path == "/api/v1/status":
        _validate_status(payload, cohort)
        return

    raise RuntimeError(f"unsupported platform smoke endpoint: {path}")


def _validate_health(payload: Mapping[str, object]) -> None:
    if payload.get("status") != "ok":
        raise RuntimeError("/healthz must report status='ok'")
    if payload.get("service") != "ditto-api":
        raise RuntimeError("/healthz must report service='ditto-api'")


def _validate_readiness(payload: Mapping[str, object]) -> None:
    if payload.get("status") != "ready":
        raise RuntimeError("/readyz must report status='ready'")
    if payload.get("service") != "ditto-api":
        raise RuntimeError("/readyz must report service='ditto-api'")
    raw_checks = payload.get("checks")
    checks = raw_checks if isinstance(raw_checks, dict) else {}
    successful = {
        name
        for name, raw_check in checks.items()
        if isinstance(name, str)
        and isinstance(raw_check, dict)
        and raw_check.get("ok") is True
    }
    missing = sorted(_REQUIRED_READY_CHECKS - successful)
    if missing:
        raise RuntimeError(f"/readyz missing successful checks: {missing}")


def _validate_status(payload: Mapping[str, object], cohort: Mapping[str, str]) -> None:
    if payload.get("status") != "running":
        raise RuntimeError("/api/v1/status must report status='running'")
    mismatches = {
        response_name: {
            "expected": cohort.get(environment_name),
            "actual": payload.get(response_name),
        }
        for response_name, environment_name in _STATUS_COHORT_FIELDS.items()
        if payload.get(response_name) != cohort.get(environment_name)
    }
    if mismatches:
        raise RuntimeError(f"/api/v1/status cohort metadata mismatch: {mismatches}")


def run_platform_smoke(workspace_root: Path, *, timeout: float = 60.0) -> None:
    """Run one isolated API lifecycle and prove liveness, readiness, and cohort."""
    if timeout <= 0:
        raise ValueError("timeout must be positive")
    root = workspace_root.resolve(strict=True)
    cohort = development_cohort_environment(root)
    contract_sha256 = cohort["DITTO_API_CONTRACT_SHA256"]
    BuildMetadata.from_environment(
        cohort,
        generated_contract_sha256=contract_sha256,
        production=True,
    )
    port = available_port(0)

    with tempfile.TemporaryDirectory(prefix="ditto-platform-smoke-") as temporary:
        environment = isolated_runtime_environment(Path(temporary), os.environ)
        environment.update(cohort)
        environment["DITTO_CORS_ORIGINS"] = f"http://{_HOST}:{port}"
        process = spawn_managed(backend_command(port), root, environment)
        try:
            for path in ("/healthz", "/readyz", "/api/v1/status"):
                wait_until_ready(_HOST, port, path, process, timeout)
                payload = fetch_json(_HOST, port, path, timeout)
                validate_payload(path, payload, cohort)
        finally:
            terminate_managed(process)

    print(
        "Platform API smoke passed:",
        f"loopback={_HOST}:{port}",
        f"git_sha={cohort['DITTO_GIT_SHA']}",
        f"contract_sha256={contract_sha256}",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--readiness-timeout", type=float, default=60.0)
    arguments = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    run_platform_smoke(root, timeout=arguments.readiness_timeout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
