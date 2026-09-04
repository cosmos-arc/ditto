"""Golden and replay tests for deterministic market-context features."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest
from ditto_features.market_context.contracts import MarketRegimeInput
from ditto_features.market_context.service import MarketRegimeService


def _input() -> MarketRegimeInput:
    return MarketRegimeInput(
        as_of=datetime(2026, 8, 31, 9, tzinfo=UTC),
        knowledge_cutoff=datetime(2026, 8, 31, 9, tzinfo=UTC),
        publication_cutoff=datetime(2026, 8, 31, 8, 30, tzinfo=UTC),
        source_snapshot_ids=(
            "snapshot:tushare:stock_daily:sha256:abc",
            "snapshot:fred:macro_indicators:sha256:def",
        ),
        advancing_count=800,
        declining_count=200,
        universe_count=1_000,
        benchmark_return_20d=0.05,
        small_cap_return_20d=0.04,
        large_cap_return_20d=0.0,
        realized_volatility_20d=0.125,
        global_return_1d=0.015,
        macro_surprise_score=0.4,
        macro_trend_score=0.6,
        declared_missing_inputs=(),
    )


@pytest.mark.pit
def test_regime_formula_matches_golden_case() -> None:
    result = MarketRegimeService().evaluate(_input())

    assert result.status == "ready"
    assert result.label == "risk_on"
    assert result.score == pytest.approx(0.525)
    assert {feature.name: feature.value for feature in result.features} == {
        "breadth": pytest.approx(0.6),
        "trend": pytest.approx(0.5),
        "style": pytest.approx(0.5),
        "volatility": pytest.approx(0.5),
        "cross_market": pytest.approx(0.5),
        "macro": pytest.approx(0.5),
    }
    assert sum(driver.contribution for driver in result.drivers) == pytest.approx(
        result.score
    )


def test_replay_identity_and_driver_order_are_deterministic() -> None:
    service = MarketRegimeService()

    first = service.evaluate(_input())
    second = service.evaluate(_input())

    assert first == second
    assert first.feature_set_id.startswith("market-regime:sha256:")
    assert tuple(abs(item.contribution) for item in first.drivers) == tuple(
        sorted((abs(item.contribution) for item in first.drivers), reverse=True)
    )


@pytest.mark.pit
def test_missing_core_input_blocks_without_regime_conclusion() -> None:
    result = MarketRegimeService().evaluate(
        replace(_input(), benchmark_return_20d=None)
    )

    assert result.status == "blocked"
    assert result.label is None
    assert result.score is None
    assert "benchmark_return_20d" in result.missing_inputs


def test_missing_optional_input_degrades_and_renormalizes_available_weights() -> None:
    result = MarketRegimeService().evaluate(
        replace(_input(), global_return_1d=None, macro_surprise_score=None)
    )

    assert result.status == "degraded"
    assert result.label == "risk_on"
    assert result.score is not None
    assert set(result.missing_inputs) == {
        "global_return_1d",
        "macro_surprise_score",
    }


def test_input_rejects_inverted_or_naive_time_boundaries() -> None:
    with pytest.raises(ValueError, match="publication_cutoff"):
        replace(
            _input(),
            knowledge_cutoff=datetime(2026, 8, 31, 8, tzinfo=UTC),
            publication_cutoff=datetime(2026, 8, 31, 8, 1, tzinfo=UTC),
        )
    with pytest.raises(ValueError, match="timezone-aware"):
        replace(_input(), as_of=datetime(2026, 8, 31, 9))
