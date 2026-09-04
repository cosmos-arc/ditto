"""No-exporter and non-recording-span edges for tracing helpers."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from ditto_platform.foundation.config.environment import Environment
from ditto_platform.foundation.observability.config import ObservabilityConfig
from ditto_platform.foundation.observability.tracing import (
    SpanContext,
    configure_tracing,
    get_span_id,
    get_trace_id,
    reset_tracing,
)


@pytest.fixture(autouse=True)
def _isolated_tracing_state() -> Iterator[None]:
    reset_tracing()
    yield
    reset_tracing()


def test_non_recording_current_span_ignores_handled_exception() -> None:
    SpanContext("inactive").record_exception(ValueError("handled"))


def test_enabled_tracing_without_exporter_has_empty_ids_outside_a_span() -> None:
    tracer = configure_tracing(
        ObservabilityConfig(
            environment=Environment.DEVELOPMENT,
            pytest_running=False,
            tracing_enabled=True,
            tracing_exporter="none",
        )
    )

    assert tracer is not None
    assert get_trace_id() == ""
    assert get_span_id() == ""
