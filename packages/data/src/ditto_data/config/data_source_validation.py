"""数据源配置校验提供者."""

from __future__ import annotations

from pathlib import Path

from ditto_platform.foundation import (
    InitResult,
    InitScope,
)
from loguru import logger

from ditto_data.config.data_source import DataSourceSettings

__all__ = ["DataSourceValidationProvider"]


class DataSourceValidationProvider:
    """
    数据源配置校验.

    职责：校验数据源所需的配置项（如 API Token）。
    """

    def __init__(self, settings: DataSourceSettings | None = None) -> None:
        self._settings = settings or DataSourceSettings()

    @property
    def name(self) -> str:
        """返回提供者名称."""
        return "data_source_validation"

    @property
    def scope(self) -> InitScope:
        """返回初始化作用域."""
        return InitScope.STARTUP

    def check(self, data_root: Path) -> bool:
        """检查是否需要初始化."""
        return True

    def initialize(self, data_root: Path) -> InitResult:
        """校验数据源配置项."""
        errors: list[str] = []

        # Validate the already-resolved env > keyring > config value. Reading only
        # os.environ here would reject a valid keyring-backed runtime.
        token = self._settings.tushare_token
        if not token.strip():
            errors.append("TUSHARE_TOKEN is not set or empty")

        if errors:
            message = "; ".join(errors)
            logger.error(
                "Data source validation failed",
                event="data_source_validation_failed",
                message=message,
            )
            return InitResult(
                provider=self.name,
                success=False,
                message=message,
            )

        logger.info("Data source validation passed")
        return InitResult(
            provider=self.name,
            success=True,
            message="All data source config checks passed",
        )
