"""
Ditto 共享模块.

提供跨项目的共享类型、配置和工具
"""

__version__ = "0.1.0"
__author__ = "Ditto Team"

# Export app initializer
from ditto_foundation.app_initializer import AppInitializer, initialize_app

__all__ = ["AppInitializer", "initialize_app"]
