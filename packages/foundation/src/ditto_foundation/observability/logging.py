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

from ditto_foundation.config.paths import get_paths

from .config import ObservabilityConfig


def _resolve_log_dir(config: ObservabilityConfig) -> Path:
    """
    解析日志目录路径.

    如果 config.log_dir 是默认值 "logs"，使用 XDGPaths 的 state_subdir.
    否则，使用指定的路径并创建目录.

    Args:
    ----
        config: 可观测性配置

    Returns:
    -------
        Path: 日志目录路径

    """
    if config.log_dir == "logs":
        return get_paths().state_subdir("logs")

    log_dir = Path(config.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


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


def configure_logging(config: ObservabilityConfig) -> None:
    """
    配置 Loguru 日志系统.

    Args:
    ----
        config: 可观测性配置

    """
    # 获取生效配置
    effective = config.get_effective_config()

    # 移除默认 handler
    _logger.remove()

    # 静默模式：不添加任何 handler
    if not effective.verbose_logging:
        return

    # 解析日志目录
    log_dir = _resolve_log_dir(config)

    # Console sink
    console_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    )

    if config.environment.is_production:
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
        level=effective.log_level,
        colorize=config.environment.is_development,
    )

    # File sink - JSON 格式（生产环境）
    if config.environment.is_production:
        log_file = log_dir / "ditto.jsonl"
        _logger.add(
            log_file,
            format=_json_formatter,
            level=effective.log_level,
            rotation="1 day",
            retention="30 days",
            compression="gz",
            serialize=False,
        )

    # File sink - 文本格式（开发环境）
    if config.environment.is_development:
        log_file = log_dir / "ditto.log"
        _logger.add(
            log_file,
            format=console_format,
            level=effective.log_level,
            rotation="1 day",
            retention="30 days",
            compression="gz",
        )

    # 单独的错误日志文件
    error_log_file = log_dir / "ditto_error.log"
    _logger.add(
        error_log_file,
        level="ERROR",
        format=console_format if config.environment.is_development else _json_formatter,
        rotation="1 day",
        retention="30 days",
        compression="gz",
    )

    # 初始化日志
    if config.environment.is_development:
        _logger.debug("Logging configured for development environment")
    elif config.environment.is_production:
        _logger.info("Logging configured for production environment")


# 导出 logger 供外部使用
logger = _logger
