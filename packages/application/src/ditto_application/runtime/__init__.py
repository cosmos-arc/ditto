"""
Runtime — 应用运行时工具模块.

提供 Synchronizer 实现（backtest / paper）等运行时基础设施。
由 builders/ 在装配阶段构建，供 processes/ 在运行时使用。
"""

from __future__ import annotations

from ditto_application.runtime.synchronizer import PaperSynchronizer

__all__ = ["PaperSynchronizer"]
