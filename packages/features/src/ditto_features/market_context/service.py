"""Versioned market-context formulas and deterministic driver attribution."""

from __future__ import annotations

import hashlib
from dataclasses import asdict

import orjson

from ditto_features.market_context.contracts import (
    MarketRegimeDriver,
    MarketRegimeFeature,
    MarketRegimeFeatureSet,
    MarketRegimeInput,
    MarketRegimeLabel,
)

__all__ = ["MarketRegimeService"]

_FEATURE_VERSION = "market-regime.v1"
_REGIME_THRESHOLD = 0.20
_WEIGHTS: dict[str, float] = {
    "breadth": 0.25,
    "trend": 0.25,
    "style": 0.10,
    "volatility": 0.15,
    "cross_market": 0.10,
    "macro": 0.15,
}
_CATEGORIES: dict[str, str] = {
    "breadth": "a_share",
    "trend": "a_share",
    "style": "style",
    "volatility": "risk",
    "cross_market": "global",
    "macro": "macro",
}
_CORE_INPUTS = frozenset(
    {
        "advancing_count",
        "declining_count",
        "universe_count",
        "benchmark_return_20d",
        "realized_volatility_20d",
    }
)


def _clamp(value: float) -> float:
    return max(-1.0, min(1.0, value))


def _input_hash(value: MarketRegimeInput) -> str:
    payload = orjson.dumps(
        asdict(value),
        option=orjson.OPT_SORT_KEYS | orjson.OPT_UTC_Z,
    )
    return hashlib.sha256(payload).hexdigest()


def _missing(value: MarketRegimeInput) -> tuple[str, ...]:
    missing = set(value.declared_missing_inputs)
    for field in (
        "advancing_count",
        "declining_count",
        "universe_count",
        "benchmark_return_20d",
        "small_cap_return_20d",
        "large_cap_return_20d",
        "realized_volatility_20d",
        "global_return_1d",
        "macro_surprise_score",
        "macro_trend_score",
    ):
        if getattr(value, field) is None:
            missing.add(field)
    return tuple(sorted(missing))


def _feature_values(value: MarketRegimeInput) -> dict[str, float]:
    features: dict[str, float] = {}
    if (
        value.advancing_count is not None
        and value.declining_count is not None
        and value.universe_count
    ):
        features["breadth"] = _clamp(
            (value.advancing_count - value.declining_count) / value.universe_count
        )
    if value.benchmark_return_20d is not None:
        features["trend"] = _clamp(value.benchmark_return_20d / 0.10)
    if (
        value.small_cap_return_20d is not None
        and value.large_cap_return_20d is not None
    ):
        features["style"] = _clamp(
            (value.small_cap_return_20d - value.large_cap_return_20d) / 0.08
        )
    if value.realized_volatility_20d is not None:
        features["volatility"] = _clamp(-(value.realized_volatility_20d - 0.20) / 0.15)
    if value.global_return_1d is not None:
        features["cross_market"] = _clamp(value.global_return_1d / 0.03)
    if value.macro_surprise_score is not None and value.macro_trend_score is not None:
        features["macro"] = _clamp(
            (value.macro_surprise_score + value.macro_trend_score) / 2
        )
    return features


def _label(score: float) -> MarketRegimeLabel:
    if score >= _REGIME_THRESHOLD:
        return "risk_on"
    if score <= -_REGIME_THRESHOLD:
        return "risk_off"
    return "balanced"


class MarketRegimeService:
    """Evaluate a stable formula without performing I/O or querying data."""

    def evaluate(self, value: MarketRegimeInput) -> MarketRegimeFeatureSet:
        """Return a blocked, degraded, or ready versioned feature set."""
        input_hash = _input_hash(value)
        feature_set_id = f"market-regime:sha256:{input_hash}"
        missing_inputs = _missing(value)
        if _CORE_INPUTS.intersection(missing_inputs):
            return MarketRegimeFeatureSet(
                feature_set_id=feature_set_id,
                feature_version=_FEATURE_VERSION,
                input_hash=input_hash,
                as_of=value.as_of,
                knowledge_cutoff=value.knowledge_cutoff,
                publication_cutoff=value.publication_cutoff,
                source_snapshot_ids=value.source_snapshot_ids,
                status="blocked",
                label=None,
                score=None,
                features=(),
                drivers=(),
                missing_inputs=missing_inputs,
            )

        raw_values = _feature_values(value)
        available_weight = sum(_WEIGHTS[name] for name in raw_values)
        features = tuple(
            MarketRegimeFeature(
                name=name,
                category=_CATEGORIES[name],
                value=raw_values[name],
                weight=_WEIGHTS[name] / available_weight,
                contribution=raw_values[name] * _WEIGHTS[name] / available_weight,
            )
            for name in _WEIGHTS
            if name in raw_values
        )
        score = sum(feature.contribution for feature in features)
        drivers = tuple(
            sorted(
                (
                    MarketRegimeDriver(
                        name=feature.name,
                        category=feature.category,
                        contribution=feature.contribution,
                        direction=(
                            "supportive"
                            if feature.contribution > 0
                            else "pressuring"
                            if feature.contribution < 0
                            else "neutral"
                        ),
                    )
                    for feature in features
                ),
                key=lambda driver: (-abs(driver.contribution), driver.name),
            )
        )
        return MarketRegimeFeatureSet(
            feature_set_id=feature_set_id,
            feature_version=_FEATURE_VERSION,
            input_hash=input_hash,
            as_of=value.as_of,
            knowledge_cutoff=value.knowledge_cutoff,
            publication_cutoff=value.publication_cutoff,
            source_snapshot_ids=value.source_snapshot_ids,
            status="degraded" if missing_inputs else "ready",
            label=_label(score),
            score=score,
            features=features,
            drivers=drivers,
            missing_inputs=missing_inputs,
        )
