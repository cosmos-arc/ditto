"""DQ configuration settings."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class DQSettings(BaseSettings):
    """
    DQ configuration settings.

    Environment variables:
        DITTO_DQ_L1_ENABLED: Enable L1 technical checks
        DITTO_DQ_L2_ENABLED: Enable L2 business checks
        DITTO_DQ_L3_ENABLED: Enable L3 statistical checks
        DITTO_DQ_RULES_DIR: DQ rules directory path
        DITTO_DQ_QUARANTINE_ENABLED: Enable quarantine feature
        DITTO_DQ_QUARANTINE_PATH: Quarantine data path
        DITTO_DQ_REPORT_ENABLED: Enable DQ report generation
        DITTO_DQ_REPORT_PATH: DQ report output path
    """

    model_config = SettingsConfigDict(
        env_prefix="DITTO_DQ_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Switches
    l1_enabled: bool = True
    l2_enabled: bool = True
    l3_enabled: bool = True

    # Rules directory
    rules_dir: str = "config/default/dq_rules"

    # Quarantine
    quarantine_enabled: bool = True
    quarantine_path: str = "data/quarantine"

    # Reports
    report_enabled: bool = True
    report_path: str = "data/reports/dq"

    @property
    def rules_path(self) -> Path:
        """Get rules directory path."""
        return Path(self.rules_dir)

    def get_rules_paths(self, dataset: str, env: str | None = None) -> list[Path]:
        """
        Get rule file loading paths (priority from high to low).

        Priority:
            1. Environment-specific: config/{env}/dq_rules/{dataset}.yml
            2. Default: config/default/dq_rules/{dataset}.yml
            3. Package fallback: packages/core/config/dq_rules/{dataset}.yml

        Args:
            dataset: Dataset name
            env: Environment name (development/testing/production)

        Returns:
            List of rule file paths (existing only, priority order)

        """
        if env is None:
            # Import here to avoid circular dependency
            from ditto_foundation.config import get_settings  # noqa: PLC0415

            settings = get_settings()
            env = settings.system.ditto_env.value

        paths: list[Path] = []

        # 1. Environment-specific
        env_rules = Path(f"config/{env}/dq_rules/{dataset}.yml")
        if env_rules.exists():
            paths.append(env_rules)

        # 2. Default
        default_rules = self.rules_path / f"{dataset}.yml"
        if default_rules.exists():
            paths.append(default_rules)

        # 3. Package fallback
        package_dir = Path(__file__).parent.parent.parent / "config" / "dq_rules"
        package_rules = package_dir / f"{dataset}.yml"
        if package_rules.exists():
            paths.append(package_rules)

        return paths
