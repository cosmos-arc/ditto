"""Tests for the cross-platform live API smoke supervisor."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest
from tooling.dev import platform_smoke

_COHORT = {
    "DITTO_PRODUCT_VERSION": "0.1.0",
    "DITTO_GIT_SHA": "d" * 40,
    "DITTO_API_CONTRACT_VERSION": "v1",
    "DITTO_API_CONTRACT_SHA256": "a" * 64,
}


def _running_process() -> Mock:
    process = Mock(spec=subprocess.Popen)
    process.pid = 711
    process.poll.return_value = None
    process.returncode = None
    return process


def _payload(path: str) -> dict[str, object]:
    if path == "/healthz":
        return {"status": "ok", "service": "ditto-api"}
    if path == "/readyz":
        return {
            "status": "ready",
            "service": "ditto-api",
            "checks": {
                name: {"ok": True, "detail": "available"}
                for name in ("startup", "config_root", "state_root", "cache_root")
            },
        }
    if path == "/api/v1/status":
        return {
            "status": "running",
            "product_version": _COHORT["DITTO_PRODUCT_VERSION"],
            "git_sha": _COHORT["DITTO_GIT_SHA"],
            "api_contract_version": _COHORT["DITTO_API_CONTRACT_VERSION"],
            "api_contract_sha256": _COHORT["DITTO_API_CONTRACT_SHA256"],
        }
    raise AssertionError(f"unexpected path: {path}")


def test_live_smoke_uses_temporary_roots_exact_cohort_and_loopback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    process = _running_process()
    captured_environment: dict[str, str] = {}
    captured_command: list[str] = []
    waited_paths: list[str] = []
    terminated: list[Mock] = []

    def fake_spawn(command: list[str], root: Path, environment: dict[str, str]) -> Mock:
        assert root == tmp_path
        for name in (
            "DITTO_CONFIG_ROOT",
            "DITTO_STATE_ROOT",
            "DITTO_CACHE_ROOT",
            "DITTO_LOG_DIR",
        ):
            runtime_path = Path(environment[name])
            assert runtime_path.is_dir()
            assert not runtime_path.is_relative_to(tmp_path)
        captured_command.extend(command)
        captured_environment.update(environment)
        return process

    def fake_wait(
        host: str,
        port: int,
        path: str,
        candidate: Mock,
        timeout: float,
    ) -> None:
        assert host == "127.0.0.1"
        assert port == 18731
        assert candidate is process
        assert timeout == 3.0
        waited_paths.append(path)

    monkeypatch.setenv("TUSHARE_TOKEN", "real-user-secret")
    monkeypatch.setattr(
        platform_smoke,
        "development_cohort_environment",
        lambda _root: _COHORT.copy(),
    )
    monkeypatch.setattr(platform_smoke, "available_port", lambda _requested: 18731)
    monkeypatch.setattr(platform_smoke, "spawn_managed", fake_spawn)
    monkeypatch.setattr(platform_smoke, "wait_until_ready", fake_wait)
    monkeypatch.setattr(platform_smoke, "fetch_json", lambda *_args: _payload(_args[2]))
    monkeypatch.setattr(platform_smoke, "terminate_managed", terminated.append)

    platform_smoke.run_platform_smoke(tmp_path, timeout=3.0)

    assert captured_command == platform_smoke.backend_command(18731)
    assert "--host" in captured_command
    assert captured_command[captured_command.index("--host") + 1] == "127.0.0.1"
    assert waited_paths == ["/healthz", "/readyz", "/api/v1/status"]
    assert terminated == [process]
    assert "TUSHARE_TOKEN" not in captured_environment
    assert captured_environment["DITTO_ALLOW_REAL_DATA"] == "0"
    for name, expected in _COHORT.items():
        assert captured_environment[name] == expected
    for name in (
        "DITTO_CONFIG_ROOT",
        "DITTO_STATE_ROOT",
        "DITTO_CACHE_ROOT",
        "DITTO_LOG_DIR",
    ):
        runtime_path = Path(captured_environment[name])
        assert not runtime_path.exists(), "temporary runtime roots must be removed"
        assert not runtime_path.is_relative_to(tmp_path)


def test_live_smoke_fails_closed_and_still_cleans_the_api(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    process = _running_process()
    terminated: list[Mock] = []

    monkeypatch.setattr(
        platform_smoke,
        "development_cohort_environment",
        lambda _root: _COHORT.copy(),
    )
    monkeypatch.setattr(platform_smoke, "available_port", lambda _requested: 18732)
    monkeypatch.setattr(platform_smoke, "spawn_managed", lambda *_args: process)
    monkeypatch.setattr(platform_smoke, "wait_until_ready", lambda *_args: None)
    monkeypatch.setattr(
        platform_smoke,
        "fetch_json",
        lambda *_args: (
            {"status": "not_ready", "service": "ditto-api", "checks": {}}
            if _args[2] == "/readyz"
            else _payload(_args[2])
        ),
    )
    monkeypatch.setattr(platform_smoke, "terminate_managed", terminated.append)

    with pytest.raises(RuntimeError, match=r"/readyz.*status='ready'"):
        platform_smoke.run_platform_smoke(tmp_path, timeout=0.1)

    assert terminated == [process]


@pytest.mark.parametrize(
    ("path", "payload", "message"),
    [
        ("/healthz", {"status": "ok"}, "service='ditto-api'"),
        (
            "/readyz",
            {
                "status": "ready",
                "service": "ditto-api",
                "checks": {"startup": {"ok": True}},
            },
            "missing successful checks",
        ),
        (
            "/api/v1/status",
            {
                "status": "running",
                "product_version": "different",
                "git_sha": _COHORT["DITTO_GIT_SHA"],
                "api_contract_version": "v1",
                "api_contract_sha256": "a" * 64,
            },
            "cohort metadata mismatch",
        ),
    ],
)
def test_response_validation_is_fail_closed(
    path: str, payload: dict[str, object], message: str
) -> None:
    with pytest.raises(RuntimeError, match=message):
        platform_smoke.validate_payload(path, payload, _COHORT)
