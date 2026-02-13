"""
Ditto 统一基础设施层.

包含:
- foundation: 技术基础设施（完全业务无关）
- services: 应用级基础设施服务
"""

from ditto_infra import foundation, services

__all__ = ["foundation", "services"]
