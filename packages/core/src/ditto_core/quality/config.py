"""DQ configuration settings."""

from pathlib import Path

from pydantic import Field
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
        DITTO_DQ_REPORT_ENABLED: Enable DQ report generation
        DITTO_DQ_REPORT_PATH: DQ report output path
    """

    model_config = SettingsConfigDict(
        env_prefix="DITTO_DQ_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 环境信息（通过 DI 注入，不参与环境变量读取）
    env: str = Field(
        default="development",
        description="当前环境 (development/testing/production)",
        exclude=True,  # 不参与环境变量读取
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

    @property
    def rules_path(self) -> Path:
        """获取规则目录路径（环境感知）."""
        # 如果 rules_dir 是绝对路径，直接使用
        if Path(self.rules_dir).is_absolute():
            return Path(self.rules_dir)
        # 相对路径：基于用户配置的 rules_dir 解析
        return Path(self.rules_dir)

    def get_rules_paths(self, dataset: str) -> list[Path]:
        """
        获取规则文件路径（优先级顺序）.

        ✅ 无需 env 参数，使用 self.env

        Priority:
            1. Environment-specific: config/{env}/dq_rules/{dataset}.yml
            2. Default: config/default/dq_rules/{dataset}.yml
            3. Package fallback: packages/core/config/dq_rules/{dataset}.yml

        Args:
            dataset: 数据集名称

        Returns:
            规则文件路径列表（按优先级排序）

        """
        paths: list[Path] = []

        # 1. 环境特定（使用 self.env）
        env_rules = Path(f"config/{self.env}/dq_rules/{dataset}.yml")
        if env_rules.exists():
            paths.append(env_rules)

        # 2. 默认（使用 self.env）
        default_rules = self.rules_path / f"{dataset}.yml"
        if default_rules.exists():
            paths.append(default_rules)

        # 3. 包内回退
        package_dir = Path(__file__).parent.parent.parent / "config" / "dq_rules"
        package_rules = package_dir / f"{dataset}.yml"
        if package_rules.exists():
            paths.append(package_rules)

        return paths
