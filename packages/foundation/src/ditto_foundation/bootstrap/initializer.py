"""
Application initializer for Ditto system.

Provides unified initialization for:
- Observability system (loguru, tracing, metrics)
- Directory structure
- Configuration validation
"""

from pathlib import Path
from typing import Any

from ditto_foundation.config import get_settings
from ditto_foundation.observability import Mode, init
from ditto_foundation.observability.logging import logger


class AppInitializer:
    """
    Application initializer.

    Handles system-wide initialization tasks including observability setup,
    directory creation, and configuration validation.
    """

    def __init__(self) -> None:
        """Initialize AppInitializer."""
        self._initialized = False

    def initialize(self) -> dict[str, Any]:
        """
        Initialize application.

        Returns:
            Dictionary with initialization status.

        """
        if self._initialized:
            logger.warning("Application already initialized")
            return {"status": "already_initialized"}

        settings = get_settings()

        # Create directories
        self._create_directories(settings)

        # Setup observability
        self._setup_observability(settings)

        # Validate configuration
        errors = self._validate_config(settings)

        self._initialized = True

        result = {
            "status": "initialized",
            "observability_initialized": True,
            "directories_created": True,
            "config_valid": len(errors) == 0,
            "config_errors": errors,
        }

        logger.info(
            "application_initialized",
            event="app_init",
            status=result["status"],
            env=settings.system.ditto_env,
        )

        return result

    def _create_directories(self, settings: Any) -> None:
        """Create required directories."""
        directories = [
            Path(settings.file_storage.data_root),
            Path(settings.file_storage.log_root),
            Path(settings.file_storage.backup_root),
            Path(settings.file_storage.temp_root),
        ]

        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)

    def _setup_observability(self, settings: Any) -> None:
        """Set up observability (logging, tracing, metrics)."""
        obs_settings = settings.observability

        # 检查是否启用
        if not obs_settings.enabled:
            logger.info("Observability disabled by configuration")
            return

        # 解析 mode
        mode_mapping: dict[str, Mode | None] = {
            "auto": None,
            "production": Mode.PRODUCTION,
            "development": Mode.DEVELOPMENT,
            "testing": Mode.TESTING,
        }

        configured_mode = mode_mapping.get(obs_settings.mode.lower(), None)
        actual_mode = configured_mode or (
            Mode.PRODUCTION if settings.is_production else Mode.DEVELOPMENT
        )

        # 初始化
        init(
            service_name="ditto",
            environment=settings.system.ditto_env,
            log_level=obs_settings.log_level,
            log_dir=str(settings.file_storage.log_root),
            vm_endpoint=obs_settings.vm_endpoint,
            mode=actual_mode,
        )

    def _validate_config(self, settings: Any) -> list[str]:
        """Validate configuration."""
        # Basic validation - can be extended
        errors: list[str] = []

        if not settings.data_source.tushare_token:
            errors.append("TUSHARE_TOKEN not set")

        return errors


class _AppInitializerRegistry:
    """
    Registry for managing AppInitializer singleton.

    Uses class-level attributes to store singleton state, eliminating
    the need for global statements while maintaining the same API.
    """

    instance: AppInitializer | None = None

    @classmethod
    def get_instance(cls) -> AppInitializer:
        """Get or create the singleton AppInitializer instance."""
        if cls.instance is None:
            cls.instance = AppInitializer()
        return cls.instance

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton instance (for testing purposes)."""
        cls.instance = None

    @classmethod
    def get(cls) -> AppInitializer | None:
        """Get the current instance without creating one."""
        return cls.instance


def initialize_app() -> dict[str, Any]:
    """
    Initialize application (singleton pattern).

    Returns:
        Initialization status dictionary.

    """
    initializer = _AppInitializerRegistry.get_instance()
    return initializer.initialize()


def get_initializer() -> AppInitializer | None:
    """
    Get global initializer instance.

    Returns:
        AppInitializer instance or None.

    """
    return _AppInitializerRegistry.get()


def reset_for_testing() -> None:
    """
    Reset the singleton initializer (for testing purposes only).

    This function allows tests to reset the global state between test runs.
    """
    _AppInitializerRegistry.reset()


# Module-level accessor for backward compatibility with tests
# Exposes registry instance as module-level variable for test access
_initializer = _AppInitializerRegistry.instance
