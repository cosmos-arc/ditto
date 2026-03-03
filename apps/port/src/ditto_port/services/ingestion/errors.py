"""
摄取专用错误类型.

此模块保留用于向后兼容，新代码应使用 ditto_port.errors 中的异常类。
"""

from __future__ import annotations

from ditto_port.errors import SourceFetchError

__all__ = ["SourceFetchError"]
