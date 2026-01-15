"""
单例管理器模块.

提供通用的单例管理器基类，用于替代 global 变量实现的单例模式。
消除 PLW0603 (global statement) 警告。
"""

from __future__ import annotations

from abc import abstractmethod
from typing import Any, ClassVar

from ditto_foundation.config.paths import XDGPaths


class SingletonManager[T]:
    """
    泛型单例管理器基类.

    使用类属性而非 global 变量实现单例模式，避免 PLW0603 警告。

    子类需要：
    1. 声明类属性 _instance: ClassVar[T | None] = None
    2. 实现 _create_instance() 方法

    示例::

        class MyManager(SingletonManager[MyConfig]):
            _instance: ClassVar[MyConfig | None] = None

            @classmethod
            def _create_instance(cls) -> MyConfig:
                return MyConfig()

        # 使用
        config = MyManager.get()  # 获取或创建实例
        MyManager.reload()        # 重新创建实例
        MyManager.reset()         # 清除实例

    """

    # 子类必须声明 _instance: ClassVar[T | None] = None
    _instance: ClassVar[Any] = None

    @classmethod
    @abstractmethod
    def _create_instance(cls) -> T:
        """
        创建新实例的工厂方法.

        子类必须实现此方法以定义如何创建实例。

        Returns:
            新创建的实例.

        """
        ...

    @classmethod
    def get(cls) -> T:
        """
        获取单例实例.

        如果实例不存在，则创建新实例。

        Returns:
            单例实例.

        """
        if cls._instance is None:
            cls._instance = cls._create_instance()
        return cls._instance

    @classmethod
    def reload(cls) -> T:
        """
        重新加载实例.

        创建新实例并替换当前实例。主要用于配置热更新或测试场景。

        Returns:
            新创建的实例.

        """
        cls._instance = cls._create_instance()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """
        重置实例.

        清除当前实例，下次调用 get() 时会创建新实例。
        主要用于测试场景的状态隔离。
        """
        cls._instance = None


class PathsManager(SingletonManager[XDGPaths]):
    """
    XDGPaths 单例管理器.

    管理全局 XDGPaths 实例的生命周期。
    """

    _instance: ClassVar[XDGPaths | None] = None

    @classmethod
    def _create_instance(cls) -> XDGPaths:
        """创建 XDGPaths 实例并确保目录存在."""
        paths = XDGPaths()
        paths.ensure_all()
        return paths
