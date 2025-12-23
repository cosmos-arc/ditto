"""Tests for app_initializer module."""

import os

import ditto_foundation.app_initializer as init_module
import ditto_foundation.config.settings as settings_module
import pytest
from ditto_foundation.app_initializer import (
    AppInitializer,
    get_initializer,
    initialize_app,
)


def test_app_initializer_init() -> None:
    """测试 AppInitializer 初始化."""
    initializer = AppInitializer()
    assert initializer is not None
    assert not initializer._initialized


def test_initialize_app_basic() -> None:
    """测试基础应用初始化."""
    result = initialize_app()
    assert result is not None
    assert "log_initialized" in result
    assert "status" in result


def test_initialize_app_creates_directories(tmp_path: pytest.TempPathFactory) -> None:
    """测试初始化创建必要目录."""
    # Backup original environment variables
    orig_data_root = os.environ.get("DITTO_DATA_ROOT")
    orig_log_root = os.environ.get("DITTO_LOG_ROOT")

    try:
        # Set temporary paths
        os.environ["DITTO_DATA_ROOT"] = str(tmp_path / "data")
        os.environ["DITTO_LOG_ROOT"] = str(tmp_path / "logs")

        # Reset global initializer and settings for testing
        init_module._initializer = None
        settings_module._settings = None

        initialize_app()

        assert (tmp_path / "data").exists()
        assert (tmp_path / "logs").exists()

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
    """测试重复初始化的处理."""
    init_module._initializer = None

    initializer = AppInitializer()
    initializer.initialize()
    result2 = initializer.initialize()

    assert result2["status"] == "already_initialized"


def test_get_initializer() -> None:
    """测试获取全局初始化器."""
    init_module._initializer = None

    # Before initialization
    assert get_initializer() is None

    # After initialization
    initialize_app()
    assert get_initializer() is not None
