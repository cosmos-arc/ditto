"""Runtime deployment contract tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from ditto_apps.config.runtime import (
    RuntimeConfigurationError,
    RuntimePaths,
    configured_state_root,
    load_runtime_paths,
    resolve_runtime_paths,
)
from ditto_platform.foundation import Environment


def test_production_runtime_paths_are_explicit_and_absolute(tmp_path: Path) -> None:
    """Production resolves all roots from deployment input, not repository layout."""
    config_root = tmp_path / "config"
    state_root = tmp_path / "state"
    cache_root = tmp_path / "cache"

    paths = resolve_runtime_paths(
        Environment.PRODUCTION,
        environ={
            "DITTO_CONFIG_ROOT": str(config_root),
            "DITTO_STATE_ROOT": str(state_root),
            "DITTO_CACHE_ROOT": str(cache_root),
        },
    )

    assert paths == RuntimePaths(
        config_root=config_root,
        state_root=state_root,
        cache_root=cache_root,
    )


@pytest.mark.parametrize(
    "missing_name",
    ["DITTO_CONFIG_ROOT", "DITTO_STATE_ROOT", "DITTO_CACHE_ROOT"],
)
def test_production_runtime_paths_fail_closed_when_missing(
    tmp_path: Path,
    missing_name: str,
) -> None:
    """A production server cannot silently rediscover a checkout layout."""
    environ = {
        "DITTO_CONFIG_ROOT": str(tmp_path / "config"),
        "DITTO_STATE_ROOT": str(tmp_path / "state"),
        "DITTO_CACHE_ROOT": str(tmp_path / "cache"),
    }
    del environ[missing_name]

    with pytest.raises(RuntimeConfigurationError, match=missing_name):
        resolve_runtime_paths(Environment.PRODUCTION, environ=environ)


def test_legacy_data_root_is_mapped_once_to_state_root(tmp_path: Path) -> None:
    """DITTO_DATA_ROOT remains a narrow transition alias for state only."""
    legacy_state = tmp_path / "legacy-data"

    paths = resolve_runtime_paths(
        Environment.PRODUCTION,
        environ={
            "DITTO_CONFIG_ROOT": str(tmp_path / "config"),
            "DITTO_DATA_ROOT": str(legacy_state),
            "DITTO_CACHE_ROOT": str(tmp_path / "cache"),
        },
    )

    assert paths.state_root == legacy_state


def test_original_data_root_alias_survives_one_transition_release(
    tmp_path: Path,
) -> None:
    """The pre-DITTO DATA_ROOT spelling remains a lower-priority state alias."""
    legacy_state = tmp_path / "original-data-root"

    resolved = configured_state_root({"DATA_ROOT": str(legacy_state)})

    assert resolved == legacy_state


def test_explicit_state_root_precedes_legacy_alias(tmp_path: Path) -> None:
    explicit = tmp_path / "state"

    resolved = configured_state_root(
        {
            "DITTO_STATE_ROOT": str(explicit),
            "DITTO_DATA_ROOT": str(tmp_path / "legacy-data"),
            "DATA_ROOT": str(tmp_path / "original-data-root"),
        }
    )

    assert resolved == explicit


def test_production_rejects_relative_runtime_paths(tmp_path: Path) -> None:
    """Deployment paths must not depend on the process working directory."""
    with pytest.raises(RuntimeConfigurationError, match="absolute"):
        resolve_runtime_paths(
            Environment.PRODUCTION,
            environ={
                "DITTO_CONFIG_ROOT": "config",
                "DITTO_STATE_ROOT": str(tmp_path / "state"),
                "DITTO_CACHE_ROOT": str(tmp_path / "cache"),
            },
        )


def test_production_loader_uses_only_explicit_deployment_roots(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The production loader reads exactly the deployment-provided roots."""
    monkeypatch.setenv("DITTO_CONFIG_ROOT", str(tmp_path / "config"))
    monkeypatch.setenv("DITTO_STATE_ROOT", str(tmp_path / "state"))
    monkeypatch.setenv("DITTO_CACHE_ROOT", str(tmp_path / "cache"))

    assert load_runtime_paths(Environment.PRODUCTION) == RuntimePaths(
        config_root=tmp_path / "config",
        state_root=tmp_path / "state",
        cache_root=tmp_path / "cache",
    )


def test_testing_runtime_defaults_to_isolated_writable_roots(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Testing must never default state or cache writes into the checkout."""
    for name in (
        "DITTO_CONFIG_ROOT",
        "DITTO_STATE_ROOT",
        "DITTO_DATA_ROOT",
        "DATA_ROOT",
        "DITTO_CACHE_ROOT",
    ):
        monkeypatch.delenv(name, raising=False)

    paths = load_runtime_paths(Environment.TESTING)

    assert paths.state_root.parent == paths.config_root
    assert paths.cache_root.parent == paths.config_root
    assert paths.state_root.name == "state"
    assert paths.cache_root.name == "cache"


def test_development_runtime_defaults_to_xdg_user_roots(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Development defaults are user-owned and independent of a Git checkout."""
    for name in (
        "DITTO_CONFIG_ROOT",
        "DITTO_STATE_ROOT",
        "DITTO_DATA_ROOT",
        "DATA_ROOT",
        "DITTO_CACHE_ROOT",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg-config"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg-state"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg-cache"))

    paths = load_runtime_paths(Environment.DEVELOPMENT)

    assert paths == RuntimePaths(
        config_root=tmp_path / "xdg-config" / "ditto",
        state_root=tmp_path / "xdg-state" / "ditto",
        cache_root=tmp_path / "xdg-cache" / "ditto",
    )


def test_development_rejects_relative_xdg_roots(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A relative XDG value must not reintroduce process-CWD path semantics."""
    for name in (
        "DITTO_CONFIG_ROOT",
        "DITTO_STATE_ROOT",
        "DITTO_DATA_ROOT",
        "DATA_ROOT",
        "DITTO_CACHE_ROOT",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", "relative-config")

    with pytest.raises(RuntimeConfigurationError, match="XDG_CONFIG_HOME"):
        load_runtime_paths(Environment.DEVELOPMENT)
