"""Adversarial edge coverage for selection evidence contracts."""

from __future__ import annotations

from collections.abc import Callable
from typing import cast

import pytest
from ditto_strategy.alpha.selection_evidence import (
    ExclusionEvidence,
    ExclusionReason,
    FactorContributionEvidence,
    InitialUniverseEvidence,
    SelectionEvidence,
    SelectionEvidenceCollector,
    SelectionEvidenceLog,
    SelectionExposureDeclaration,
    SelectionExposureEvidence,
    SelectionExposurePolicy,
    SelectionExposureSizeBucket,
)
from ditto_strategy.errors import StrategySpecError

_TRADE_DATE = "2026-09-04"


def _declaration(*, applicable: bool = True) -> SelectionExposureDeclaration:
    return SelectionExposureDeclaration.from_policy(
        _TRADE_DATE,
        SelectionExposurePolicy.stock()
        if applicable
        else SelectionExposurePolicy.etf(),
    )


def _exposure(instrument_id: int = 1) -> SelectionExposureEvidence:
    return SelectionExposureEvidence(
        trade_date=_TRADE_DATE,
        instrument_id=instrument_id,
        selected_weight=0.5,
        industry_id="bank",
        size_value=50_000_000_000.0,
        size_bucket=SelectionExposureSizeBucket.LARGE,
    )


def _initial(instrument_id: int = 1) -> InitialUniverseEvidence:
    return InitialUniverseEvidence(_TRADE_DATE, instrument_id, 1)


def _exclusion(instrument_id: int = 2) -> ExclusionEvidence:
    return ExclusionEvidence(
        _TRADE_DATE,
        instrument_id,
        "liquidity",
        ExclusionReason.INSUFFICIENT_LIQUIDITY,
    )


def _contribution(instrument_id: int = 3) -> FactorContributionEvidence:
    return FactorContributionEvidence(
        trade_date=_TRADE_DATE,
        instrument_id=instrument_id,
        factor_name="momentum",
        raw_value=0.5,
        processed_value=0.5,
        normalized_value=0.5,
        weight=0.5,
        contribution=0.25,
        factor_signal_score=0.25,
    )


def _selection(instrument_id: int = 4) -> SelectionEvidence:
    return SelectionEvidence(_TRADE_DATE, instrument_id, 0.8, 1, True)


def test_trade_date_rejects_non_string_values() -> None:
    with pytest.raises(StrategySpecError) as exc_info:
        InitialUniverseEvidence(cast("str", 20260904), 1, 1)

    assert exc_info.value.details["reason"] == "invalid_evidence_trade_date"


def test_log_rejects_an_item_from_the_wrong_evidence_sequence() -> None:
    with pytest.raises(TypeError, match="InitialUniverseEvidence"):
        SelectionEvidenceLog(
            initial_universe=(cast("InitialUniverseEvidence", _selection()),)
        )


def test_collector_rejects_untyped_event() -> None:
    collector = SelectionEvidenceCollector()
    collector.begin_rebalance(_TRADE_DATE)

    with pytest.raises(TypeError, match="immutable selection evidence"):
        collector.emit(object())


def test_collector_rejects_duplicate_exposure_declaration_and_row() -> None:
    collector = SelectionEvidenceCollector()
    collector.begin_rebalance(_TRADE_DATE)
    declaration = _declaration()
    exposure = _exposure()
    collector.emit(declaration)

    with pytest.raises(StrategySpecError) as declaration_exc:
        collector.emit(declaration)

    collector.emit(exposure)
    with pytest.raises(StrategySpecError) as exposure_exc:
        collector.emit(exposure)

    assert declaration_exc.value.details["reason"] == "duplicate_exposure_declaration"
    assert exposure_exc.value.details["reason"] == (
        "duplicate_selection_exposure_evidence"
    )


def test_collector_requires_an_applicable_same_date_exposure_declaration() -> None:
    missing = SelectionEvidenceCollector()
    missing.begin_rebalance(_TRADE_DATE)
    with pytest.raises(StrategySpecError) as missing_exc:
        missing.emit(_exposure())

    not_applicable = SelectionEvidenceCollector()
    not_applicable.begin_rebalance(_TRADE_DATE)
    not_applicable.emit(_declaration(applicable=False))
    with pytest.raises(StrategySpecError) as applicability_exc:
        not_applicable.emit(_exposure())

    assert missing_exc.value.details["reason"] == "exposure_declaration_missing"
    assert applicability_exc.value.details["reason"] == (
        "not_applicable_exposure_has_rows"
    )


def test_collector_rejects_duplicate_contribution_and_exclusion_contradiction() -> None:
    collector = SelectionEvidenceCollector()
    collector.begin_rebalance(_TRADE_DATE)
    contribution = _contribution()
    collector.emit(contribution)
    with pytest.raises(StrategySpecError) as contribution_exc:
        collector.emit(contribution)

    collector.emit(_exclusion(5))
    with pytest.raises(StrategySpecError) as contradiction_exc:
        collector.emit(_selection(5))

    assert contribution_exc.value.details["reason"] == (
        "duplicate_factor_contribution_evidence"
    )
    assert contradiction_exc.value.details["reason"] == (
        "contradictory_exclusion_evidence"
    )


def test_abort_removes_every_pending_index_entry() -> None:
    events = (
        _declaration(),
        _exposure(),
        _initial(),
        _exclusion(),
        _contribution(),
        _selection(),
    )
    collector = SelectionEvidenceCollector()
    collector.begin_rebalance(_TRADE_DATE)
    for event in events:
        collector.emit(event)
    collector.abort_rebalance()

    collector.begin_rebalance(_TRADE_DATE)
    for event in events:
        collector.emit(event)
    collector.commit_rebalance()

    snapshot = collector.snapshot()
    assert snapshot.exposure_declarations == (events[0],)
    assert snapshot.exposures == (events[1],)
    assert snapshot.initial_universe == (events[2],)
    assert snapshot.exclusions == (events[3],)
    assert snapshot.factor_contributions == (events[4],)
    assert snapshot.selections == (events[5],)


def _duplicate_declaration_log() -> SelectionEvidenceLog:
    declaration = _declaration()
    return SelectionEvidenceLog(exposure_declarations=(declaration, declaration))


def _duplicate_exposure_log() -> SelectionEvidenceLog:
    exposure = _exposure()
    return SelectionEvidenceLog(
        exposure_declarations=(_declaration(),),
        exposures=(exposure, exposure),
    )


def _duplicate_contribution_log() -> SelectionEvidenceLog:
    contribution = _contribution()
    return SelectionEvidenceLog(factor_contributions=(contribution, contribution))


def _contradictory_log() -> SelectionEvidenceLog:
    return SelectionEvidenceLog(
        exclusions=(_exclusion(7),),
        selections=(_selection(7),),
    )


def _empty_applicable_exposure_log() -> SelectionEvidenceLog:
    return SelectionEvidenceLog(exposure_declarations=(_declaration(),))


@pytest.mark.parametrize(
    ("build_log", "reason"),
    [
        (_duplicate_declaration_log, "duplicate_exposure_declaration"),
        (_duplicate_exposure_log, "duplicate_selection_exposure_evidence"),
        (_duplicate_contribution_log, "duplicate_factor_contribution_evidence"),
        (_contradictory_log, "contradictory_exclusion_evidence"),
        (_empty_applicable_exposure_log, "applicable_exposure_empty"),
    ],
)
def test_log_revalidates_cross_event_invariants(
    build_log: Callable[[], SelectionEvidenceLog],
    reason: str,
) -> None:
    with pytest.raises(StrategySpecError) as exc_info:
        build_log()

    assert exc_info.value.details["reason"] == reason
