"""
基础设施组件注册（已迁移到 ConfigProvider）.

⚠️ AppProvider 已废弃，所有配置相关 Provider 已迁移到 ConfigProvider.

保留此文件是为了向后兼容，未来版本可能移除。
"""

from dishka import Provider, Scope

__all__ = ["AppProvider"]


class AppProvider(Provider):
    """
    基础设施组件 Provider（已废弃）.

    ⚠️ 所有功能已迁移到 ConfigProvider。
    此 Provider 保留为空类，用于向后兼容。

    迁移指南：
        旧方式: AppProvider + DataHubProvider
        新方式: ConfigProvider + DataHubProvider
    """

    scope = Scope.APP
    # 所有 provider 方法已迁移到 ConfigProvider
