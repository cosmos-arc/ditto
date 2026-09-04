"""Application adapters for replayable MarketContext and technical inputs."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.execution.replay_context_inputs import (
    build_replay_context_inputs,
    decode_replay_context_inputs,
    replay_context_inputs_payload,
)
from ditto_application.queries.market_context import MarketContextView
from ditto_backtest.context_inputs import ContextInputKind
from ditto_features.technical_analysis.contracts import (
    TechnicalAnalysisSnapshot,
    canonical_snapshot_hash,
)
from ditto_kernel.identity import InstrumentId

_AS_OF = datetime(2026, 8, 31, 7, 0, tzinfo=UTC)


def _market() -> MarketContextView:
    return MarketContextView(
        as_of=_AS_OF,
        knowledge_cutoff=_AS_OF,
        publication_cutoff=_AS_OF,
        source_snapshot_ids=("market-b", "market-a"),
        source_snapshot_set_id="source-set:sha256:market",
        status="ready",
        feature_set_id="market-regime:sha256:input",
        feature_version="market-regime-v1",
        regime_label="balanced",
        regime_score=0.0,
        drivers=(),
        metrics=(),
        impacts=(),
        missing_inputs=(),
        data_conflicts=(),
        uncertainties=(),
        evidence_refs=("market-evidence",),
    )


def _technical() -> TechnicalAnalysisSnapshot:
    draft = TechnicalAnalysisSnapshot(
        snapshot_id="pending",
        input_hash="a" * 64,
        spec_hash="b" * 64,
        registry_version="technical-v1",
        instrument_id=InstrumentId(600000),
        instrument_name="Pudong Bank",
        as_of=_AS_OF,
        knowledge_cutoff=_AS_OF,
        publication_cutoff=_AS_OF,
        source_snapshot_ids=("technical-a",),
        status="ready",
        last_visible_bar_at=_AS_OF,
        last_computed_bar_at=_AS_OF,
        readings=(),
        levels=(),
        timeframe_summaries=(),
        conflicts=(),
        missing_inputs=(),
        warnings=(),
        selection_run_id="selection-run:sha256:one",
        research_case_id="research-case:sha256:one",
        portfolio_snapshot_id=None,
    )
    digest = canonical_snapshot_hash(draft)
    return replace(draft, snapshot_id=f"technical-analysis:sha256:{digest}")


def test_build_replay_context_inputs_preserves_exact_hash_and_pit_lineage() -> None:
    technical = _technical()

    refs = build_replay_context_inputs(
        market_context=_market(),
        technical_snapshots=(technical,),
    )

    assert tuple(item.context_kind for item in refs) == (
        ContextInputKind.MARKET_CONTEXT,
        ContextInputKind.TECHNICAL_ANALYSIS,
    )
    assert refs[1].context_id == technical.snapshot_id
    assert refs[1].content_hash == canonical_snapshot_hash(technical)
    assert refs[1].source_snapshot_ids == technical.source_snapshot_ids


def test_build_replay_context_inputs_rejects_blocked_or_temporally_mixed_evidence() -> (
    None
):
    with pytest.raises(AppProcessError) as blocked_error:
        build_replay_context_inputs(
            market_context=replace(_market(), status="blocked"),
            technical_snapshots=(),
        )
    assert blocked_error.value.details["reason"] == "replay_context_blocked"

    changed_technical = replace(
        _technical(),
        as_of=datetime(2026, 8, 30, 7, 0, tzinfo=UTC),
        knowledge_cutoff=datetime(2026, 8, 30, 7, 0, tzinfo=UTC),
        publication_cutoff=datetime(2026, 8, 30, 7, 0, tzinfo=UTC),
    )
    changed_technical = replace(
        changed_technical,
        snapshot_id=(
            f"technical-analysis:sha256:{canonical_snapshot_hash(changed_technical)}"
        ),
    )
    with pytest.raises(AppProcessError) as mixed_error:
        build_replay_context_inputs(
            market_context=_market(),
            technical_snapshots=(changed_technical,),
        )
    assert mixed_error.value.details["reason"] == "replay_context_temporal_mismatch"


def test_replay_context_input_codec_round_trips_canonical_refs() -> None:
    refs = build_replay_context_inputs(
        market_context=_market(),
        technical_snapshots=(_technical(),),
    )

    payload = replay_context_inputs_payload(refs)

    assert decode_replay_context_inputs(payload) == refs
    with pytest.raises(AppProcessError) as caught:
        decode_replay_context_inputs([*payload, payload[0]])
    assert caught.value.details["reason"] == "invalid_replay_context_inputs"

    mixed = (
        refs[0],
        replace(
            refs[1],
            as_of="2026-08-30T07:00:00Z",
            knowledge_cutoff="2026-08-30T07:00:00Z",
            publication_cutoff="2026-08-30T07:00:00Z",
        ),
    )
    with pytest.raises(AppProcessError) as mixed_error:
        replay_context_inputs_payload(mixed)
    assert mixed_error.value.details["reason"] == "invalid_replay_context_inputs"
