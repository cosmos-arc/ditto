"""Unit tests for AppInitializer."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from ditto_foundation.bootstrap import (
    AppInitializer,
    get_initializer,
    initialize_app,
    reset_for_testing,
)
from ditto_foundation.config import get_settings
from pytest_mock import MockerFixture


@pytest.mark.unit
class TestAppInitializer:
    """Tests for AppInitializer class."""

    def test_initialization_starts_uninitialized(self) -> None:
        """Test that AppInitializer starts in uninitialized state."""
        initializer = AppInitializer()
        # Cannot directly access _initialized, but can test behavior
        result = initializer._validate_config(get_settings())
        # If this works, initializer was created successfully
        assert isinstance(result, list)

    def test_initialize_returns_status_dict(self, mocker: MockerFixture) -> None:
        """Test initialize returns status dictionary."""
        initializer = AppInitializer()

        # Mock _create_directories and _setup_observability
        mocker.patch.object(initializer, "_create_directories")
        mocker.patch.object(initializer, "_setup_observability")

        result = initializer.initialize()

        assert isinstance(result, dict)
        assert "status" in result
        assert "observability_initialized" in result
        assert "directories_created" in result
        assert "config_valid" in result
        assert "config_errors" in result

    def test_initialize_creates_directories(self, mocker: MockerFixture) -> None:
        """Test initialize calls _create_directories."""
        initializer = AppInitializer()
        mock_create = mocker.patch.object(initializer, "_create_directories")
        mocker.patch.object(initializer, "_setup_observability")

        initializer.initialize()

        mock_create.assert_called_once()

    def test_initialize_sets_up_observability(self, mocker: MockerFixture) -> None:
        """Test initialize calls _setup_observability."""
        initializer = AppInitializer()
        mock_setup = mocker.patch.object(initializer, "_setup_observability")
        mocker.patch.object(initializer, "_create_directories")

        initializer.initialize()

        mock_setup.assert_called_once()

    def test_initialize_twice_returns_already_initialized(
        self, mocker: MockerFixture
    ) -> None:
        """Test that calling initialize twice returns already_initialized status."""
        initializer = AppInitializer()
        mocker.patch.object(initializer, "_create_directories")
        mocker.patch.object(initializer, "_setup_observability")

        # First call
        result1 = initializer.initialize()
        assert result1["status"] == "initialized"

        # Second call
        result2 = initializer.initialize()
        assert result2["status"] == "already_initialized"

    def test_create_directories_makes_required_paths(
        self, mocker: MockerFixture, tmp_path: Path
    ) -> None:
        """Test _create_directories creates all required directories."""
        initializer = AppInitializer()

        # Create mock settings with tmp_path
        mock_settings = MagicMock()
        mock_settings.file_storage.data_root = str(tmp_path / "data")
        mock_settings.file_storage.log_root = str(tmp_path / "logs")
        mock_settings.file_storage.backup_root = str(tmp_path / "backup")
        mock_settings.file_storage.temp_root = str(tmp_path / "temp")

        initializer._create_directories(mock_settings)

        # Verify all directories were created
        assert (tmp_path / "data").exists()
        assert (tmp_path / "logs").exists()
        assert (tmp_path / "backup").exists()
        assert (tmp_path / "temp").exists()

    def test_create_directories_with_existing_directories(
        self, mocker: MockerFixture, tmp_path: Path
    ) -> None:
        """Test _create_directories handles existing directories gracefully."""
        initializer = AppInitializer()

        # Pre-create some directories
        data_dir = tmp_path / "data"
        data_dir.mkdir(parents=True)

        mock_settings = MagicMock()
        mock_settings.file_storage.data_root = str(data_dir)
        mock_settings.file_storage.log_root = str(tmp_path / "logs")
        mock_settings.file_storage.backup_root = str(tmp_path / "backup")
        mock_settings.file_storage.temp_root = str(tmp_path / "temp")

        # Should not raise error
        initializer._create_directories(mock_settings)

        assert data_dir.exists()

    def test_setup_observability_calls_init(
        self, mocker: MockerFixture, tmp_path: Path
    ) -> None:
        """Test _setup_observability calls observability.init."""
        initializer = AppInitializer()

        # Create mock settings
        mock_settings = MagicMock()
        mock_settings.observability.log_level = "INFO"
        mock_settings.observability.vm_endpoint = "http://localhost:4318"
        mock_settings.file_storage.log_root = str(tmp_path / "logs")
        mock_settings.system.ditto_env = MagicMock()
        mock_settings.system.ditto_env.value = "testing"

        # Mock observability.init
        mock_init = mocker.patch("ditto_foundation.bootstrap.initializer.init")

        initializer._setup_observability(mock_settings)

        # Verify init was called with correct parameters
        mock_init.assert_called_once()
        call_kwargs = mock_init.call_args.kwargs
        assert call_kwargs["service_name"] == "ditto"
        assert call_kwargs["environment"] == "testing"
        assert call_kwargs["log_level"] == "INFO"
        assert call_kwargs["vm_endpoint"] == "http://localhost:4318"

    def test_validate_config_with_missing_token(self, mocker: MockerFixture) -> None:
        """Test _validate_config returns error when token is missing."""
        initializer = AppInitializer()

        mock_settings = MagicMock()
        mock_settings.data_source.tushare_token = ""

        errors = initializer._validate_config(mock_settings)

        assert len(errors) > 0
        assert any("TUSHARE_TOKEN" in err for err in errors)

    def test_validate_config_with_none_token(self, mocker: MockerFixture) -> None:
        """Test _validate_config returns error when token is None."""
        initializer = AppInitializer()

        mock_settings = MagicMock()
        mock_settings.data_source.tushare_token = None

        errors = initializer._validate_config(mock_settings)

        assert len(errors) > 0
        assert any("TUSHARE_TOKEN" in err for err in errors)

    def test_validate_config_with_valid_token(self, mocker: MockerFixture) -> None:
        """Test _validate_config returns no errors with valid token."""
        initializer = AppInitializer()

        mock_settings = MagicMock()
        mock_settings.data_source.tushare_token = "valid_token_12345"

        errors = initializer._validate_config(mock_settings)

        assert len(errors) == 0


@pytest.mark.unit
class TestAppInitializerRegistry:
    """Tests for _AppInitializerRegistry singleton behavior."""

    def test_get_instance_returns_singleton(self) -> None:
        """Test get_instance returns same instance on multiple calls."""
        from ditto_foundation.bootstrap.initializer import _AppInitializerRegistry

        # Reset first
        _AppInitializerRegistry.reset()

        instance1 = _AppInitializerRegistry.get_instance()
        instance2 = _AppInitializerRegistry.get_instance()

        assert instance1 is instance2

    def test_get_returns_none_when_no_instance(self) -> None:
        """Test get returns None when no instance exists."""
        from ditto_foundation.bootstrap.initializer import _AppInitializerRegistry

        # Reset first
        _AppInitializerRegistry.reset()

        instance = _AppInitializerRegistry.get()

        assert instance is None

    def test_get_returns_existing_instance(self) -> None:
        """Test get returns existing instance without creating new one."""
        from ditto_foundation.bootstrap.initializer import _AppInitializerRegistry

        # Reset first
        _AppInitializerRegistry.reset()

        # Create instance
        instance1 = _AppInitializerRegistry.get_instance()

        # Get should return same instance
        instance2 = _AppInitializerRegistry.get()

        assert instance1 is instance2

    def test_reset_clears_instance(self) -> None:
        """Test reset clears the singleton instance."""
        from ditto_foundation.bootstrap.initializer import _AppInitializerRegistry

        # Create instance
        instance1 = _AppInitializerRegistry.get_instance()
        assert instance1 is not None

        # Reset
        _AppInitializerRegistry.reset()

        # Get should create new instance
        instance2 = _AppInitializerRegistry.get_instance()

        assert instance1 is not instance2


@pytest.mark.unit
class TestModuleFunctions:
    """Tests for module-level functions."""

    def test_initialize_app_returns_status_dict(self, mocker: MockerFixture) -> None:
        """Test initialize_app returns status dictionary."""
        from ditto_foundation.bootstrap.initializer import (
            _AppInitializerRegistry,
        )

        # Reset first
        _AppInitializerRegistry.reset()

        # Mock the initialize method
        mocker.patch.object(
            AppInitializer,
            "initialize",
            return_value={
                "status": "initialized",
                "observability_initialized": True,
                "directories_created": True,
                "config_valid": True,
                "config_errors": [],
            },
        )

        result = initialize_app()

        assert isinstance(result, dict)
        assert "status" in result

    def test_initialize_app_uses_singleton(self, mocker: MockerFixture) -> None:
        """Test initialize_app uses singleton pattern."""
        from ditto_foundation.bootstrap.initializer import (
            _AppInitializerRegistry,
        )

        # Reset first
        _AppInitializerRegistry.reset()

        mocker.patch.object(
            AppInitializer,
            "initialize",
            return_value={"status": "initialized"},
        )

        # First call
        result1 = initialize_app()
        assert result1["status"] == "initialized"

        # Get instance should return same instance
        instance = _AppInitializerRegistry.get()
        assert instance is not None

    def test_get_initializer_returns_instance(self) -> None:
        """Test get_initializer returns AppInitializer instance."""
        from ditto_foundation.bootstrap.initializer import (
            _AppInitializerRegistry,
        )

        # Reset first
        _AppInitializerRegistry.reset()

        # Create instance
        _AppInitializerRegistry.get_instance()

        result = get_initializer()

        assert result is not None
        assert isinstance(result, AppInitializer)

    def test_get_initializer_returns_none_when_not_initialized(self) -> None:
        """Test get_initializer returns None when not initialized."""
        from ditto_foundation.bootstrap.initializer import (
            _AppInitializerRegistry,
        )

        # Reset first
        _AppInitializerRegistry.reset()

        result = get_initializer()

        assert result is None

    def test_reset_for_testing_clears_singleton(self) -> None:
        """Test reset_for_testing clears the singleton."""
        # Create instance
        initialize_app()
        assert get_initializer() is not None

        # Reset
        reset_for_testing()

        # Should return None after reset
        assert get_initializer() is None


@pytest.mark.unit
class TestObservabilityIntegration:
    """Tests for observability integration."""

    def test_initialize_calls_detect_runtime_flags(self, mocker: MockerFixture) -> None:
        """Test initialize uses ObservabilityConfig.detect_runtime_flags."""
        initializer = AppInitializer()

        # Mock settings
        mock_settings = MagicMock()
        mock_settings.observability.log_level = "INFO"
        mock_settings.observability.vm_endpoint = "http://localhost:4318"
        mock_settings.file_storage.log_root = "/tmp/logs"
        mock_settings.system.ditto_env = MagicMock()
        mock_settings.system.ditto_env.value = "testing"

        # Mock detect_runtime_flags
        mock_detect = mocker.patch(
            "ditto_foundation.bootstrap.initializer.ObservabilityConfig.detect_runtime_flags",
            return_value={
                "pytest_running": True,
                "assertions_enabled": False,
                "verbose_logging": False,
            },
        )

        # Mock init to avoid actual initialization
        mocker.patch("ditto_foundation.bootstrap.initializer.init")

        initializer._setup_observability(mock_settings)

        # Verify detect_runtime_flags was called
        mock_detect.assert_called_once_with(mock_settings.system.ditto_env)

    def test_initialize_with_pytest_running_flag(self, mocker: MockerFixture) -> None:
        """Test initialize passes pytest_running flag to init."""
        initializer = AppInitializer()

        mock_settings = MagicMock()
        mock_settings.observability.log_level = "INFO"
        mock_settings.observability.vm_endpoint = "http://localhost:4318"
        mock_settings.file_storage.log_root = "/tmp/logs"
        mock_settings.system.ditto_env = MagicMock()
        mock_settings.system.ditto_env.value = "testing"

        # Mock detect_runtime_flags to return pytest_running=True
        mocker.patch(
            "ditto_foundation.bootstrap.initializer.ObservabilityConfig.detect_runtime_flags",
            return_value={
                "pytest_running": True,
                "assertions_enabled": True,
                "verbose_logging": False,
            },
        )

        mock_init = mocker.patch("ditto_foundation.bootstrap.initializer.init")

        initializer._setup_observability(mock_settings)

        # Verify init received pytest_running=True
        call_kwargs = mock_init.call_args.kwargs
        assert call_kwargs["pytest_running"] is True
        assert call_kwargs["assertions_enabled"] is True
