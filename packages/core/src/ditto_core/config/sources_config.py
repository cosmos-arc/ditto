"""Configuration management for data sources with environment variable support."""

import os
import re
from pathlib import Path
from typing import Any, ClassVar, Literal, cast

import yaml
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


def substitute_env_vars(value: Any) -> Any:
    """
    Recursively substitute environment variables in configuration values.

    Supports patterns:
    - ${VAR_NAME}: Replace with environment variable
    - ${VAR_NAME:default}: Replace with env var or default if missing

    Args:
        value: Value to process (can be dict, list, or string)

    Returns:
        Value with environment variables substituted

    Raises:
        ValueError: If required environment variable is not found

    """
    if isinstance(value, dict):
        return {k: substitute_env_vars(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [substitute_env_vars(item) for item in value]
    elif isinstance(value, str):
        # Pattern to match ${VAR_NAME} or ${VAR_NAME:default}
        pattern = re.compile(r"\$\{([^}:]+)(?::([^}]*))?\}")

        def replacer(match: re.Match[str]) -> str:
            var_name = match.group(1)
            default_value = match.group(2) if match.group(2) is not None else None

            env_value = os.getenv(var_name)
            if env_value is None:
                if default_value is not None:
                    return default_value
                raise ValueError(
                    f"Environment variable '{var_name}' not found "
                    "and no default provided"
                )

            return env_value

        return pattern.sub(replacer, value)
    else:
        return value


class SourceConfig(BaseSettings):
    """Configuration for a single data source."""

    type: Literal["tushare", "akshare", "csv"] = Field(description="Data source type")
    enabled: bool = Field(default=True, description="Whether this source is enabled")
    config: dict[str, Any] = Field(
        default_factory=dict, description="Source-specific configuration"
    )

    @field_validator("config", mode="before")
    @classmethod
    def substitute_config_env_vars(cls, v: dict[str, Any]) -> dict[str, Any]:
        """Substitute environment variables in config."""
        result = substitute_env_vars(v)
        # We know the result is a dict because substitute_env_vars preserves structure
        return cast("dict[str, Any]", result)


class CollectionConfig(BaseSettings):
    """Configuration for data collection behavior."""

    batch_size: int = Field(
        default=1000, ge=1, le=10000, description="Batch size for data processing"
    )
    max_concurrent_fetches: int = Field(
        default=3, ge=1, le=10, description="Maximum concurrent downloads"
    )
    validate_consistency: bool = Field(
        default=True, description="Whether to validate consistency between sources"
    )
    price_tolerance: float = Field(
        default=0.01,
        ge=0.0,
        le=1.0,
        description="Price difference tolerance for consistency check",
    )
    enable_cross_validation: bool = Field(
        default=True,
        description="Enable cross-validation between primary and backup sources",
    )


class PriceValidationConfig(BaseSettings):
    """Configuration for price validation."""

    enabled: bool = Field(default=True, description="Enable price validation")
    min_price: float = Field(default=0.01, ge=0.0, description="Minimum valid price")
    max_price: float = Field(default=10000, ge=0.0, description="Maximum valid price")
    max_change_pct: float = Field(
        default=20.0, ge=0.0, le=100.0, description="Maximum daily change percentage"
    )


class VolumeValidationConfig(BaseSettings):
    """Configuration for volume validation."""

    enabled: bool = Field(default=True, description="Enable volume validation")
    min_volume: int = Field(default=0, ge=0, description="Minimum valid volume")
    max_volume: int = Field(
        default=1_000_000_000_000, ge=0, description="Maximum valid volume"
    )


class ContinuityValidationConfig(BaseSettings):
    """Configuration for data continuity validation."""

    enabled: bool = Field(default=True, description="Enable continuity validation")
    max_gap_days: int = Field(
        default=7, ge=1, le=365, description="Maximum allowed data gap in days"
    )


class CrossValidationConfig(BaseSettings):
    """Configuration for cross-validation between sources."""

    enabled: bool = Field(default=True, description="Enable cross-validation")
    tolerance: float = Field(
        default=0.01, ge=0.0, le=1.0, description="Price difference tolerance"
    )
    min_samples: int = Field(
        default=10, ge=1, le=1000, description="Minimum samples for validation"
    )


class QualityConfig(BaseSettings):
    """Configuration for data quality validation."""

    price_validation: PriceValidationConfig = Field(
        default_factory=PriceValidationConfig
    )
    volume_validation: VolumeValidationConfig = Field(
        default_factory=VolumeValidationConfig
    )
    continuity_validation: ContinuityValidationConfig = Field(
        default_factory=ContinuityValidationConfig
    )
    cross_validation: CrossValidationConfig = Field(
        default_factory=CrossValidationConfig
    )


class UpdateTaskConfig(BaseSettings):
    """Configuration for a specific update task."""

    enabled: bool = Field(default=True, description="Whether this task is enabled")
    schedule: str = Field(description="Cron schedule for the task")
    retry_count: int = Field(
        default=3, ge=0, le=10, description="Number of retries on failure"
    )


class ETFListUpdateConfig(UpdateTaskConfig):
    """Configuration for ETF list updates."""

    schedule: str = Field(default="0 2 * * *", description="Daily at 2 AM")


class DailyDataUpdateConfig(UpdateTaskConfig):
    """Configuration for daily data updates."""

    schedule: str = Field(default="30 15 * * *", description="Daily at 3:30 PM")
    lookback_days: int = Field(
        default=5, ge=1, le=30, description="Days to look back for updates"
    )


class AdjFactorsUpdateConfig(UpdateTaskConfig):
    """Configuration for adjustment factor updates."""

    schedule: str = Field(default="0 3 * * 0", description="Weekly on Sunday at 3 AM")
    force_update: bool = Field(default=False, description="Force update existing data")


class UpdateStrategyConfig(BaseSettings):
    """Configuration for data update strategies."""

    etf_list: ETFListUpdateConfig = Field(default_factory=ETFListUpdateConfig)
    daily_data: DailyDataUpdateConfig = Field(default_factory=DailyDataUpdateConfig)
    adj_factors: AdjFactorsUpdateConfig = Field(default_factory=AdjFactorsUpdateConfig)


class SourcesConfig(BaseSettings):
    """Main configuration for all data sources."""

    primary: SourceConfig = Field(description="Primary data source configuration")
    backup: SourceConfig = Field(description="Backup data source configuration")
    test: SourceConfig = Field(description="Test data source configuration")
    collection: CollectionConfig = Field(default_factory=CollectionConfig)
    quality: QualityConfig = Field(default_factory=QualityConfig)
    update_strategy: UpdateStrategyConfig = Field(default_factory=UpdateStrategyConfig)

    # Class variable for default config file path
    DEFAULT_CONFIG_PATH: ClassVar[Path] = Path(__file__).parent / "sources.yaml"

    def get_enabled_sources(self) -> dict[str, SourceConfig]:
        """
        Get all enabled data sources.

        Returns:
            Dictionary mapping source names to their configurations

        """
        enabled = {}
        for name in ["primary", "backup", "test"]:
            source_config = getattr(self, name)
            if source_config.enabled:
                enabled[name] = source_config
        return enabled

    def get_source_config(self, source_name: str) -> SourceConfig | None:
        """
        Get configuration for a specific source.

        Args:
            source_name: Name of the source (primary, backup, or test)

        Returns:
            Source configuration or None if not found

        """
        return getattr(self, source_name, None)

    @classmethod
    def load_from_dict(cls, data: dict[str, Any]) -> "SourcesConfig":
        """
        Load configuration from a dictionary.

        Args:
            data: Configuration dictionary

        Returns:
            SourcesConfig instance

        """
        # Substitute environment variables in the entire config
        data = substitute_env_vars(data)
        return cls(**data)


def load_sources_config(config_path: str | Path | None = None) -> SourcesConfig:
    """
    Load sources configuration from YAML file.

    Args:
        config_path: Path to config file. If None, uses default path.

    Returns:
        SourcesConfig instance

    Raises:
        FileNotFoundError: If config file doesn't exist
        ValueError: If required environment variables are missing

    """
    if config_path is None:
        config_path = SourcesConfig.DEFAULT_CONFIG_PATH

    config_file = Path(config_path)
    if not config_file.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_file}")

    # Load and parse YAML
    with config_file.open("r", encoding="utf-8") as f:
        config_data = yaml.safe_load(f)

    if not config_data:
        raise ValueError(f"Configuration file is empty: {config_file}")

    return SourcesConfig.load_from_dict(config_data)


# Create a global config instance
_sources_config: SourcesConfig | None = None


def get_sources_config() -> SourcesConfig:
    """
    Get the global sources configuration instance.

    Loads the configuration on first call and caches it.

    Returns:
        SourcesConfig instance

    """
    global _sources_config  # noqa: PLW0603 - Intentional singleton pattern

    if _sources_config is None:
        _sources_config = load_sources_config()

    return _sources_config


def reload_sources_config(config_path: str | Path | None = None) -> SourcesConfig:
    """
    Reload the sources configuration.

    Args:
        config_path: Optional path to config file. If None, uses default.

    Returns:
        New SourcesConfig instance

    """
    global _sources_config  # noqa: PLW0603 - Intentional singleton pattern
    _sources_config = load_sources_config(config_path)
    return _sources_config
