"""Tests for app_initializer module."""

import os
from pathlib import Path
from typing import Any

import ditto_foundation.app_initializer as init_module
import ditto_foundation.config.settings as settings_module
from ditto_foundation.app_initializer import (
    AppInitializer,
    get_initializer,
    initialize_app,
)


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
    """Test initialization creates required directories."""
    # Backup original environment variables
    orig_data_root = os.environ.get("DITTO_DATA_ROOT")
    orig_log_root = os.environ.get("DITTO_LOG_ROOT")

    try:
        # Set temporary paths using pathlib
        data_path = tmp_path / "data"
        log_path = tmp_path / "logs"
        os.environ["DITTO_DATA_ROOT"] = str(data_path)
        os.environ["DITTO_LOG_ROOT"] = str(log_path)

        # Reset global initializer and settings for testing
        init_module._initializer = None
        settings_module._settings = None

        initialize_app()

        # Check if directories exist
        assert Path(data_path).exists()
        assert Path(log_path).exists()

    finally:
        # Restore original environment variables
        if orig_data_root:
            os.environ["DITTO_DATA_ROOT"] = orig_data_root
        elif "DITTO_DATA_ROOT" in os.environ:
            del os.environ["DITTO_DATA_ROOT"]

        if orig_log_root:
            os.environ["DITTO_LOG_ROOT"] = orig_log_root
        elif "DITTO_LOG_ROOT" in os.environ:
            del os.environ["DITTO_LOG_ROOT"]

        # Reset global initializer
        init_module._initializer = None
        settings_module._settings = None


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
