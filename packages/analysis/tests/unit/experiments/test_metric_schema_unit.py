"""Unit tests for the canonical R3 research metric schema."""

from dataclasses import FrozenInstanceError
from typing import cast

import pytest
from ditto_analysis.errors import ExperimentSpecError
from ditto_analysis.experiments import (
    R3_COMPARISON_METRIC_IDS,
    R3_DIAGNOSTIC_METRIC_IDS,
    R3_RESEARCH_METRIC_SCHEMA,
    ResearchMetricAggregation,
    ResearchMetricDirection,
    ResearchMetricDomain,
    ResearchMetricId,
    ResearchMetricScale,
    ResearchMetricUnit,
    ResearchMetricValue,
)


def test_r3_schema_has_versioned_typed_canonical_definitions() -> None:
    schema = R3_RESEARCH_METRIC_SCHEMA

    assert schema.schema_id == "r3-research-metrics"
    assert schema.version == 1
    assert tuple(item.metric_id for item in schema.definitions) == tuple(
        ResearchMetricId
    )
    assert R3_COMPARISON_METRIC_IDS == (
        ResearchMetricId.NET_RETURN,
        ResearchMetricId.RELATIVE_NET_RETURN,
        ResearchMetricId.SHARPE_RATIO,
        ResearchMetricId.CALMAR_RATIO,
        ResearchMetricId.MAX_DRAWDOWN,
        ResearchMetricId.TURNOVER,
        ResearchMetricId.COST_DRAG,
        ResearchMetricId.CAPACITY,
    )
    assert set(R3_DIAGNOSTIC_METRIC_IDS).issubset(set(ResearchMetricId))
    drawdown = schema.definition(ResearchMetricId.MAX_DRAWDOWN)
    assert drawdown.unit is ResearchMetricUnit.PERCENT
    assert drawdown.domain is ResearchMetricDomain.RISK
    assert drawdown.direction is ResearchMetricDirection.MAXIMIZE
    assert drawdown.aggregation is (
        ResearchMetricAggregation.RECOMPUTE_CROSS_FOLD_EQUITY_CURVE
    )
    sharpe = schema.definition(ResearchMetricId.SHARPE_RATIO)
    assert sharpe.scale is ResearchMetricScale.ANNUALIZED
    assert sharpe.periods_per_year == 252
    assert drawdown.scale is ResearchMetricScale.POINT_ESTIMATE
    assert drawdown.periods_per_year is None


def test_metric_value_preserves_percent_semantics_and_canonical_payload() -> None:
    value = ResearchMetricValue(ResearchMetricId.NET_RETURN, -8)

    assert value.value == -8.0
    assert value.canonical_payload() == {
        "metric_id": "net_return",
        "unit": "percent",
        "value": -8.0,
    }


@pytest.mark.parametrize(
    ("metric_id", "value"),
    [
        (ResearchMetricId.MAX_DRAWDOWN, 0.01),
        (ResearchMetricId.MAX_DRAWDOWN, -100.01),
        (ResearchMetricId.TURNOVER, -0.01),
        (ResearchMetricId.COST_DRAG, -0.01),
        (ResearchMetricId.CAPACITY, -1.0),
        (ResearchMetricId.COVERAGE, 1.01),
        (ResearchMetricId.MISSINGNESS, -0.01),
    ],
)
def test_metric_value_rejects_values_outside_canonical_domain(
    metric_id: ResearchMetricId,
    value: float,
) -> None:
    with pytest.raises(ExperimentSpecError) as exc_info:
        ResearchMetricValue(metric_id, value)

    assert exc_info.value.details["reason_code"] == "metric_value_out_of_domain"


def test_metric_schema_is_frozen_and_rejects_unknown_lookup() -> None:
    with pytest.raises(FrozenInstanceError):
        _set_attribute(R3_RESEARCH_METRIC_SCHEMA, "version", 2)

    with pytest.raises(ExperimentSpecError) as exc_info:
        R3_RESEARCH_METRIC_SCHEMA.definition(cast("ResearchMetricId", "net_return"))

    assert exc_info.value.details["reason_code"] == "invalid_research_metric_id"


def _set_attribute(target: object, name: str, value: object) -> None:
    setattr(target, name, value)
