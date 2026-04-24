"""数据源配置校验提供者."""

from __future__ import annotations

import os
from pathlib import Path

from ditto_infra.foundation.config.initializer import (
    ConfigInitProvider,
    InitResult,
    InitScope,
)
from loguru import logger

__all__ = ["DataSourceValidationProvider"]


class DataSourceValidationProvider(ConfigInitProvider):
    """
    数据源配置校验.

    职责：校验数据源所需的配置项（如 API Token）。
    """

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

        # 校验 TUSHARE_TOKEN
        token = os.environ.get("TUSHARE_TOKEN", "")
        if not token.strip():
            errors.append("TUSHARE_TOKEN is not set or empty")

        if errors:
            message = "; ".join(errors)
            logger.error(f"Data source validation failed: {message}")
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
