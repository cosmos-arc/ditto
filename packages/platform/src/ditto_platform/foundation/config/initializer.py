"""配置初始化协调器。"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from loguru import logger

from ditto_platform.foundation.config.errors import ConfigInitError


class InitScope(StrEnum):
    """初始化作用域。"""

    STARTUP = "startup"
    MANUAL = "manual"
    ALWAYS = "always"


@dataclass(frozen=True)
class InitResult:
    """初始化结果。"""

    provider: str
    success: bool
    message: str
    skipped: bool = False


class ConfigInitProvider(Protocol):
    """初始化提供者协议。"""

    @property
    def name(self) -> str:
        """返回初始化提供者名称。"""
        ...

    @property
    def scope(self) -> InitScope:
        """返回初始化作用域。"""
        ...

    def check(self, data_root: Path) -> bool:
        """检查是否需要初始化。"""
        ...

    def initialize(self, data_root: Path) -> InitResult:
        """执行初始化。"""
        ...


class ConfigInitCoordinator:
    """初始化协调器（非单例）。"""

    def __init__(self) -> None:
        self._providers: list[ConfigInitProvider] = []
        self._lock = threading.Lock()

    def register(self, provider: ConfigInitProvider) -> None:
        """注册初始化提供者。"""
        with self._lock:
            self._providers.append(provider)
            logger.debug(
                "Registered config init provider",
                event="config_init_provider_registered",
                provider=provider.name,
            )

    def initialize(
        self,
        scope: InitScope,
        data_root: Path,
        force: bool = False,
        fail_fast: bool = True,
    ) -> dict[str, InitResult]:
        """
        按作用域执行初始化。

        Args:
            scope: 初始化作用域（STARTUP, MANUAL, ALWAYS）。
            data_root: 数据根目录。
            force: 是否强制初始化（忽略 check 结果）。
            fail_fast: STARTUP 场景下是否在失败时立即抛出异常。

        Returns:
            初始化结果映射（provider name -> InitResult）。

        Raises:
            ConfigInitError: STARTUP 场景下有 provider 失败且 fail_fast=True。

        """
        results: dict[str, InitResult] = {}

        with self._lock:
            providers_to_check = self._providers.copy()

        for provider in providers_to_check:
            if scope not in (InitScope.ALWAYS, provider.scope):
                continue

            try:
                need_init = force or provider.check(data_root)

                if not need_init:
                    results[provider.name] = InitResult(
                        provider=provider.name,
                        success=True,
                        message="Configuration already exists",
                        skipped=True,
                    )
                    continue

                result = provider.initialize(data_root)
                results[provider.name] = result

                status_str = "success" if result.success else "failed"
                logger.info(
                    "Config init completed",
                    event="config_init_completed",
                    provider=provider.name,
                    status=status_str,
                    message=result.message,
                )

            except Exception as e:
                logger.error(
                    "Config init failed",
                    event="config_init_failed",
                    provider=provider.name,
                    error=str(e),
                )
                results[provider.name] = InitResult(
                    provider=provider.name,
                    success=False,
                    message=f"{type(e).__name__}: {e}",
                )

        # STARTUP 场景 fail-fast 逻辑
        if fail_fast and scope == InitScope.STARTUP:
            failed = {name: r.message for name, r in results.items() if not r.success}
            if failed:
                raise ConfigInitError(list(failed.keys()), failed)

        return results

    def check(self, data_root: Path) -> dict[str, bool]:
        """检查所有提供者的初始化状态。"""
        status: dict[str, bool] = {}

        with self._lock:
            providers_to_check = self._providers.copy()

        for provider in providers_to_check:
            try:
                need_init = provider.check(data_root)
                status[provider.name] = need_init
            except Exception as e:
                logger.warning(
                    "Config provider check failed",
                    provider=provider.name,
                    error=str(e),
                )
                status[provider.name] = True

        return status


__all__ = [
    "ConfigInitCoordinator",
    "ConfigInitProvider",
    "InitResult",
    "InitScope",
]
