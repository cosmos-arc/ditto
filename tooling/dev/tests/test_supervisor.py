from __future__ import annotations

import hashlib
import os
import signal
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from types import FrameType
from unittest.mock import Mock

import pytest
from tooling.dev import supervisor
from tooling.dev.supervisor import isolated_runtime_environment, service_ports

_TEST_COHORT = {
    "DITTO_PRODUCT_VERSION": "0.1.0",
    "DITTO_GIT_SHA": "d" * 40,
    "DITTO_API_CONTRACT_VERSION": "v1",
    "DITTO_API_CONTRACT_SHA256": "a" * 64,
}


def _stub_development_cohort(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        supervisor,
        "development_cohort_environment",
        lambda _root: _TEST_COHORT.copy(),
    )


def test_worktree_runtime_is_isolated_and_scrubs_credentials(tmp_path: Path) -> None:
    source = {
        "OPENAI_API_KEY": "secret",
        "TUSHARE_TOKEN": "secret",
        "AWS_SECRET_ACCESS_KEY": "secret",
        "DATABASE_PASSWORD": "secret",
        "SENTRY_DSN": "https://secret@example.invalid/1",
        "DATA_ROOT": "/real/user/data",
        "DITTO_BASE_DIR": "/real/user/base",
        "DITTO_DATA_ROOT": "/real/user/state",
        "DITTO_RUNTIME_DIR": "/real/user/runtime",
        "DITTO_TRADING_SQLITE_PATH": "/real/user/trading.sqlite",
        "DUCKDB_PATH": "/real/user/market.duckdb",
        "ENVIRONMENT": "production",
        "LOG_DIR": "/real/user/logs",
        "PATH": "/usr/bin",
        "PYTHON_KEYRING_BACKEND": "keyring.backends.macOS.Keyring",
        "SQLITE_PATH": "/real/user/metadata.sqlite",
        "VITE_API_BASE_URL": "https://remote.invalid/api",
        "VITE_USE_MOCK": "true",
    }

    environment = isolated_runtime_environment(tmp_path, source)

    assert "OPENAI_API_KEY" not in environment
    assert "TUSHARE_TOKEN" not in environment
    assert "AWS_SECRET_ACCESS_KEY" not in environment
    assert "DATABASE_PASSWORD" not in environment
    assert "SENTRY_DSN" not in environment
    for name in (
        "DATA_ROOT",
        "DITTO_BASE_DIR",
        "DITTO_DATA_ROOT",
        "DITTO_RUNTIME_DIR",
        "DITTO_TRADING_SQLITE_PATH",
        "DUCKDB_PATH",
        "LOG_DIR",
        "SQLITE_PATH",
    ):
        assert name not in environment
    assert "VITE_API_BASE_URL" not in environment
    assert "VITE_USE_MOCK" not in environment
    assert environment["PYTHON_KEYRING_BACKEND"] == "keyring.backends.null.Keyring"
    assert environment["ENVIRONMENT"] == "development"
    assert environment["DITTO_RUNTIME_PROFILE"] == "development-isolated"
    assert environment["DITTO_ALLOW_REAL_DATA"] == "0"
    assert environment["OTEL_SDK_DISABLED"] == "false"
    for name in ("DITTO_CONFIG_ROOT", "DITTO_STATE_ROOT", "DITTO_CACHE_ROOT"):
        path = Path(environment[name])
        assert path.is_dir()
        assert path.is_relative_to(tmp_path)
    observability = (
        Path(environment["DITTO_CONFIG_ROOT"])
        / "config"
        / "development"
        / "observability.env"
    ).read_text(encoding="utf-8")
    assert "TRACING_ENABLED=true" in observability
    assert "TRACING_EXPORTER=none" in observability
    assert "METRICS_ENABLED=false" in observability
    data_source = (
        Path(environment["DITTO_CONFIG_ROOT"])
        / "config"
        / "development"
        / "data_source.env"
    ).read_text(encoding="utf-8")
    assert "TUSHARE_TOKEN=ditto-isolated-placeholder" in data_source
    assert "HTTP_BASE_URL=http://127.0.0.1:9/disabled" in data_source


def test_different_worktrees_get_different_runtime_roots(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()

    first_env = isolated_runtime_environment(first, {})
    second_env = isolated_runtime_environment(second, {})

    assert first_env["DITTO_STATE_ROOT"] != second_env["DITTO_STATE_ROOT"]


def test_development_cohort_is_derived_from_head_manifest_and_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract = b'{"openapi":"3.1.0"}\n'
    contract_path = tmp_path / "contracts" / "openapi" / "v1.json"
    contract_path.parent.mkdir(parents=True)
    contract_path.write_bytes(contract)
    (tmp_path / "package.json").write_text(
        '{"name":"@ditto/workspace","version":"0.1.0"}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(supervisor, "_git_head_sha", lambda _root: "d" * 40)

    environment = supervisor.development_cohort_environment(tmp_path)

    assert environment == {
        "DITTO_PRODUCT_VERSION": "0.1.0",
        "DITTO_GIT_SHA": "d" * 40,
        "DITTO_API_CONTRACT_VERSION": "v1",
        "DITTO_API_CONTRACT_SHA256": hashlib.sha256(contract).hexdigest(),
    }


def test_development_git_identity_resolves_verified_full_head(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    git = tmp_path / "bin" / "git"
    calls: list[tuple[list[str], Path]] = []

    def fake_run(
        command: list[str],
        *,
        cwd: Path,
        capture_output: bool,
        text: bool,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        assert capture_output is True
        assert text is True
        assert check is False
        calls.append((command, cwd))
        return subprocess.CompletedProcess(command, 0, stdout=f"{'d' * 40}\n")

    monkeypatch.setattr(supervisor.shutil, "which", lambda _name: str(git))
    monkeypatch.setattr(supervisor.subprocess, "run", fake_run)

    assert supervisor._git_head_sha(tmp_path) == "d" * 40
    assert calls == [([str(git), "rev-parse", "--verify", "HEAD^{commit}"], tmp_path)]


def test_service_ports_reject_explicit_collision() -> None:
    with pytest.raises(ValueError, match="must differ"):
        service_ports(18101, 18101)


def test_service_ports_retry_a_dynamic_collision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidates = iter((18111, 18111, 18112))
    monkeypatch.setattr(
        supervisor,
        "available_port",
        lambda _requested: next(candidates),
    )

    assert service_ports(0, 0) == (18111, 18112)


def test_development_command_uses_the_pinned_workspace_leaf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(supervisor.shutil, "which", lambda _name: "/toolchain/bun")

    _api, web = supervisor.development_commands(tmp_path, 18201, 18202)

    assert web == [
        "/toolchain/bun",
        "run",
        "--cwd",
        str(tmp_path / "apps" / "web"),
        "dev",
        "--",
        "--host",
        "127.0.0.1",
        "--port",
        "18202",
        "--strictPort",
    ]


def _running_process(pid: int) -> Mock:
    process = Mock(spec=subprocess.Popen)
    process.pid = pid
    process.poll.return_value = None
    process.returncode = None
    return process


def test_supervisor_cleans_started_child_when_second_spawn_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = _running_process(101)
    started: list[Mock] = []
    terminated: list[Mock] = []

    def fake_spawn(
        _command: list[str], _root: Path, _environment: dict[str, str]
    ) -> Mock:
        assert _environment["VITE_DEV_API_TARGET"] == "http://127.0.0.1:18001"
        assert _environment["DITTO_CORS_ORIGINS"] == "http://127.0.0.1:18002"
        assert _environment["DITTO_PRODUCT_VERSION"] == "0.1.0"
        assert _environment["DITTO_GIT_SHA"] == "d" * 40
        assert _environment["DITTO_API_CONTRACT_VERSION"] == "v1"
        assert _environment["DITTO_API_CONTRACT_SHA256"] == "a" * 64
        if started:
            raise OSError("web process could not start")
        started.append(first)
        return first

    _stub_development_cohort(monkeypatch)
    monkeypatch.setattr(
        supervisor, "development_commands", lambda *_: (["api"], ["web"])
    )
    monkeypatch.setattr(supervisor, "spawn_managed", fake_spawn)
    monkeypatch.setattr(supervisor, "terminate_managed", terminated.append)

    with pytest.raises(OSError, match="web process could not start"):
        supervisor.supervise(tmp_path, 18001, 18002, 0.1)

    assert terminated == [first]


def test_supervisor_turns_sigterm_into_cleanup_and_shell_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = _running_process(201)
    second = _running_process(202)
    processes = iter((first, second))
    terminated: list[Mock] = []
    handlers: dict[int, Callable[[int, FrameType | None], object]] = {}
    restored: list[tuple[int, object]] = []
    previous_handler = object()

    def fake_signal(
        signal_number: int,
        handler: Callable[[int, FrameType | None], None] | object,
    ) -> object:
        if handler is previous_handler:
            restored.append((signal_number, handler))
        else:
            assert callable(handler)
            handlers[signal_number] = handler
        return previous_handler

    sleep_calls = 0

    def fake_sleep(_seconds: float) -> None:
        nonlocal sleep_calls
        sleep_calls += 1
        if sleep_calls == 1:
            handlers[signal.SIGTERM](signal.SIGTERM, None)

    _stub_development_cohort(monkeypatch)
    monkeypatch.setattr(
        supervisor, "development_commands", lambda *_: (["api"], ["web"])
    )
    monkeypatch.setattr(supervisor, "spawn_managed", lambda *_: next(processes))
    monkeypatch.setattr(supervisor, "wait_until_ready", lambda *_: None)
    monkeypatch.setattr(supervisor, "terminate_managed", terminated.append)
    monkeypatch.setattr(
        supervisor.signal, "getsignal", lambda _signal: previous_handler
    )
    monkeypatch.setattr(supervisor.signal, "signal", fake_signal)
    monkeypatch.setattr(supervisor.time, "sleep", fake_sleep)

    status = supervisor.supervise(tmp_path, 18011, 18012, 0.1)

    assert status == 128 + signal.SIGTERM
    assert terminated == [second, first]
    assert {item[0] for item in restored} == {signal.SIGINT, signal.SIGTERM}


def test_supervisor_propagates_child_failure_and_cleans_its_sibling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    failed = _running_process(301)
    failed.poll.return_value = 7
    failed.returncode = 7
    sibling = _running_process(302)
    processes = iter((failed, sibling))
    terminated: list[Mock] = []

    _stub_development_cohort(monkeypatch)
    monkeypatch.setattr(
        supervisor, "development_commands", lambda *_: (["api"], ["web"])
    )
    monkeypatch.setattr(supervisor, "spawn_managed", lambda *_: next(processes))
    monkeypatch.setattr(supervisor, "wait_until_ready", lambda *_: None)
    monkeypatch.setattr(supervisor, "terminate_managed", terminated.append)

    status = supervisor.supervise(tmp_path, 18021, 18022, 0.1)

    assert status == 7
    assert terminated == [sibling, failed]


def test_supervisor_cleans_both_children_when_readiness_times_out(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = _running_process(401)
    second = _running_process(402)
    processes = iter((first, second))
    terminated: list[Mock] = []

    _stub_development_cohort(monkeypatch)
    monkeypatch.setattr(
        supervisor, "development_commands", lambda *_: (["api"], ["web"])
    )
    monkeypatch.setattr(supervisor, "spawn_managed", lambda *_: next(processes))
    monkeypatch.setattr(
        supervisor,
        "wait_until_ready",
        lambda *_: (_ for _ in ()).throw(TimeoutError("not ready")),
    )
    monkeypatch.setattr(supervisor, "terminate_managed", terminated.append)

    with pytest.raises(TimeoutError, match="not ready"):
        supervisor.supervise(tmp_path, 18031, 18032, 0.1)

    assert terminated == [second, first]


def _windows_taskkill(tmp_path: Path) -> Path:
    taskkill = tmp_path / "Windows" / "System32" / "taskkill.exe"
    taskkill.parent.mkdir(parents=True)
    taskkill.touch()
    return taskkill


def test_windows_cleanup_routes_through_tree_kill_when_leader_already_exited(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    leader = _running_process(491)
    leader.poll.return_value = 7
    leader.returncode = 7
    terminated: list[Mock] = []

    monkeypatch.setattr(supervisor.os, "name", "nt")
    monkeypatch.setattr(
        supervisor,
        "_terminate_windows_process_tree",
        terminated.append,
    )

    supervisor.terminate_managed(leader)

    assert terminated == [leader]


def test_windows_tree_kill_uses_system_taskkill_for_exited_leader(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    taskkill = _windows_taskkill(tmp_path)
    leader = _running_process(492)
    leader.poll.return_value = 7
    leader.returncode = 7
    leader.wait.return_value = 7
    commands: list[list[str]] = []

    def fake_run(
        command: list[str],
        *,
        capture_output: bool,
        text: bool,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        assert capture_output is True
        assert text is True
        assert check is False
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="SUCCESS", stderr="")

    monkeypatch.setenv("SystemRoot", str(taskkill.parents[1]))
    monkeypatch.setenv("PATH", str(tmp_path / "untrusted-path"))
    monkeypatch.setattr(supervisor.subprocess, "run", fake_run)

    supervisor._terminate_windows_process_tree(leader)

    assert commands == [[str(taskkill), "/PID", "492", "/T", "/F"]]
    leader.wait.assert_called_once_with(
        timeout=supervisor._PROCESS_GROUP_KILL_WAIT_SECONDS
    )


def test_windows_tree_kill_fails_closed_when_taskkill_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    taskkill = _windows_taskkill(tmp_path)
    leader = _running_process(493)

    monkeypatch.setenv("SystemRoot", str(taskkill.parents[1]))
    monkeypatch.setattr(
        supervisor.subprocess,
        "run",
        lambda command, **_kwargs: subprocess.CompletedProcess(
            command,
            5,
            stdout="ERROR: child 9001 remains",
            stderr="Access is denied",
        ),
    )

    with pytest.raises(
        RuntimeError,
        match=r"taskkill failed for process tree 493 with exit code 5",
    ) as failure:
        supervisor._terminate_windows_process_tree(leader)

    assert "Access is denied" in str(failure.value)
    leader.wait.assert_not_called()


@pytest.mark.skipif(supervisor.os.name == "nt", reason="POSIX process-group contract")
def test_terminate_managed_signals_group_when_leader_already_exited(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    leader = _running_process(501)
    leader.poll.return_value = 7
    leader.returncode = 7
    signals: list[tuple[int, int]] = []
    monkeypatch.setattr(
        supervisor.os,
        "killpg",
        lambda process_group, signal_number: signals.append(
            (process_group, signal_number)
        ),
    )
    monkeypatch.setattr(supervisor, "_process_group_exists", lambda _group: False)

    supervisor.terminate_managed(leader)

    assert signals == [(501, signal.SIGTERM)]


def _pid_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


@pytest.mark.skipif(supervisor.os.name == "nt", reason="POSIX process-group contract")
def test_terminate_managed_kills_stubborn_descendant_after_leader_exits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    child_code = """
import os
import signal
import sys
import time

ready_fd = int(sys.argv[1])
signal.signal(signal.SIGTERM, signal.SIG_IGN)
os.write(ready_fd, b"1")
os.close(ready_fd)
time.sleep(60)
"""
    leader_code = """
import os
import subprocess
import sys

read_fd, write_fd = os.pipe()
child = subprocess.Popen(
    [sys.executable, "-c", sys.argv[1], str(write_fd)],
    pass_fds=(write_fd,),
)
os.close(write_fd)
os.read(read_fd, 1)
os.close(read_fd)
print(child.pid, flush=True)
"""
    leader = subprocess.Popen(
        [sys.executable, "-c", leader_code, child_code],
        start_new_session=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert leader.stdout is not None
    child_pid = int(leader.stdout.readline().strip())
    leader.wait(timeout=5)
    monkeypatch.setattr(supervisor, "_PROCESS_GROUP_GRACE_SECONDS", 0.1)
    monkeypatch.setattr(supervisor, "_PROCESS_GROUP_KILL_WAIT_SECONDS", 1.0)

    try:
        supervisor.terminate_managed(leader)
        deadline = time.monotonic() + 1
        while _pid_exists(child_pid) and time.monotonic() < deadline:
            time.sleep(0.01)
        assert not _pid_exists(child_pid)
    finally:
        try:
            supervisor.os.killpg(leader.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
