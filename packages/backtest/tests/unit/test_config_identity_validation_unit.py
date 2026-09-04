"""Canonical identity validation for replayable engine configuration."""

from __future__ import annotations

from typing import cast

import pytest
from ditto_backtest.config import (
    EngineConfig,
    validate_effective_parameter_identity,
    validate_research_snapshot_identity,
)
from ditto_strategy.alpha.parameters import EffectiveParameter

_EMPTY_PARAMETER_HASH = (
    "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945"
)


def test_effective_parameters_require_a_typed_canonical_tuple() -> None:
    with pytest.raises(ValueError, match="must be tuple"):
        validate_effective_parameter_identity(_EMPTY_PARAMETER_HASH, [])
    with pytest.raises(ValueError, match="must be tuple"):
        validate_effective_parameter_identity(
            _EMPTY_PARAMETER_HASH,
            (cast(EffectiveParameter, object()),),
        )

    unsorted = (
        EffectiveParameter(path="z", value=1),
        EffectiveParameter(path="a", value=2),
    )
    with pytest.raises(ValueError, match="canonical path order"):
        validate_effective_parameter_identity("a" * 64, unsorted)


def test_effective_parameter_hash_rejects_duplicates_and_wrong_content() -> None:
    duplicate = (
        EffectiveParameter(path="a", value=1),
        EffectiveParameter(path="a", value=2),
    )
    with pytest.raises(ValueError, match="unique"):
        validate_effective_parameter_identity("a" * 64, duplicate)
    with pytest.raises(ValueError, match="does not match"):
        validate_effective_parameter_identity("a" * 64, ())


def test_research_snapshot_identity_is_atomic_and_utf8_canonical() -> None:
    assert validate_research_snapshot_identity(None, None) is None
    with pytest.raises(ValueError, match="provided together"):
        validate_research_snapshot_identity("snapshot-1", None)
    with pytest.raises(ValueError, match="non-empty canonical"):
        validate_research_snapshot_identity(" snapshot-1", "a" * 64)
    with pytest.raises(ValueError, match="canonical UTF-8"):
        validate_research_snapshot_identity("\ud800", "a" * 64)
    assert validate_research_snapshot_identity("snapshot-1", "a" * 64) == (
        "snapshot-1",
        "a" * 64,
    )


def test_engine_config_rejects_unresolved_legacy_parameter_overrides() -> None:
    with pytest.raises(ValueError, match="parameter_overrides"):
        EngineConfig(
            start_date="2026-09-01",
            end_date="2026-09-04",
            initial_cash=1_000_000.0,
            spec_hash="a" * 64,
            base_spec_hash="b" * 64,
            parameter_hash=_EMPTY_PARAMETER_HASH,
            effective_parameters=(),
            research_snapshot_id=None,
            research_snapshot_manifest_hash=None,
            parameter_overrides=("top_k=10",),
        )
