"""
Application initializer for Ditto system.

Provides unified initialization for:
- Observability system (loguru, tracing, metrics)
- Directory structure
- Configuration validation
"""

from pathlib import Path
from typing import Any

from loguru import logger

from ditto_foundation.config import get_settings
from ditto_foundation.observability import Mode, init


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
        """Setup observability (logging, tracing, metrics)."""
        # Determine mode based on environment
        mode = Mode.PRODUCTION if settings.is_production else Mode.DEVELOPMENT

        # Initialize observability
        init(
            service_name="ditto",
            environment=settings.system.ditto_env,
            log_level=settings.system.log_level,
            log_dir=str(settings.file_storage.log_root),
            mode=mode,
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
