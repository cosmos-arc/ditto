"""
Application initializer for Ditto system.

Provides unified initialization for:
- Logging system (loguru)
- Directory structure
- Configuration validation
"""

from pathlib import Path
from typing import Any

from loguru import logger

from ditto_foundation.config import get_settings
from ditto_foundation.logging_config import LogConfig, setup_logging


class AppInitializer:
    """
    Application initializer.

    Handles system-wide initialization tasks including logging setup,
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

        # Setup logging
        self._setup_logging(settings)

        # Validate configuration
        errors = self._validate_config(settings)

        self._initialized = True

        result = {
            "status": "initialized",
            "log_initialized": True,
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

    def _setup_logging(self, settings: Any) -> None:
        """Setup logging configuration."""
        log_dir = Path(settings.file_storage.log_root)
        log_config = LogConfig(
            level=settings.system.log_level,
            json_format=settings.is_production,
            enable_console=not settings.is_production,
            enable_file=True,
        )

        setup_logging(
            config=log_config,
            log_dir=log_dir,
            env=settings.system.ditto_env,
        )

    def _validate_config(self, settings: Any) -> list[str]:
        """Validate configuration."""
        # Basic validation - can be extended
        errors = []

        if not settings.data_source.tushare_token:
            errors.append("TUSHARE_TOKEN not set")

        return errors


# Global initializer instance
_initializer: AppInitializer | None = None


def initialize_app() -> dict[str, Any]:
    """
    Initialize application (singleton pattern).

    Returns:
        Initialization status dictionary.

    """
    global _initializer  # noqa: PLW0603

    if _initializer is None:
        _initializer = AppInitializer()

    return _initializer.initialize()


def get_initializer() -> AppInitializer | None:
    """
    Get global initializer instance.

    Returns:
        AppInitializer instance or None.

    """
    return _initializer
