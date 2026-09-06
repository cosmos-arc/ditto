"""Focused subprocess lifecycle tests for the local supply-chain gate."""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import NoReturn

import pytest
from tooling.security import supply_chain


def test_linked_worktree_history_is_mounted_and_checked_before_scanning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repository"
    worktree = tmp_path / "worktree"
    git = shutil.which("git")
    assert git is not None
    subprocess.run(  # noqa: S603 — resolved Git, fixed arguments in a temporary repository
        [git, "init", str(repository)], check=True, capture_output=True
    )
    subprocess.run(  # noqa: S603
        [
            git,
            "-C",
            str(repository),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "--allow-empty",
            "-m",
            "initial",
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(  # noqa: S603
        [git, "-C", str(repository), "worktree", "add", str(worktree)],
        check=True,
        capture_output=True,
    )
    commands: list[list[str]] = []
    monkeypatch.setattr(supply_chain, "_require_docker", lambda _root: "docker")

    def record(command: list[str], **_kwargs: object) -> int:
        commands.append(command)
        return 0

    monkeypatch.setattr(supply_chain, "_run", record)
    supply_chain.run_supply_chain_gate(worktree)
    common = repository / ".git"
    history = [command for command in commands if "--log-opts=--all" in command]
    assert len(history) == 2
    assert all(f"{common}:{common}:ro" in command for command in history)
    assert any(
        "--entrypoint" in command and "rev-parse" in command for command in commands
    )


def _resolved_executable(name: str) -> str:
    return f"/resolved/{name}"


def test_scanner_timeout_removes_only_its_named_container(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    commands: list[list[str]] = []

    def fake_run(
        command: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[bytes]:
        commands.append(command)
        if command[1] == "run":
            raise subprocess.TimeoutExpired(cmd=command, timeout=1)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(supply_chain.subprocess, "run", fake_run)
    with pytest.raises(supply_chain.SupplyChainGateError, match="timed out"):
        supply_chain._run(
            ["/resolved/docker", "run", "--rm", "scanner"],
            cwd=tmp_path,
            timeout_seconds=1,
        )
    assert len(commands) == 2
    name = commands[0][commands[0].index("--name") + 1]
    assert name.startswith("ditto-security-")
    assert commands[1] == ["/resolved/docker", "rm", "--force", name]


def test_docker_probe_timeout_is_reported_as_a_fail_closed_gate_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def timeout_run(command: list[str], **_kwargs: object) -> NoReturn:
        raise subprocess.TimeoutExpired(cmd=command, timeout=1)

    monkeypatch.setattr(supply_chain, "_executable", _resolved_executable)
    monkeypatch.setattr(supply_chain.subprocess, "run", timeout_run)

    with pytest.raises(
        supply_chain.SupplyChainGateError,
        match=r"timed out.*docker.*version",
    ) as captured:
        supply_chain.run_supply_chain_gate(tmp_path)

    assert isinstance(captured.value.__cause__, subprocess.TimeoutExpired)


def test_repository_enumeration_timeout_is_reported_as_a_gate_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fake_run(
        command: list[str],
        *,
        cwd: Path,
        check: bool,
        timeout: float | None = None,
        capture_output: bool = False,
    ) -> subprocess.CompletedProcess[bytes]:
        del cwd, check, timeout, capture_output
        if command[1] == "ls-files":
            raise subprocess.TimeoutExpired(cmd=command, timeout=1)
        return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(supply_chain, "_executable", _resolved_executable)
    monkeypatch.setattr(supply_chain.subprocess, "run", fake_run)

    with pytest.raises(
        supply_chain.SupplyChainGateError,
        match=r"repository enumeration timed out.*git.*ls-files",
    ) as captured:
        supply_chain.run_supply_chain_gate(tmp_path)

    assert isinstance(captured.value.__cause__, subprocess.TimeoutExpired)


def test_every_local_security_command_has_an_explicit_category_budget(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[tuple[tuple[str, ...], float | None]] = []

    def fake_run(
        command: list[str],
        *,
        cwd: Path,
        check: bool,
        timeout: float | None = None,
        capture_output: bool = False,
    ) -> subprocess.CompletedProcess[bytes]:
        del cwd, check
        calls.append((tuple(command), timeout))
        returncode = 23 if "/probe/leak.txt" in command else 0
        stdout = b"" if capture_output else None
        return subprocess.CompletedProcess(
            command,
            returncode,
            stdout=stdout,
            stderr=b"" if capture_output else None,
        )

    monkeypatch.setattr(supply_chain, "_executable", _resolved_executable)
    monkeypatch.setattr(supply_chain.subprocess, "run", fake_run)

    supply_chain.run_supply_chain_gate(tmp_path)

    assert all(timeout is not None and 0 < timeout < 60 * 60 for _, timeout in calls)

    def timeout_for(predicate: Callable[[tuple[str, ...]], bool]) -> float | None:
        matches = [timeout for command, timeout in calls if predicate(command)]
        assert len(matches) == 1
        return matches[0]

    assert timeout_for(lambda command: command[1:3] == ("version", "--format")) == (
        supply_chain._DOCKER_PROBE_TIMEOUT_SECONDS
    )
    assert timeout_for(lambda command: command[1] == "ls-files") == (
        supply_chain._REPOSITORY_ENUMERATION_TIMEOUT_SECONDS
    )
    sentinel_timeouts = [
        timeout for command, timeout in calls if "/probe/leak.txt" in command
    ]
    assert sentinel_timeouts == [
        supply_chain._SCANNER_SENTINEL_TIMEOUT_SECONDS,
        supply_chain._SCANNER_SENTINEL_TIMEOUT_SECONDS,
    ]
    assert timeout_for(lambda command: supply_chain._OSV_SCANNER in command) == (
        supply_chain._OSV_SCAN_TIMEOUT_SECONDS
    )

    gitleaks_timeouts = [
        timeout
        for command, timeout in calls
        if "/probe/leak.txt" not in command
        and "--entrypoint" not in command
        and (
            supply_chain._GITLEAKS_CURRENT in command
            or supply_chain._GITLEAKS_KNOWN_GOOD in command
        )
    ]
    assert gitleaks_timeouts == [
        supply_chain._GITLEAKS_SCAN_TIMEOUT_SECONDS,
        supply_chain._GITLEAKS_SCAN_TIMEOUT_SECONDS,
        supply_chain._GITLEAKS_SCAN_TIMEOUT_SECONDS,
        supply_chain._GITLEAKS_SCAN_TIMEOUT_SECONDS,
    ]


def test_each_gitleaks_version_scans_the_exact_current_tree_and_its_own_sentinel(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    commands: list[tuple[str, ...]] = []

    def fake_run(
        command: list[str],
        *,
        cwd: Path,
        check: bool,
        timeout: float | None = None,
        capture_output: bool = False,
    ) -> subprocess.CompletedProcess[bytes]:
        del cwd, check, timeout
        commands.append(tuple(command))
        returncode = 23 if "/probe/leak.txt" in command else 0
        stdout = b"" if capture_output else None
        return subprocess.CompletedProcess(
            command,
            returncode,
            stdout=stdout,
            stderr=b"" if capture_output else None,
        )

    monkeypatch.setattr(supply_chain, "_executable", _resolved_executable)
    monkeypatch.setattr(supply_chain.subprocess, "run", fake_run)

    supply_chain.run_supply_chain_gate(tmp_path)

    for image in (
        supply_chain._GITLEAKS_CURRENT,
        supply_chain._GITLEAKS_KNOWN_GOOD,
    ):
        tree_scans = [
            command
            for command in commands
            if image in command
            and any(argument.endswith(":/scan:ro") for argument in command)
        ]
        sentinel_scans = [
            command
            for command in commands
            if image in command and "/probe/leak.txt" in command
        ]
        assert len(tree_scans) == 1
        assert len(sentinel_scans) == 1
