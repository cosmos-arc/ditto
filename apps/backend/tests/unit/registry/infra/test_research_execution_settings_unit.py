"""Unit tests for checkout-independent research build metadata resolution."""

from __future__ import annotations

import pytest
from ditto_apps.config.runtime import RuntimeConfigurationError
from ditto_apps.registry.infra import config as config_module
from ditto_apps.registry.infra.config import ConfigProvider
from ditto_platform.foundation import Environment


@pytest.mark.parametrize(
    ("environment", "env_override"),
    [
        (Environment.PRODUCTION, "override-sha"),
        (Environment.TESTING, None),
        (Environment.PRODUCTION, None),
        (Environment.DEVELOPMENT, None),
    ],
)
def test_resolve_research_code_version_priority(
    monkeypatch,
    environment: Environment,
    env_override: str | None,
) -> None:
    """Only deployment metadata may supply a research code version."""
    monkeypatch.delenv("DITTO_RESEARCH_CODE_VERSION", raising=False)
    if env_override is not None:
        monkeypatch.setenv("DITTO_RESEARCH_CODE_VERSION", env_override)

    resolved = config_module._resolve_research_code_version(environment)
    assert resolved == env_override


@pytest.mark.parametrize(
    ("environment", "env_override"),
    [
        (Environment.PRODUCTION, "env-hash"),
        (Environment.TESTING, None),
        (Environment.PRODUCTION, None),
        (Environment.DEVELOPMENT, None),
    ],
)
def test_resolve_research_environment_lock_hash_priority(
    monkeypatch,
    environment: Environment,
    env_override: str | None,
) -> None:
    """Only deployment metadata may supply an environment lock hash."""
    monkeypatch.delenv("DITTO_RESEARCH_ENVIRONMENT_LOCK_HASH", raising=False)
    if env_override is not None:
        monkeypatch.setenv("DITTO_RESEARCH_ENVIRONMENT_LOCK_HASH", env_override)

    resolved = config_module._resolve_research_environment_lock_hash(environment)
    assert resolved == env_override


def test_research_execution_settings_provider_combines_resolved_values(
    monkeypatch,
) -> None:
    """Provider must merge resolved code_version + lock_hash into settings."""
    code_version = "d" * 40
    lock_hash = "c" * 64
    monkeypatch.setenv("DITTO_GIT_SHA", code_version)
    monkeypatch.setenv("DITTO_RESEARCH_CODE_VERSION", code_version)
    monkeypatch.setenv("DITTO_RESEARCH_ENVIRONMENT_LOCK_HASH", lock_hash)

    settings = ConfigProvider().research_execution_settings(
        Environment.PRODUCTION,
    )

    assert settings.code_version == code_version
    assert settings.environment_lock_hash == lock_hash


@pytest.mark.parametrize("environment", [Environment.TESTING, Environment.DEVELOPMENT])
def test_research_execution_settings_provider_falls_back_to_defaults(
    monkeypatch,
    environment: Environment,
) -> None:
    """Non-production environments retain explicit deterministic fallbacks."""
    monkeypatch.delenv("DITTO_RESEARCH_CODE_VERSION", raising=False)
    monkeypatch.delenv("DITTO_RESEARCH_ENVIRONMENT_LOCK_HASH", raising=False)

    settings = ConfigProvider().research_execution_settings(environment)

    assert settings.code_version == "unversioned"
    assert settings.environment_lock_hash == (
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )


def test_production_research_execution_settings_require_deployment_provenance(
    monkeypatch,
) -> None:
    """Production must not silently publish testing provenance defaults."""
    for name in (
        "DITTO_GIT_SHA",
        "DITTO_RESEARCH_CODE_VERSION",
        "DITTO_RESEARCH_ENVIRONMENT_LOCK_HASH",
    ):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(RuntimeConfigurationError, match="DITTO_RESEARCH_CODE_VERSION"):
        ConfigProvider().research_execution_settings(Environment.PRODUCTION)


@pytest.mark.parametrize(
    ("git_sha", "code_version", "lock_hash", "expected"),
    [
        ("a" * 40, "unversioned", "b" * 64, "DITTO_RESEARCH_CODE_VERSION"),
        ("a" * 40, "a" * 40, "empty-lock", "DITTO_RESEARCH_ENVIRONMENT_LOCK_HASH"),
        ("a" * 40, "b" * 40, "c" * 64, "DITTO_GIT_SHA"),
    ],
)
def test_production_research_execution_settings_reject_invalid_or_split_identity(
    monkeypatch,
    git_sha: str,
    code_version: str,
    lock_hash: str,
    expected: str,
) -> None:
    """Research and product metadata must bind one full commit and lock digest."""
    monkeypatch.setenv("DITTO_GIT_SHA", git_sha)
    monkeypatch.setenv("DITTO_RESEARCH_CODE_VERSION", code_version)
    monkeypatch.setenv("DITTO_RESEARCH_ENVIRONMENT_LOCK_HASH", lock_hash)

    with pytest.raises(RuntimeConfigurationError, match=expected):
        ConfigProvider().research_execution_settings(Environment.PRODUCTION)
