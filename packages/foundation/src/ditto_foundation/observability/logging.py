"""
日志配置模块.

基于 loguru 的结构化日志配置，支持多环境和 JSON 格式输出.
"""

import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import orjson
from loguru import logger as _logger

from .config import Mode, ObservabilityConfig


def _build_log_record(record: dict[str, Any] | Any) -> dict[str, Any]:
    """
    构建日志记录字典.

    Args:
    ----
        record: loguru 日志记录

    Returns:
    -------
        dict[str, Any]: 包含所有日志字段的字典

    """
    rec = record["record"]
    extra = record["extra"]

    # 基本字段
    log_entry = {
        "timestamp": datetime.fromtimestamp(rec["time"].timestamp()).isoformat(),
        "level": rec["level"].name,
        "logger": rec["name"],
        "function": rec["function"],
        "line": rec["line"],
        "message": rec["message"],
    }

    # 添加所有额外字段（包括 event 和 trace_id）
    log_entry.update(extra)

    # 添加异常信息
    if rec["exception"]:
        exc = rec["exception"]
        log_entry["exception"] = {
            "type": exc.type.__name__,
            "value": str(exc.value),
            "traceback": str(exc.traceback),
        }

    return log_entry


def _json_formatter(record: dict[str, Any] | Any) -> str:
    """
    JSON 格式化器，用于生产环境日志.

    Args:
    ----
        record: loguru 日志记录

    Returns:
    -------
        str: JSON 格式的日志字符串

    """
    log_entry = _build_log_record(record)
    return orjson.dumps(log_entry).decode("utf-8") + "\n"


def configure_logging(config: ObservabilityConfig, mode: Mode) -> None:
    """
    配置 Loguru 日志系统.

    Args:
    ----
        config: 可观测性配置
        mode: 运行模式

    """
    # 移除默认 handler
    _logger.remove()

    # 静默模式：不添加任何 handler
    if mode.is_silent():
        return

    # 使用 XDG Base Directory 规范获取日志目录
    # 如果 config.log_dir 是默认值 "logs"，使用 XDGPaths
    if config.log_dir == "logs":
        from ditto_foundation.config.paths import (  # noqa: PLC0415 - circular import avoidance
            get_paths,
        )

        log_dir = get_paths().state_subdir("logs")
    else:
        log_dir = Path(config.log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)

    # Console sink
    console_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    )

    if mode == Mode.PRODUCTION:
        # 生产环境：简化格式
        console_format = (
            "{time:YYYY-MM-DD HH:mm:ss} | "
            "{level: <8} | "
            "{name}:{function}:{line} | "
            "{message}"
        )

    _logger.add(
        sys.stdout,
        format=console_format,
        level=config.log_level,
        colorize=mode == Mode.DEVELOPMENT,
    )

    # File sink - JSON 格式（生产环境）
    if mode == Mode.PRODUCTION:
        log_file = log_dir / "ditto.jsonl"
        _logger.add(
            log_file,
            format=_json_formatter,
            level=config.log_level,
            rotation="1 day",
            retention="30 days",
            compression="gz",
            serialize=False,
        )

    # File sink - 文本格式（开发环境）
    if mode == Mode.DEVELOPMENT:
        log_file = log_dir / "ditto.log"
        _logger.add(
            log_file,
            format=console_format,
            level=config.log_level,
            rotation="1 day",
            retention="30 days",
            compression="gz",
        )

    # 单独的错误日志文件
    error_log_file = log_dir / "ditto_error.log"
    _logger.add(
        error_log_file,
        level="ERROR",
        format=console_format if mode == Mode.DEVELOPMENT else _json_formatter,
        rotation="1 day",
        retention="30 days",
        compression="gz",
    )

    # 初始化日志
    if mode == Mode.DEVELOPMENT:
        _logger.debug("Logging configured for development environment")
    elif mode == Mode.PRODUCTION:
        _logger.info("Logging configured for production environment")


# 导出 logger 供外部使用
logger = _logger
