"""
Logging configuration for Ditto system.

This module provides structured logging configuration using loguru,
with support for different environments, log levels, and output formats.
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger
from pydantic import BaseModel


class LogConfig(BaseModel):
    """Logging configuration model."""

    level: str = "INFO"
    format: str = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    )
    rotation: str = "1 day"
    retention: str = "30 days"
    compression: str = "gz"
    json_format: bool = False
    enable_console: bool = True
    enable_file: bool = True


class StructuredLogger:
    """
    Structured logger wrapper around loguru.

    Provides additional functionality for structured logging
    and context management.
    """

    def __init__(self, name: str) -> None:
        """Initialize logger with name."""
        self.name = name
        self.logger = logger.bind(name=name)

    def info(self, message: str, **kwargs: Any) -> None:
        """Log info message with optional structured data."""
        if kwargs:
            self.logger.info(f"{message} | {json.dumps(kwargs)}")
        else:
            self.logger.info(message)

    def error(self, message: str, **kwargs: Any) -> None:
        """Log error message with optional structured data."""
        if kwargs:
            self.logger.error(f"{message} | {json.dumps(kwargs)}")
        else:
            self.logger.error(message)

    def warning(self, message: str, **kwargs: Any) -> None:
        """Log warning message with optional structured data."""
        if kwargs:
            self.logger.warning(f"{message} | {json.dumps(kwargs)}")
        else:
            self.logger.warning(message)

    def debug(self, message: str, **kwargs: Any) -> None:
        """Log debug message with optional structured data."""
        if kwargs:
            self.logger.debug(f"{message} | {json.dumps(kwargs)}")
        else:
            self.logger.debug(message)

    def exception(self, message: str, **kwargs: Any) -> None:
        """Log exception with traceback."""
        if kwargs:
            self.logger.exception(f"{message} | {json.dumps(kwargs)}")
        else:
            self.logger.exception(message)

    def bind(self, **kwargs: Any) -> Any:
        """Create a new logger with bound context."""
        return self.logger.bind(**kwargs)


def setup_logging(
    config: LogConfig | None = None,
    log_dir: Path | None = None,
    env: str = "development",
) -> None:
    """
    Set up logging configuration for the application.

    Args:
        config: Logging configuration
        log_dir: Directory for log files
        env: Environment (development, testing, production)

    """
    # Remove default logger
    logger.remove()

    # Use default config if not provided
    if config is None:
        config = LogConfig()

    # Set log directory
    if log_dir is None:
        log_dir = Path("./logs")
    log_dir.mkdir(parents=True, exist_ok=True)

    # Console handler
    if config.enable_console:
        console_format = config.format
        if env == "production":
            # Simpler format for production
            console_format = (
                "{time:YYYY-MM-DD HH:mm:ss} | "
                "{level: <8} | "
                "{name}:{function}:{line} | "
                "{message}"
            )
        elif env == "testing":
            # Minimal format for testing
            console_format = "{level} | {message}"

        logger.add(
            sys.stdout,
            format=console_format,
            level=config.level,
            colorize=env != "production",
        )

    # File handler
    if config.enable_file:
        log_file = log_dir / "ditto.log"

        # Determine file format
        if config.json_format:
            # JSON format for structured logging
            logger.add(
                log_file,
                format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level} | {name} | {message}",
                level=config.level,
                rotation=config.rotation,
                retention=config.retention,
                compression=config.compression,
                serialize=True,  # JSON format
            )
        else:
            # Regular text format
            logger.add(
                log_file,
                format=config.format,
                level=config.level,
                rotation=config.rotation,
                retention=config.retention,
                compression=config.compression,
            )

        # Separate error log file
        error_log_file = log_dir / "ditto_error.log"
        logger.add(
            error_log_file,
            level="ERROR",
            format=config.format,
            rotation=config.rotation,
            retention=config.retention,
            compression=config.compression,
        )

    # Set environment-specific configurations
    if env == "development":
        logger.debug("Logging configured for development environment")
    elif env == "testing":
        logger.remove()  # Remove all handlers for testing
        logger.add(sys.stdout, level="WARNING")  # Only warnings and errors
    elif env == "production":
        logger.info("Logging configured for production environment")


def get_logger(name: str) -> StructuredLogger:
    """
    Get a structured logger instance.

    Args:
        name: Logger name (usually module name)

    Returns:
        StructuredLogger instance

    """
    return StructuredLogger(name)


class RequestLogger:
    """
    Specialized logger for HTTP requests.

    Logs request/response information in a structured format.
    """

    def __init__(self) -> None:
        """Initialize request logger."""
        self.logger = logger.bind(name="requests")

    def log_request(
        self,
        method: str,
        path: str,
        headers: dict[str, Any] | None = None,
        query_params: dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> None:
        """Log incoming request."""
        log_data = {
            "event": "request",
            "method": method,
            "path": path,
            "headers": headers,
            "query_params": query_params,
            "request_id": request_id,
        }
        self.logger.info(f"{method} {path}", **log_data)

    def log_response(
        self,
        method: str,
        path: str,
        status_code: int,
        duration_ms: float,
        request_id: str | None = None,
    ) -> None:
        """Log outgoing response."""
        log_data = {
            "event": "response",
            "method": method,
            "path": path,
            "status_code": status_code,
            "duration_ms": duration_ms,
            "request_id": request_id,
        }

        # Define HTTP status code constants
        HTTP_WARNING_THRESHOLD = 400
        HTTP_ERROR_THRESHOLD = 500
        level = (
            "info"
            if status_code < HTTP_WARNING_THRESHOLD
            else "warning"
            if status_code < HTTP_ERROR_THRESHOLD
            else "error"
        )
        getattr(self.logger, level)(
            f"{method} {path} - {status_code} ({duration_ms:.2f}ms)", **log_data
        )

    def log_error(
        self,
        method: str,
        path: str,
        error: Exception,
        request_id: str | None = None,
    ) -> None:
        """Log request error."""
        log_data = {
            "event": "error",
            "method": method,
            "path": path,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "request_id": request_id,
        }
        self.logger.error(
            f"{method} {path} - {type(error).__name__}: {error}", **log_data
        )


class BusinessLogger:
    """
    Specialized logger for business events.

    Logs important business events like trades, strategy decisions, etc.
    """

    def __init__(self) -> None:
        """Initialize business logger."""
        self.logger = logger.bind(name="business")

    def log_trade(  # noqa: PLR0913
        self,
        strategy: str,
        symbol: str,
        action: str,
        quantity: int,
        price: float,
        order_id: str | None = None,
    ) -> None:
        """Log trade execution."""
        log_data = {
            "event": "trade",
            "strategy": strategy,
            "symbol": symbol,
            "action": action,
            "quantity": quantity,
            "price": price,
            "order_id": order_id,
            "timestamp": datetime.now().isoformat(),
        }
        self.logger.info(f"Trade: {action} {quantity} {symbol} @ {price}", **log_data)

    def log_signal(
        self,
        strategy: str,
        symbol: str,
        signal_type: str,
        confidence: float,
        factors: dict[str, float] | None = None,
    ) -> None:
        """Log trading signal."""
        log_data = {
            "event": "signal",
            "strategy": strategy,
            "symbol": symbol,
            "signal_type": signal_type,
            "confidence": confidence,
            "factors": factors,
            "timestamp": datetime.now().isoformat(),
        }
        self.logger.info(
            f"Signal: {signal_type} for {symbol} (confidence: {confidence:.2f})",
            **log_data,
        )

    def log_data_update(
        self,
        source: str,
        symbol: str,
        update_type: str,
        records: int,
        success: bool,
    ) -> None:
        """Log data update event."""
        log_data = {
            "event": "data_update",
            "source": source,
            "symbol": symbol,
            "update_type": update_type,
            "records": records,
            "success": success,
            "timestamp": datetime.now().isoformat(),
        }
        level = "info" if success else "error"
        getattr(self.logger, level)(
            f"Data update: {source} - {update_type} for {symbol} "
            f"({'success' if success else 'failed'})",
            **log_data,
        )


# Global logger instances
request_logger = RequestLogger()
business_logger = BusinessLogger()


# Context manager for temporary log level changes
class LogLevelContext:
    """Context manager for temporary log level changes."""

    def __init__(self, level: str, logger_name: str | None = None) -> None:
        """Initialize context manager."""
        self.level = level
        self.logger_name = logger_name
        self.original_level = None

    def __enter__(self) -> "LogLevelContext":
        """Enter context and change log level."""
        if self.logger_name:
            # For specific logger - implementation would depend on loguru version
            pass
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit context and restore original log level."""
        pass
