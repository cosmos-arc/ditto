"""Port 层 Provider 聚合。"""

from dishka import Provider

__all__ = ["get_port_providers"]


def get_port_providers() -> list[Provider]:
    """返回 Port 层所有 Provider（已空，App 层服务迁入 ditto_app.providers）。"""
    return []
