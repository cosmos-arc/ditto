"""
Ingestion Service 模块.

本模块提供数据摄取相关的服务层组件。
"""

from ditto_port.services.ingestion.factory import create_coordinator

__all__ = ["create_coordinator"]
