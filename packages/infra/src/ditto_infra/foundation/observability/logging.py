"""日志配置模块。"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import orjson
from loguru import logger as _logger

from .config import ObservabilityConfig


def _resolve_log_dir(config: ObservabilityConfig) -> Path:
    """解析日志目录路径。"""
    log_dir = Path(config.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def _build_log_record(record: dict[str, Any]) -> dict[str, Any]:
    """
    从 loguru record wrapper 构建 JSON log entry.

    loguru 在运行时传递的 record 是一个 wrapper dict，
    包含 ``"record"``（Record TypedDict）和 ``"extra"`` 键。
    """
    rec = record["record"]
    extra = record["extra"]

    log_entry: dict[str, Any] = {
        "timestamp": datetime.fromtimestamp(rec["time"].timestamp()).isoformat(),
        "level": rec["level"].name,
        "logger": rec["name"],
        "function": rec["function"],
        "line": rec["line"],
        "message": rec["message"],
    }

    log_entry.update(extra)

    if rec["exception"]:
        exc = rec["exception"]
        log_entry["exception"] = {
            "type": exc.type.__name__,
            "value": str(exc.value),
            "traceback": str(exc.traceback),
        }

    return log_entry


def _json_formatter(record: dict[str, Any]) -> str:
    """JSON 格式化函数 — 将 loguru record 转为 JSONL."""
    log_entry = _build_log_record(record)
    return orjson.dumps(log_entry).decode("utf-8") + "\n"


# Loguru 类型桩定义 FormatFunction = Callable[[Record], str]，
# 但运行时实际传递的 record 是一个 wrapper dict。
# 使用 Any 类型注解使 pyright 接受任意类型，
# 同时避免 ANN401（变量注解不在 ANN401 检查范围）。
_json_log_format: Any = _json_formatter


def configure_logging(config: ObservabilityConfig) -> None:
    """配置 Loguru 日志系统。"""
    effective = config.get_effective_config()

    _logger.remove()

    if effective.pytest_running:
        return

    log_dir = _resolve_log_dir(config)

    if effective.verbose_logging:
        console_format = (
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        )
    else:
        console_format = (
            "{time:YYYY-MM-DD HH:mm:ss} | "
            "{level: <8} | "
            "{name}:{function}:{line} | "
            "{message}"
        )

    if effective.log_to_console:
        if effective.log_format == "json":
            _logger.add(
                sys.stdout,
                format=_json_log_format,
                level=effective.log_level,
                colorize=False,
            )
        else:
            _logger.add(
                sys.stdout,
                format=console_format,
                level=effective.log_level,
                colorize=effective.verbose_logging,
            )

    if effective.log_to_file:
        file_format = (
            _json_log_format
            if effective.log_format == "json" or config.environment.is_production
            else console_format
        )
        log_file = log_dir / (
            "ditto.jsonl" if file_format is _json_log_format else "ditto.log"
        )
        _logger.add(
            log_file,
            format=file_format,
            level=effective.log_level,
            rotation="1 day",
            retention="30 days",
            compression="gz",
            serialize=False,
        )

        error_log_file = log_dir / "ditto_error.log"
        _logger.add(
            error_log_file,
            level="ERROR",
            format=file_format,
            rotation="1 day",
            retention="30 days",
            compression="gz",
        )

    if config.environment.is_development:
        _logger.debug("Logging configured for development environment")
    elif config.environment.is_production:
        _logger.info("Logging configured for production environment")
    elif config.environment.is_testing:
        _logger.info("Logging configured for testing environment")


logger = _logger

__all__ = ["configure_logging", "logger"]
