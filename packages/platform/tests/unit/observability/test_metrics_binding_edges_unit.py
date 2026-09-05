"""Dynamic binding and no-exporter edges for observability metrics."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from ditto_platform.foundation.config.environment import Environment
from ditto_platform.foundation.observability.config import ObservabilityConfig
from ditto_platform.foundation.observability.metrics import (
    Metrics,
    SafeCounter,
    configure_metrics,
    register_metric_definitions,
    reset_metrics,
)
from ditto_platform.foundation.observability.metrics._types import MetricDefinition


@pytest.fixture(autouse=True)
def _isolated_metric_registry() -> Iterator[None]:
    reset_metrics()
    yield
    reset_metrics()


def test_registered_definition_can_be_rehydrated_by_metric_metaclass() -> None:
    register_metric_definitions(
        [
            {
                "name": "external_jobs_total",
                "instrument_name": "ditto.external.jobs_total",
                "type": "counter",
                "description": "External jobs",
            }
        ]
    )
    delattr(Metrics, "external_jobs_total")

    assert isinstance(Metrics.external_jobs_total, SafeCounter)


def test_ensure_definition_rejects_unknown_metric_type() -> None:
    definition: MetricDefinition = {
        "name": "invalid_metric",
        "instrument_name": "ditto.invalid.metric",
        "type": "summary",
        "description": "Unsupported metric",
    }

    with pytest.raises(ValueError, match="Unknown metric type"):
        Metrics.ensure_definition(definition)


def test_reset_wrappers_ignores_external_names_without_live_attributes() -> None:
    Metrics.reset_wrappers(["missing_external_one", "missing_external_two"])

    assert not hasattr(Metrics, "missing_external_one")
    assert not hasattr(Metrics, "missing_external_two")


def test_metrics_enabled_with_none_exporter_uses_local_meter() -> None:
    config = ObservabilityConfig(
        environment=Environment.DEVELOPMENT,
        pytest_running=False,
        metrics_enabled=True,
        metrics_exporter="none",
    )

    meter = configure_metrics(config)

    assert meter is not None
    assert isinstance(Metrics.api_requests, SafeCounter)
