"""DQ configuration settings."""

from pathlib import Path

from ditto_platform.foundation.config.project_root import find_project_root
from pydantic import BaseModel, ConfigDict, Field


class DQSettings(BaseModel):
    """DQ configuration settings (pure model)."""

    model_config = ConfigDict(extra="ignore")

    environment: str = Field(
        default="development",
        description="当前环境 (development/testing/production)",
    )

    # Switches
    l1_enabled: bool = True
    l2_enabled: bool = True
    l3_enabled: bool = True

    # Rules directory
    rules_dir: str = "config/default/dq_rules"

    # Quarantine
    quarantine_enabled: bool = True

    # Reports
    report_enabled: bool = True
    report_path: str = "data/reports/dq"

    config_root: Path = Field(default_factory=find_project_root)

    @property
    def rules_path(self) -> Path:
        """获取规则目录路径。"""
        path = Path(self.rules_dir)
        if path.is_absolute():
            return path
        return self.config_root / path

    def get_rules_paths(self, dataset: str) -> list[Path]:
        """获取规则文件路径（按优先级）。"""
        paths: list[Path] = []

        dq_path = self.config_root / "config" / self.environment / "dq_rules"
        env_rules = dq_path / f"{dataset}.yml"
        if env_rules.exists():
            paths.append(env_rules)

        default_rules = self.rules_path / f"{dataset}.yml"
        if default_rules.exists():
            paths.append(default_rules)

        package_dir = Path(__file__).parent.parent.parent / "config" / "dq_rules"
        package_rules = package_dir / f"{dataset}.yml"
        if package_rules.exists():
            paths.append(package_rules)

        return paths


__all__ = ["DQSettings"]
