"""Unit tests for ResearchExecutionSettings git/lockfile resolution."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from ditto_apps.registry.infra import config as config_module
from ditto_apps.registry.infra.config import ConfigProvider
from ditto_platform.foundation import Environment


@pytest.mark.parametrize(
    ("environment", "env_override", "git_result", "expected_calls_git"),
    [
        # Env override always wins.
        (
            Environment.PRODUCTION,
            "override-sha",
            "git-sha\n",
            False,
        ),
        # TESTING skips git/lockfile I/O entirely.
        (Environment.TESTING, None, "git-sha\n", False),
        # PRODUCTION reads git HEAD.
        (Environment.PRODUCTION, None, "abc123\n", True),
        # DEVELOPMENT reads git HEAD.
        (Environment.DEVELOPMENT, None, "def456\n", True),
    ],
)
def test_resolve_research_code_version_priority(
    monkeypatch,
    environment: Environment,
    env_override: str | None,
    git_result: str,
    expected_calls_git: bool,
) -> None:
    """Env > git HEAD > None; TESTING never runs git."""
    monkeypatch.delenv("DITTO_RESEARCH_CODE_VERSION", raising=False)
    if env_override is not None:
        monkeypatch.setenv("DITTO_RESEARCH_CODE_VERSION", env_override)

    call_count = {"n": 0}

    class _FakeCompletedProcess:
        def __init__(self, stdout: str) -> None:
            self.stdout = stdout

    def fake_run(*args: object, **kwargs: object) -> object:
        call_count["n"] += 1
        return _FakeCompletedProcess(git_result)

    monkeypatch.setattr(config_module.subprocess, "run", fake_run)

    resolved = config_module._resolve_research_code_version(environment)

    if env_override is not None:
        assert resolved == env_override
        assert call_count["n"] == 0
    elif environment is Environment.TESTING:
        assert resolved is None
        assert call_count["n"] == 0
    else:
        assert resolved == git_result.strip()
        assert call_count["n"] == 1


def test_resolve_research_code_version_falls_back_when_git_unavailable(
    monkeypatch,
) -> None:
    """Missing git binary must silently fall back to None (default settings)."""
    monkeypatch.delenv("DITTO_RESEARCH_CODE_VERSION", raising=False)

    def raise_oserror(*args: object, **kwargs: object) -> object:
        raise OSError("git not found")

    monkeypatch.setattr(config_module.subprocess, "run", raise_oserror)

    assert config_module._resolve_research_code_version(Environment.PRODUCTION) is None


@pytest.mark.parametrize(
    ("environment", "env_override", "lockfile_present", "expected"),
    [
        (Environment.PRODUCTION, "env-hash", True, "env-hash"),
        (Environment.TESTING, None, True, None),
        (Environment.PRODUCTION, None, True, "pixi-content-hash"),
        (Environment.PRODUCTION, None, False, None),
        (Environment.DEVELOPMENT, None, False, None),
    ],
)
def test_resolve_research_environment_lock_hash_priority(
    monkeypatch,
    tmp_path: Path,
    environment: Environment,
    env_override: str | None,
    lockfile_present: bool,
    expected: str | None,
) -> None:
    """Env > pixi.lock sha256 > None; TESTING never reads the lockfile."""
    monkeypatch.delenv("DITTO_RESEARCH_ENVIRONMENT_LOCK_HASH", raising=False)
    if env_override is not None:
        monkeypatch.setenv("DITTO_RESEARCH_ENVIRONMENT_LOCK_HASH", env_override)

    lockfile = tmp_path / "pixi.lock"
    expected_content_hash = hashlib.sha256(b"pixi-content").hexdigest()
    if lockfile_present:
        lockfile.write_bytes(b"pixi-content")
    monkeypatch.setattr(config_module, "_PIXI_LOCK_PATH", lockfile)

    resolved = config_module._resolve_research_environment_lock_hash(environment)

    if expected is None:
        assert resolved is None
    elif env_override is not None:
        assert resolved == env_override
    else:
        assert resolved == expected_content_hash


def test_resolve_research_environment_lock_hash_falls_back_on_oserror(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Missing lockfile must silently fall back to None (default settings)."""
    monkeypatch.delenv("DITTO_RESEARCH_ENVIRONMENT_LOCK_HASH", raising=False)
    monkeypatch.setattr(
        config_module,
        "_PIXI_LOCK_PATH",
        tmp_path / "does-not-exist.lock",
    )

    assert (
        config_module._resolve_research_environment_lock_hash(Environment.PRODUCTION)
        is None
    )


def test_research_execution_settings_provider_combines_resolved_values(
    monkeypatch,
) -> None:
    """Provider must merge resolved code_version + lock_hash into settings."""
    monkeypatch.delenv("DITTO_RESEARCH_CODE_VERSION", raising=False)
    monkeypatch.delenv("DITTO_RESEARCH_ENVIRONMENT_LOCK_HASH", raising=False)

    monkeypatch.setattr(
        config_module,
        "_resolve_research_code_version",
        lambda env: "deadbeef",
    )
    monkeypatch.setattr(
        config_module,
        "_resolve_research_environment_lock_hash",
        lambda env: "cafef00d",
    )

    settings = ConfigProvider().research_execution_settings(
        Environment.PRODUCTION,
    )

    assert settings.code_version == "deadbeef"
    assert settings.environment_lock_hash == "cafef00d"


def test_research_execution_settings_provider_falls_back_to_defaults(
    monkeypatch,
) -> None:
    """When both resolvers return None, the default settings must be used."""
    monkeypatch.delenv("DITTO_RESEARCH_CODE_VERSION", raising=False)
    monkeypatch.delenv("DITTO_RESEARCH_ENVIRONMENT_LOCK_HASH", raising=False)
    monkeypatch.setattr(
        config_module,
        "_resolve_research_code_version",
        lambda env: None,
    )
    monkeypatch.setattr(
        config_module,
        "_resolve_research_environment_lock_hash",
        lambda env: None,
    )

    settings = ConfigProvider().research_execution_settings(Environment.TESTING)

    assert settings.code_version == "unversioned"
    assert settings.environment_lock_hash == (
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )
