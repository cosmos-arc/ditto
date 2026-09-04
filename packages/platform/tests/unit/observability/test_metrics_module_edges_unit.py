"""Unknown-symbol and malformed-wrapper edges for the metrics module."""

from __future__ import annotations

import ditto_platform.foundation.observability.metrics as metrics_module
import pytest
from ditto_platform.foundation.observability.metrics._types import (
    MetricDefinition,
    _new_noop_wrapper,
)


def test_metrics_module_rejects_unknown_lazy_export() -> None:
    symbol = "unknown_metric_symbol"

    with pytest.raises(AttributeError, match=f"has no attribute '{symbol}'"):
        getattr(metrics_module, symbol)


def test_noop_wrapper_factory_rejects_unknown_metric_type() -> None:
    definition: MetricDefinition = {
        "name": "invalid",
        "instrument_name": "ditto.invalid",
        "type": "summary",
        "description": "Unsupported",
    }

    with pytest.raises(ValueError, match="Unknown metric type"):
        _new_noop_wrapper(definition)
