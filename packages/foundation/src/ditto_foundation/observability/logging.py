"""
日志配置模块.

基于 loguru 的结构化日志配置，支持多环境和 JSON 格式输出.
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger as _logger

from .config import Mode, ObservabilityConfig


def _json_formatter(record: dict[str, Any]) -> str:
    """
    JSON 格式化器，用于生产环境日志.

    Args:
    ----
        record: loguru 日志记录

    Returns:
    -------
        str: JSON 格式的日志字符串

    """
    log_entry = {
        "timestamp": datetime.fromtimestamp(
            record["record"]["time"].timestamp()
        ).isoformat(),
        "level": record["record"]["level"].name,
        "logger": record["record"]["name"],
        "function": record["record"]["function"],
        "line": record["record"]["line"],
        "message": record["record"]["message"],
    }

    # 添加额外的上下文字段
    if "event" in record["extra"]:
        log_entry["event"] = record["extra"]["event"]

    # 添加 trace_id 如果存在
    if "trace_id" in record["extra"]:
        log_entry["trace_id"] = record["extra"]["trace_id"]

    # 添加其他额外字段
    for key, value in record["extra"].items():
        if key not in ("event", "trace_id"):
            log_entry[key] = value

    # 添加异常信息
    if record["record"]["exception"]:
        log_entry["exception"] = {
            "type": record["record"]["exception"].type.__name__,
            "value": str(record["record"]["exception"].value),
            "traceback": record["record"]["exception"].traceback,
        }

    return json.dumps(log_entry, ensure_ascii=False) + "\n"


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
