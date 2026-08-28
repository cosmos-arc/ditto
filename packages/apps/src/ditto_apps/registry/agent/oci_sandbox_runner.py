"""Bounded, shell-free Docker CLI runner for an approved OCI sandbox profile."""

from __future__ import annotations

import hashlib
import os
import re
import selectors
import signal
import subprocess
import tempfile
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, cast

import orjson
from ditto_analysis.experiments.models import ContentHash

from ditto_apps.registry.agent.oci_sandbox import (
    OciSandboxCommand,
    OciSandboxProcessResult,
)

__all__ = ["DockerCliOciCommandRunner", "DockerRuntimeProfile"]

_CONTAINER_ID = re.compile(r"[0-9a-f]{64}")
_CLEANUP_VERIFY_ATTEMPTS = 20
_CLEANUP_VERIFY_INTERVAL_SECONDS = 0.05
_PROBE_OUTPUT_LIMIT = 256 * 1024
_POLICY_EXIT_CODE = 126
_RESOURCE_EXIT_CODE = 137


def _text(value: str, *, field: str) -> str:
    if not value or value != value.strip() or "\x00" in value:
        raise ValueError(f"Docker runtime {field} must be normalized")
    return value


def _texts(values: Sequence[str], *, field: str) -> tuple[str, ...]:
    typed = tuple(values)
    if not typed or any(type(value) is not str for value in typed):
        raise ValueError(f"Docker runtime {field} must be a non-empty sequence")
    normalized = tuple(sorted(_text(value, field=field) for value in typed))
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"Docker runtime {field} contains duplicates")
    return normalized


@dataclass(frozen=True, slots=True)
class DockerRuntimeProfile:
    """Exact daemon inventory covered by one A3 approval."""

    context: str
    server_version: str
    operating_system: str
    architecture: str
    kernel_version: str
    cgroup_driver: str
    security_options: Sequence[str]
    runtimes: Sequence[str]

    def __post_init__(self) -> None:
        """Normalize an immutable inventory identity."""
        for field_name in (
            "context",
            "server_version",
            "operating_system",
            "architecture",
            "kernel_version",
            "cgroup_driver",
        ):
            object.__setattr__(
                self,
                field_name,
                _text(
                    cast(str, getattr(self, field_name)),
                    field=field_name,
                ),
            )
        object.__setattr__(
            self,
            "security_options",
            _texts(self.security_options, field="security_options"),
        )
        object.__setattr__(
            self,
            "runtimes",
            _texts(self.runtimes, field="runtimes"),
        )

    def to_payload(self) -> dict[str, object]:
        """Return the canonical evidence surface for reports and approvals."""
        return {
            "context": self.context,
            "server_version": self.server_version,
            "operating_system": self.operating_system,
            "architecture": self.architecture,
            "kernel_version": self.kernel_version,
            "cgroup_driver": self.cgroup_driver,
            "security_options": list(self.security_options),
            "runtimes": list(self.runtimes),
        }


@dataclass(frozen=True, slots=True)
class _BoundedResult:
    exit_code: int | None
    stdout: bytes
    stderr: bytes
    timed_out: bool
    output_exhausted: bool


class _SelectableStream(Protocol):
    def fileno(self) -> int: ...

    def close(self) -> None: ...


@dataclass(slots=True)
class _StreamBuffers:
    stdin: bytes
    stdout_limit: int
    stderr_limit: int
    input_offset: int = 0
    stdout: bytearray = field(default_factory=bytearray)
    stderr: bytearray = field(default_factory=bytearray)


def _unregister_and_close(
    selector: selectors.BaseSelector,
    stream: _SelectableStream,
) -> None:
    selector.unregister(stream)
    stream.close()


def _append_bounded(target: bytearray, chunk: bytes, *, limit: int) -> bool:
    remaining = limit + 1 - len(target)
    if remaining > 0:
        target.extend(chunk[:remaining])
    return len(target) > limit or len(chunk) > remaining


def _handle_stream_event(
    selector: selectors.BaseSelector,
    stream: _SelectableStream,
    *,
    kind: str,
    buffers: _StreamBuffers,
) -> bool:
    if kind == "stdin":
        try:
            written = os.write(stream.fileno(), buffers.stdin[buffers.input_offset :])
        except BrokenPipeError:
            written = len(buffers.stdin) - buffers.input_offset
        buffers.input_offset += written
        if buffers.input_offset >= len(buffers.stdin):
            _unregister_and_close(selector, stream)
        return False
    chunk = os.read(stream.fileno(), 64 * 1024)
    if not chunk:
        _unregister_and_close(selector, stream)
        return False
    target, limit = (
        (buffers.stdout, buffers.stdout_limit)
        if kind == "stdout"
        else (buffers.stderr, buffers.stderr_limit)
    )
    return _append_bounded(target, chunk, limit=limit)


def _stop_process(
    process: subprocess.Popen[bytes],
    *,
    include_descendants: bool = False,
) -> None:
    if process.poll() is not None and not include_descendants:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=0.25)
    except PermissionError:
        try:
            process.terminate()
            process.wait(timeout=0.25)
        except (PermissionError, ProcessLookupError, subprocess.TimeoutExpired):
            pass
    except (ProcessLookupError, subprocess.TimeoutExpired):
        pass
    if process.poll() is None or include_descendants:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except PermissionError:
            try:
                process.kill()
            except (PermissionError, ProcessLookupError):
                pass
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            pass


def _close_registered_streams(selector: selectors.BaseSelector) -> None:
    for key in tuple(selector.get_map().values()):
        stream = cast("_SelectableStream", key.fileobj)
        try:
            selector.unregister(stream)
        except (KeyError, ValueError):
            pass
        try:
            stream.close()
        except OSError:
            pass


def _run_bounded(
    argv: tuple[str, ...],
    *,
    stdin: bytes,
    environment: Mapping[str, str],
    timeout_seconds: int,
    stdout_limit: int,
    stderr_limit: int,
) -> _BoundedResult:
    process = subprocess.Popen(  # noqa: S603 - argv is shell-free and prevalidated.
        argv,
        stdin=subprocess.PIPE if stdin else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=dict(environment),
        close_fds=True,
        start_new_session=True,
    )
    selector = selectors.DefaultSelector()
    stdout = process.stdout
    stderr = process.stderr
    if stdout is None or stderr is None:
        _stop_process(process)
        raise RuntimeError("Docker process pipes are unavailable")
    os.set_blocking(stdout.fileno(), False)
    os.set_blocking(stderr.fileno(), False)
    selector.register(stdout, selectors.EVENT_READ, "stdout")
    selector.register(stderr, selectors.EVENT_READ, "stderr")
    buffers = _StreamBuffers(
        stdin=stdin,
        stdout_limit=stdout_limit,
        stderr_limit=stderr_limit,
    )
    input_stream = process.stdin
    if input_stream is not None:
        os.set_blocking(input_stream.fileno(), False)
        selector.register(input_stream, selectors.EVENT_WRITE, "stdin")
    deadline = time.monotonic() + timeout_seconds
    timed_out = False
    output_exhausted = False
    try:
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                _stop_process(process, include_descendants=True)
                _close_registered_streams(selector)
                break
            events = selector.select(timeout=max(0.0, min(remaining, 0.05)))
            for key, _mask in events:
                stream = cast("_SelectableStream", key.fileobj)
                kind = cast(str, key.data)
                overflow = _handle_stream_event(
                    selector,
                    stream,
                    kind=kind,
                    buffers=buffers,
                )
                if overflow:
                    output_exhausted = True
                    _stop_process(process, include_descendants=True)
                    _close_registered_streams(selector)
                    break
            if process.poll() is not None and input_stream is not None:
                try:
                    selector.unregister(input_stream)
                except (KeyError, ValueError):
                    pass
                try:
                    input_stream.close()
                except OSError:
                    pass
                input_stream = None
    finally:
        selector.close()
        _stop_process(process)
    return _BoundedResult(
        exit_code=process.poll(),
        stdout=bytes(buffers.stdout),
        stderr=bytes(buffers.stderr),
        timed_out=timed_out,
        output_exhausted=output_exhausted,
    )


class DockerCliOciCommandRunner:
    """Execute an exact Docker profile with bounded streams and cleanup."""

    def __init__(
        self,
        *,
        docker_binary: Path,
        runtime_profile: DockerRuntimeProfile,
        home_directory: Path,
        seccomp_profile_path: Path,
        seccomp_profile_hash: ContentHash,
    ) -> None:
        binary = Path(
            os.path.abspath(  # noqa: PTH100 - preserve approved CLI symlink path.
                docker_binary
            )
        )
        home = home_directory.resolve(strict=True)
        if not binary.is_file() or not os.access(binary, os.X_OK):
            raise ValueError("Docker binary must be an executable file")
        if not home.is_dir():
            raise ValueError("Docker home directory must be a directory")
        seccomp = seccomp_profile_path.resolve(strict=True)
        if not seccomp.is_file() or type(seccomp_profile_hash) is not ContentHash:
            raise ValueError("Approved seccomp profile identity is invalid")
        observed_seccomp_hash = hashlib.sha256(seccomp.read_bytes()).hexdigest()
        if observed_seccomp_hash != str(seccomp_profile_hash):
            raise ValueError("Approved seccomp profile hash does not match its file")
        self._docker_binary = binary
        self._profile = runtime_profile
        self._seccomp_profile_path = seccomp
        self._seccomp_profile_hash = seccomp_profile_hash
        self._environment = {
            "DOCKER_CONFIG": str(home / ".docker"),
            "HOME": str(home),
            "LANG": "C",
            "LC_ALL": "C",
        }

    def _host_argv(self, *arguments: str) -> tuple[str, ...]:
        return (
            str(self._docker_binary),
            f"--context={self._profile.context}",
            *arguments,
        )

    def _probe_runtime(self) -> None:
        result = _run_bounded(
            self._host_argv("info", "--format", "{{json .}}"),
            stdin=b"",
            environment=self._environment,
            timeout_seconds=15,
            stdout_limit=_PROBE_OUTPUT_LIMIT,
            stderr_limit=64 * 1024,
        )
        if result.exit_code != 0 or result.timed_out or result.output_exhausted:
            raise RuntimeError("Docker runtime inventory is unavailable")
        try:
            decoded: object = orjson.loads(result.stdout)
            if not isinstance(decoded, Mapping):
                raise ValueError
            inventory = cast("Mapping[str, object]", decoded)
            security = inventory["SecurityOptions"]
            runtimes = inventory["Runtimes"]
            if not isinstance(security, Sequence) or isinstance(security, str):
                raise ValueError
            if not isinstance(runtimes, Mapping):
                raise ValueError
            observed = DockerRuntimeProfile(
                context=self._profile.context,
                server_version=cast(str, inventory["ServerVersion"]),
                operating_system=cast(str, inventory["OperatingSystem"]),
                architecture=cast(str, inventory["Architecture"]),
                kernel_version=cast(str, inventory["KernelVersion"]),
                cgroup_driver=cast(str, inventory["CgroupDriver"]),
                security_options=cast("Sequence[str]", security),
                runtimes=tuple(cast("Mapping[str, object]", runtimes)),
            )
        except (KeyError, TypeError, ValueError, orjson.JSONDecodeError) as exc:
            raise RuntimeError("Docker runtime inventory is invalid") from exc
        if observed != self._profile:
            raise RuntimeError("Docker runtime inventory drifted outside Approval A3")

    def _cleanup(self, cid_path: Path) -> None:
        try:
            container_id = cid_path.read_text(encoding="ascii").strip()
        except OSError:
            return
        if _CONTAINER_ID.fullmatch(container_id) is None:
            raise RuntimeError("Docker container cleanup identity is invalid")
        result = _run_bounded(
            self._host_argv("rm", "--force", container_id),
            stdin=b"",
            environment=self._environment,
            timeout_seconds=5,
            stdout_limit=64 * 1024,
            stderr_limit=64 * 1024,
        )
        if result.exit_code != 0 or result.timed_out or result.output_exhausted:
            raise RuntimeError("Docker container cleanup failed")
        for attempt in range(_CLEANUP_VERIFY_ATTEMPTS):
            verification = _run_bounded(
                self._host_argv("container", "inspect", container_id),
                stdin=b"",
                environment=self._environment,
                timeout_seconds=5,
                stdout_limit=64 * 1024,
                stderr_limit=64 * 1024,
            )
            if (
                verification.exit_code == 1
                and not verification.timed_out
                and not verification.output_exhausted
            ):
                return
            if (
                verification.exit_code not in (0, 1)
                or verification.timed_out
                or verification.output_exhausted
            ):
                raise RuntimeError("Docker container cleanup verification failed")
            if attempt + 1 < _CLEANUP_VERIFY_ATTEMPTS:
                time.sleep(_CLEANUP_VERIFY_INTERVAL_SECONDS)
        raise RuntimeError("Docker container cleanup verification failed")

    def _verify_seccomp_profile(self, command: OciSandboxCommand) -> None:
        option = f"--security-opt=seccomp={self._seccomp_profile_path}"
        if tuple(command.argv).count(option) != 1:
            raise RuntimeError("Docker command seccomp profile is outside Approval A3")
        try:
            observed = hashlib.sha256(
                self._seccomp_profile_path.read_bytes()
            ).hexdigest()
        except OSError as exc:
            raise RuntimeError("Docker seccomp profile is unavailable") from exc
        if observed != str(self._seccomp_profile_hash):
            raise RuntimeError("Docker seccomp profile drifted outside Approval A3")

    def run(self, command: OciSandboxCommand) -> OciSandboxProcessResult:
        """Verify the daemon, execute once, and always remove the exact container."""
        expected_prefix = (
            "docker",
            f"--context={self._profile.context}",
            "run",
        )
        if tuple(command.argv[:3]) != expected_prefix:
            raise RuntimeError("Docker command is outside the approved runtime context")
        self._verify_seccomp_profile(command)
        self._probe_runtime()
        with tempfile.TemporaryDirectory(prefix="ditto-r5-oci-") as raw_directory:
            cid_path = Path(raw_directory) / "container.cid"
            argv = (
                str(self._docker_binary),
                *command.argv[1:3],
                f"--cidfile={cid_path}",
                *command.argv[3:],
            )
            try:
                result = _run_bounded(
                    argv,
                    stdin=command.stdin,
                    environment=self._environment,
                    timeout_seconds=command.timeout_seconds,
                    stdout_limit=command.stdout_limit_bytes,
                    stderr_limit=command.stderr_limit_bytes,
                )
            finally:
                self._cleanup(cid_path)
        return OciSandboxProcessResult(
            exit_code=result.exit_code,
            stdout=result.stdout,
            stderr=result.stderr,
            timed_out=result.timed_out,
            resource_exhausted=(
                result.output_exhausted
                or result.exit_code in (_RESOURCE_EXIT_CODE, -signal.SIGKILL)
            ),
            policy_rejected=result.exit_code == _POLICY_EXIT_CODE,
        )
