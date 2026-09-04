"""Focused tests for release artifact container smoke policy."""

from __future__ import annotations

from pathlib import Path

from tooling.release import artifact_gate


class _HealthyResponse:
    status = 200

    def __enter__(self) -> _HealthyResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None


def test_container_smoke_injects_offline_token_only_at_runtime(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Artifact smoke must not expect a credential-free image to be ready."""
    commands: list[list[str]] = []

    def fake_run(
        command: list[str],
        *,
        cwd: Path,
        capture_output: bool = False,
    ) -> str:
        del cwd, capture_output
        commands.append(command)
        if command[1:3] == ["image", "inspect"]:
            return "65532:65532"
        if command[1] == "run":
            return "container-id"
        if command[1] == "port":
            return "127.0.0.1:18000"
        if command[1] == "logs":
            return ""
        raise AssertionError(f"unexpected command: {command!r}")

    monkeypatch.setattr(artifact_gate, "_run", fake_run)
    monkeypatch.setattr(
        artifact_gate.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: _HealthyResponse(),
    )
    monkeypatch.setattr(
        artifact_gate.subprocess,
        "run",
        lambda *_args, **_kwargs: None,
    )

    artifact_gate._smoke_container("docker", tmp_path, "ditto-ci:test")

    docker_run = next(command for command in commands if command[1] == "run")
    assert "TUSHARE_TOKEN=ci-smoke-offline-credential" in docker_run
    assert docker_run.index("--env") < docker_run.index("ditto-ci:test")
