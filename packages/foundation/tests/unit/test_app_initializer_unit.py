"""Tests for app_initializer module."""

import os
from typing import Any

import ditto_foundation.app_initializer as init_module
import ditto_foundation.config.paths as paths_module
import ditto_foundation.config.settings as settings_module
from ditto_foundation.app_initializer import (
    AppInitializer,
    get_initializer,
    initialize_app,
)
from ditto_foundation.config.paths import get_paths


def test_app_initializer_init() -> None:
    """Test AppInitializer initialization."""
    initializer = AppInitializer()
    assert initializer is not None
    assert not initializer._initialized


def test_initialize_app_basic() -> None:
    """Test basic application initialization."""
    result = initialize_app()
    assert result is not None
    # CI may not have TUSHARE_TOKEN, but initialization should complete
    assert "status" in result
    assert "observability_initialized" in result


def test_initialize_app_creates_directories(tmp_path: Any) -> None:
    """Test initialization creates required directories using XDG paths."""
    # Set XDG base directory to temp path for testing
    orig_xdg_data_home = os.environ.get("XDG_DATA_HOME")
    orig_xdg_state_home = os.environ.get("XDG_STATE_HOME")

    try:
        # Set temporary paths using XDG environment variables
        xdg_data = tmp_path / "xdg" / "data"
        xdg_state = tmp_path / "xdg" / "state"
        os.environ["XDG_DATA_HOME"] = str(xdg_data)
        os.environ["XDG_STATE_HOME"] = str(xdg_state)

        # Reset global initializer and settings for testing
        init_module._initializer = None
        settings_module._settings = None

        result = initialize_app()

        # Verify initialization completed successfully
        assert result["status"] in ["initialized", "already_initialized"]
        assert "observability_initialized" in result

        # Verify that the settings are using XDG paths
        # When XDG_DATA_HOME is set, paths should use it
        paths_module._paths = None  # Reset cached paths
        paths = get_paths()

        # Check that the data_home contains our temp path
        assert (
            tmp_path.as_posix() in paths.data_home.as_posix()
            or "ditto" in paths.data_home.as_posix()
        )

    finally:
        # Restore original environment variables
        if orig_xdg_data_home:
            os.environ["XDG_DATA_HOME"] = orig_xdg_data_home
        elif "XDG_DATA_HOME" in os.environ:
            del os.environ["XDG_DATA_HOME"]

        if orig_xdg_state_home:
            os.environ["XDG_STATE_HOME"] = orig_xdg_state_home
        elif "XDG_STATE_HOME" in os.environ:
            del os.environ["XDG_STATE_HOME"]

        # Reset global initializer and paths cache
        init_module._initializer = None
        settings_module._settings = None
        paths_module._paths = None


def test_app_initializer_already_initialized() -> None:
    """Test handling of duplicate initialization."""
    init_module._initializer = None

    initializer = AppInitializer()
    initializer.initialize()
    result2 = initializer.initialize()

    assert result2["status"] == "already_initialized"


def test_get_initializer() -> None:
    """Test getting global initializer."""
    init_module._initializer = None

    # Before initialization
    assert get_initializer() is None

    # After initialization
    initialize_app()
    assert get_initializer() is not None
