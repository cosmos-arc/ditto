"""Physical process-boundary tests for the OCI Docker CLI runner."""

from __future__ import annotations

import hashlib
import os
import sys
import time
from pathlib import Path

import pytest
from ditto_analysis.experiments.models import ContentHash
from ditto_apps.registry.agent import oci_sandbox_runner
from ditto_apps.registry.agent.oci_sandbox import OciSandboxCommand
from ditto_apps.registry.agent.oci_sandbox_runner import (
    DockerCliOciCommandRunner,
    DockerRuntimeProfile,
)


def _fake_docker(tmp_path: Path) -> tuple[Path, Path]:
    cleanup_marker = tmp_path / "cleanup.marker"
    server_version = tmp_path / "server.version"
    server_version.write_text("29.4.0", encoding="ascii")
    executable = tmp_path / "docker"
    executable.write_text(
        f"""#!{sys.executable}
import json
import os
import pathlib
import subprocess
import sys
import time

if pathlib.Path(sys.argv[0]).name != "docker":
    raise SystemExit(90)

args = sys.argv[1:]
if "info" in args:
    print(json.dumps({{
        "ServerVersion": pathlib.Path(
            {str(server_version)!r}
        ).read_text(encoding="ascii"),
        "OperatingSystem": "OrbStack",
        "Architecture": "aarch64",
        "KernelVersion": "7.0.14-orbstack-test",
        "CgroupDriver": "cgroupfs",
        "SecurityOptions": ["name=seccomp,profile=builtin", "name=cgroupns"],
        "Runtimes": {{"runc": {{}}}},
    }}, separators=(",", ":")))
    raise SystemExit(0)
if "rm" in args:
    if pathlib.Path({str(tmp_path / "cleanup.fail")!r}).exists():
        sys.stderr.write("cleanup failed")
        raise SystemExit(1)
    pathlib.Path({str(cleanup_marker)!r}).write_text("cleaned", encoding="utf-8")
    if pathlib.Path({str(tmp_path / "cleanup.linger")!r}).exists():
        pathlib.Path({str(tmp_path / "inspect.remaining")!r}).write_text(
            "1", encoding="ascii"
        )
    raise SystemExit(0)
if "inspect" in args:
    count_path = pathlib.Path({str(tmp_path / "inspect.count")!r})
    count = int(count_path.read_text(encoding="ascii")) if count_path.exists() else 0
    count_path.write_text(str(count + 1), encoding="ascii")
    if pathlib.Path({str(tmp_path / "cleanup.stuck")!r}).exists():
        raise SystemExit(0)
    remaining_path = pathlib.Path({str(tmp_path / "inspect.remaining")!r})
    if remaining_path.exists():
        remaining = int(remaining_path.read_text(encoding="ascii"))
        if remaining > 0:
            remaining_path.write_text(str(remaining - 1), encoding="ascii")
            raise SystemExit(0)
    raise SystemExit(1)
cidfile = next(
    value.split("=", 1)[1] for value in args if value.startswith("--cidfile=")
)
pathlib.Path(cidfile).write_text("a" * 64, encoding="ascii")
mode = args[-1]
if mode == "timeout":
    time.sleep(10)
elif mode == "orphan-pipe":
    subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(10)"],
        stdout=sys.stdout,
        stderr=sys.stderr,
    )
elif mode == "output-bomb":
    sys.stdout.write(os.environ.get("DITTO_TEST_SECRET", "secret-absent"))
    sys.stdout.write("x" * 8192)
elif mode == "policy":
    sys.stderr.write("policy denied")
    raise SystemExit(126)
else:
    sys.stdout.write("ok")
""",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    return executable, cleanup_marker


def _profile() -> DockerRuntimeProfile:
    return DockerRuntimeProfile(
        context="orbstack",
        server_version="29.4.0",
        operating_system="OrbStack",
        architecture="aarch64",
        kernel_version="7.0.14-orbstack-test",
        cgroup_driver="cgroupfs",
        security_options=("name=cgroupns", "name=seccomp,profile=builtin"),
        runtimes=("runc",),
    )


def _seccomp(tmp_path: Path) -> tuple[Path, ContentHash]:
    path = tmp_path / "seccomp.json"
    if not path.exists():
        path.write_bytes(b'{"defaultAction":"SCMP_ACT_ERRNO"}')
    return path, ContentHash(hashlib.sha256(path.read_bytes()).hexdigest())


def _runner(executable: Path, tmp_path: Path) -> tuple[DockerCliOciCommandRunner, Path]:
    seccomp, seccomp_hash = _seccomp(tmp_path)
    return (
        DockerCliOciCommandRunner(
            docker_binary=executable,
            runtime_profile=_profile(),
            home_directory=tmp_path,
            seccomp_profile_path=seccomp,
            seccomp_profile_hash=seccomp_hash,
        ),
        seccomp,
    )


def _command(
    mode: str,
    *,
    seccomp_path: Path,
    timeout: int = 2,
    output_limit: int = 64,
) -> OciSandboxCommand:
    return OciSandboxCommand(
        argv=(
            "docker",
            "--context=orbstack",
            "run",
            f"--security-opt=seccomp={seccomp_path}",
            "--rm",
            mode,
        ),
        stdin=b"",
        environment=(),
        timeout_seconds=timeout,
        stdout_limit_bytes=output_limit,
        stderr_limit_bytes=output_limit,
        security_evidence_hash=ContentHash(hashlib.sha256(b"a3").hexdigest()),
    )


def test_runner_rejects_runtime_drift_before_container_start(
    tmp_path: Path,
) -> None:
    executable, _cleanup = _fake_docker(tmp_path)
    (tmp_path / "server.version").write_text("forged", encoding="ascii")
    runner, seccomp = _runner(executable, tmp_path)

    with pytest.raises(RuntimeError, match="runtime inventory drift"):
        runner.run(_command("success", seccomp_path=seccomp))


def test_runner_bounds_output_and_does_not_inherit_host_secrets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executable, cleanup = _fake_docker(tmp_path)
    monkeypatch.setenv("DITTO_TEST_SECRET", "must-not-leak")
    runner, seccomp = _runner(executable, tmp_path)

    result = runner.run(_command("output-bomb", seccomp_path=seccomp))

    assert result.resource_exhausted is True
    assert len(result.stdout) <= 65
    assert b"must-not-leak" not in result.stdout
    assert cleanup.read_text(encoding="utf-8") == "cleaned"


def test_runner_falls_back_to_exact_child_when_process_group_signal_is_denied(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executable, cleanup = _fake_docker(tmp_path)
    runner, seccomp = _runner(executable, tmp_path)

    def deny_process_group_signal(_process_group: int, _signal: int) -> None:
        raise PermissionError

    monkeypatch.setattr(oci_sandbox_runner.os, "killpg", deny_process_group_signal)

    result = runner.run(_command("output-bomb", seccomp_path=seccomp))

    assert result.resource_exhausted is True
    assert cleanup.read_text(encoding="utf-8") == "cleaned"


def test_runner_enforces_wall_timeout_and_removes_the_exact_container(
    tmp_path: Path,
) -> None:
    executable, cleanup = _fake_docker(tmp_path)
    runner, seccomp = _runner(executable, tmp_path)

    started = time.monotonic()
    result = runner.run(_command("timeout", seccomp_path=seccomp, timeout=3))

    # Coverage instrumentation can delay the child interpreter before it writes
    # the cidfile. Keep enough startup headroom while remaining below the fake
    # child's ten-second sleep.
    assert time.monotonic() - started < 8
    assert result.timed_out is True
    assert cleanup.read_text(encoding="utf-8") == "cleaned"


def test_runner_timeout_is_not_extended_by_orphaned_output_pipes(
    tmp_path: Path,
) -> None:
    executable, cleanup = _fake_docker(tmp_path)
    runner, seccomp = _runner(executable, tmp_path)

    started = time.monotonic()
    result = runner.run(_command("orphan-pipe", seccomp_path=seccomp, timeout=3))

    # The hard bound remains below the orphan's ten-second sleep, while leaving
    # coverage-instrumented startup headroom before the cidfile is written.
    assert time.monotonic() - started < 8
    assert result.timed_out is True
    assert cleanup.read_text(encoding="utf-8") == "cleaned"


def test_runner_maps_policy_exit_without_a_shell(tmp_path: Path) -> None:
    executable, _cleanup = _fake_docker(tmp_path)
    runner, seccomp = _runner(executable, tmp_path)

    result = runner.run(_command("policy", seccomp_path=seccomp))

    assert result.exit_code == 126
    assert result.policy_rejected is True
    assert result.stderr == b"policy denied"
    assert os.environ.get("DITTO_TEST_SECRET") is None


def test_runner_preserves_the_approved_docker_symlink_invocation_path(
    tmp_path: Path,
) -> None:
    executable, _cleanup = _fake_docker(tmp_path)
    target = tmp_path / "orbstack-docker-target"
    executable.rename(target)
    executable.symlink_to(target)
    runner, seccomp = _runner(executable, tmp_path)

    assert runner.run(_command("success", seccomp_path=seccomp)).stdout == b"ok"


def test_runner_rejects_seccomp_profile_drift_before_container_start(
    tmp_path: Path,
) -> None:
    executable, _cleanup = _fake_docker(tmp_path)
    seccomp = tmp_path / "seccomp.json"
    seccomp.write_bytes(b'{"defaultAction":"SCMP_ACT_ERRNO"}')
    approved_hash = ContentHash(hashlib.sha256(seccomp.read_bytes()).hexdigest())
    runner = DockerCliOciCommandRunner(
        docker_binary=executable,
        runtime_profile=_profile(),
        home_directory=tmp_path,
        seccomp_profile_path=seccomp,
        seccomp_profile_hash=approved_hash,
    )
    seccomp.write_bytes(b'{"defaultAction":"SCMP_ACT_ALLOW"}')

    with pytest.raises(RuntimeError, match="seccomp profile drift"):
        runner.run(_command("success", seccomp_path=seccomp))


def test_runner_fails_closed_when_exact_container_cleanup_fails(
    tmp_path: Path,
) -> None:
    executable, _cleanup = _fake_docker(tmp_path)
    (tmp_path / "cleanup.fail").touch()
    runner, seccomp = _runner(executable, tmp_path)

    with pytest.raises(RuntimeError, match="container cleanup failed"):
        runner.run(_command("success", seccomp_path=seccomp))


def test_runner_waits_until_daemon_confirms_container_cleanup(tmp_path: Path) -> None:
    executable, _cleanup = _fake_docker(tmp_path)
    (tmp_path / "cleanup.linger").touch()
    runner, seccomp = _runner(executable, tmp_path)

    result = runner.run(_command("success", seccomp_path=seccomp))

    assert result.stdout == b"ok"
    assert (tmp_path / "inspect.count").read_text(encoding="ascii") == "2"


def test_runner_fails_closed_when_daemon_never_confirms_cleanup(
    tmp_path: Path,
) -> None:
    executable, _cleanup = _fake_docker(tmp_path)
    (tmp_path / "cleanup.stuck").touch()
    runner, seccomp = _runner(executable, tmp_path)

    with pytest.raises(RuntimeError, match="cleanup verification failed"):
        runner.run(_command("success", seccomp_path=seccomp))

    assert (tmp_path / "inspect.count").read_text(encoding="ascii") == "20"
