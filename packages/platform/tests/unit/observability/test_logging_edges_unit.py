"""No-output and environment-fallthrough tests for logging configuration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import cast
from unittest.mock import MagicMock

import ditto_platform.foundation.observability.logging as logging_module
import pytest
from ditto_platform.foundation.config.environment import Environment
from ditto_platform.foundation.observability.config import (
    EffectiveConfig,
    ObservabilityConfig,
)
from ditto_platform.foundation.observability.logging import configure_logging


@dataclass(frozen=True)
class _UnclassifiedEnvironment:
    is_development: bool = False
    is_production: bool = False
    is_testing: bool = False


@dataclass(frozen=True)
class _UnclassifiedConfig:
    log_dir: str
    environment: _UnclassifiedEnvironment = _UnclassifiedEnvironment()

    def get_effective_config(self) -> EffectiveConfig:
        return EffectiveConfig(
            log_level="INFO",
            log_format="console",
            log_to_console=False,
            log_to_file=False,
            tracing_enabled=False,
            tracing_exporter="none",
            tracing_sample_rate=0.0,
            metrics_enabled=False,
            metrics_exporter="none",
            vm_endpoint="http://127.0.0.1:8428",
            assertions_enabled=False,
            verbose_logging=False,
            pytest_running=False,
        )


def test_testing_configuration_can_disable_both_logging_sinks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log = MagicMock()
    monkeypatch.setattr(logging_module, "_logger", log)
    config = ObservabilityConfig(
        environment=Environment.TESTING,
        log_dir=str(tmp_path / "logs"),
        pytest_running=False,
        log_to_console=False,
        log_to_file=False,
    )

    configure_logging(config)

    log.add.assert_not_called()
    log.info.assert_called_once_with("Logging configured for testing environment")


def test_unclassified_environment_emits_no_environment_banner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log = MagicMock()
    monkeypatch.setattr(logging_module, "_logger", log)
    config = cast(
        ObservabilityConfig,
        _UnclassifiedConfig(log_dir=str(tmp_path / "logs")),
    )

    configure_logging(config)

    log.debug.assert_not_called()
    log.info.assert_not_called()
