"""
配置初始化协调框架.

提供统一的配置初始化机制，支持多种初始化作用域和提供者注册。
"""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from loguru import logger

# ==================== 初始化作用域 ====================


class InitScope(str, Enum):
    """
    初始化作用域.

    定义配置初始化的触发时机：
    - STARTUP: 应用启动时自动检测并初始化
    - MANUAL: 用户手动触发（如执行 CLI 命令）
    - ALWAYS: 强制初始化所有提供者，忽略作用域限制
    """

    STARTUP = "startup"
    MANUAL = "manual"
    ALWAYS = "always"


# ==================== 初始化结果 ====================


@dataclass(frozen=True)
class InitResult:
    """
    配置初始化结果.

    Attributes:
        provider: 提供者名称
        success: 是否成功初始化
        message: 结果消息
        skipped: 是否跳过初始化（配置已存在）

    """

    provider: str
    success: bool
    message: str
    skipped: bool = False


# ==================== 配置初始化提供者 ====================


class ConfigInitProvider(ABC):
    """
    配置初始化提供者抽象基类.

    提供者负责：
    1. 检查配置是否已存在（check）
    2. 执行初始化操作（initialize）

    所有提供者必须实现这两个方法。
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """
        返回提供者名称.

        Returns:
            提供者唯一标识符

        """
        ...

    @property
    @abstractmethod
    def scope(self) -> InitScope:
        """
        返回初始化作用域.

        Returns:
            提供者的初始化作用域

        """
        ...

    @abstractmethod
    def check(self, data_root: Path) -> bool:
        """
        检查配置是否已存在.

        Args:
            data_root: 数据根目录

        Returns:
            True 表示需要初始化，False 表示已存在

        """
        ...

    @abstractmethod
    def initialize(self, data_root: Path) -> InitResult:
        """
        执行初始化操作.

        Args:
            data_root: 数据根目录

        Returns:
            初始化结果

        """
        ...


# ==================== 配置初始化协调器 ====================


class ConfigInitCoordinator:
    """
    配置初始化协调器.

    负责管理多个配置初始化提供者，根据作用域协调初始化流程。

    功能：
    1. 注册配置初始化提供者
    2. 根据作用域触发初始化
    3. 检查配置状态
    4. 处理初始化异常

    线程安全：使用锁保护提供者列表和初始化操作。
    """

    def __init__(self) -> None:
        """初始化协调器."""
        self._providers: list[ConfigInitProvider] = []
        self._lock = threading.Lock()

    def register(self, provider: ConfigInitProvider) -> None:
        """
        注册配置初始化提供者.

        Args:
            provider: 要注册的提供者

        """
        with self._lock:
            self._providers.append(provider)
            logger.debug(f"Registered config init provider: {provider.name}")

    def initialize(
        self,
        scope: InitScope,
        data_root: Path,
        force: bool = False,
    ) -> dict[str, InitResult]:
        """
        初始化配置.

        根据 scope 参数选择性地初始化提供者：
        - InitScope.STARTUP: 只初始化 scope=STARTUP 的提供者
        - InitScope.MANUAL: 只初始化 scope=MANUAL 的提供者
        - InitScope.ALWAYS: 初始化所有提供者

        如果 force=True，则忽略 check() 结果，强制初始化。

        Args:
            scope: 初始化作用域
            data_root: 数据根目录
            force: 是否强制初始化（忽略 check 结果）

        Returns:
            {provider.name: InitResult} 映射

        """
        results: dict[str, InitResult] = {}

        with self._lock:
            providers_to_check = self._providers.copy()

        for provider in providers_to_check:
            # 过滤作用域
            if scope not in (InitScope.ALWAYS, provider.scope):
                continue

            try:
                # 检查是否需要初始化
                need_init = force or provider.check(data_root)

                if not need_init:
                    results[provider.name] = InitResult(
                        provider=provider.name,
                        success=True,
                        message="Configuration already exists",
                        skipped=True,
                    )
                    continue

                # 执行初始化
                result = provider.initialize(data_root)
                results[provider.name] = result

                status_str = "success" if result.success else "failed"
                logger.info(
                    f"Config init {provider.name}: {status_str} - {result.message}"
                )

            except Exception as e:
                # 捕获异常，记录日志，返回失败结果
                logger.error(f"Config init {provider.name} failed: {e}")
                results[provider.name] = InitResult(
                    provider=provider.name,
                    success=False,
                    message=f"{type(e).__name__}: {e}",
                )

        return results

    def check(self, data_root: Path) -> dict[str, bool]:
        """
        检查所有提供者的配置状态.

        Args:
            data_root: 数据根目录

        Returns:
            {provider.name: need_init} 映射
            True 表示需要初始化，False 表示已存在

        """
        status: dict[str, bool] = {}

        with self._lock:
            providers_to_check = self._providers.copy()

        for provider in providers_to_check:
            try:
                need_init = provider.check(data_root)
                status[provider.name] = need_init
            except Exception as e:
                logger.warning(f"Check {provider.name} failed: {e}")
                # 检查失败时假设需要初始化
                status[provider.name] = True

        return status


# ==================== 单例注册表 ====================


class _CoordinatorRegistry:
    """
    配置初始化协调器单例注册表.

    使用类级别属性存储单例状态，避免使用 global 语句，
    同时保持相同的 API。
    """

    instance: ConfigInitCoordinator | None = None
    lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> ConfigInitCoordinator:
        """
        获取或创建配置初始化协调器单例.

        Returns:
            全局唯一的协调器实例

        """
        if cls.instance is None:
            with cls.lock:
                # 双重检查锁定模式
                if cls.instance is None:
                    cls.instance = ConfigInitCoordinator()
        return cls.instance

    @classmethod
    def reset(cls) -> None:
        """
        重置协调器单例（仅用于测试）.

        警告：此方法仅用于测试环境，不要在生产代码中调用。
        """
        with cls.lock:
            cls.instance = None


def get_config_coordinator() -> ConfigInitCoordinator:
    """
    获取配置初始化协调器单例.

    Returns:
        全局唯一的协调器实例

    """
    return _CoordinatorRegistry.get_instance()


def reset_coordinator_for_testing() -> None:
    """
    重置协调器单例（仅用于测试）.

    警告：此函数仅用于测试环境，不要在生产代码中调用。
    """
    _CoordinatorRegistry.reset()
