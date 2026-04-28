"""启动配置校验提供者."""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from ditto_infra.foundation.config.initializer import (
    ConfigInitProvider,
    InitResult,
    InitScope,
)


class ConfigValidationProvider(ConfigInitProvider):
    """
    启动配置校验.

    职责：在启动阶段校验通用配置项。
    - DATA_DIR（data_root）：存在且为目录

    注意：数据源特定校验（如 TUSHARE_TOKEN）由对应层的 ValidationProvider 负责。
    """

    @property
    def name(self) -> str:
        """返回初始化提供者名称."""
        return "config_validation"

    @property
    def scope(self) -> InitScope:
        """返回初始化作用域."""
        return InitScope.STARTUP

    def check(self, data_root: Path) -> bool:
        """始终返回 True — 校验在每次启动时都需要执行."""
        return True

    def initialize(self, data_root: Path) -> InitResult:
        """校验通用配置项，返回成功或失败结果."""
        errors: list[str] = []

        # 校验 DATA_DIR
        if not data_root.exists():
            errors.append(f"DATA_DIR does not exist: {data_root}")
        elif not data_root.is_dir():
            errors.append(f"DATA_DIR is not a directory: {data_root}")

        if errors:
            message = "; ".join(errors)
            logger.error(f"Config validation failed: {message}")
            return InitResult(
                provider=self.name,
                success=False,
                message=message,
            )

        logger.info("Config validation passed")
        return InitResult(
            provider=self.name,
            success=True,
            message="All startup config checks passed",
        )
