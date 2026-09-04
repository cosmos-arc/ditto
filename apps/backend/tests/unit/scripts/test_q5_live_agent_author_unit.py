"""Q5 Author proposal egress and lineage contracts."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import orjson
import pytest
from ditto_application.mutation_idempotency import canonical_request_hash
from ditto_application.queries.authoring_preview import AuthoringPreviewFacade
from ditto_apps.scripts.q5_live_agent_author import (
    _AUTHOR_SPEC_TEMPLATE,
    _CapturingAuthorDraftTool,
    _context,
    _exact_save_request,
    _NoBaseCatalog,
    _validate_author_spec,
    _write,
    minimal_author_context,
)


def _selection() -> dict[str, object]:
    return {
        "run_id": "selection-run:sha256:selection",
        "status": "ready",
        "as_of": "2026-09-01T13:26:30Z",
        "source_snapshot_ids": ["snapshot:tushare:etf_daily:sha256:selection"],
        "candidates": [
            {
                "rank": 1,
                "instrument_id": 2_001_724,
                "instrument_name": "华安易富黄金ETF",
                "score": 0.8866,
                "factor_contributions": [
                    {
                        "factor_name": "momentum_1d_rank",
                        "value": 0.937,
                        "weight": 0.6,
                        "contribution": 0.5622,
                    }
                ],
            },
            {
                "rank": 2,
                "instrument_id": 2_001_745,
                "instrument_name": "南方中证500ETF",
                "score": 0.8362,
            },
        ],
        "holdout_metrics": {"net_return": 99.0},
    }


def _research_case() -> dict[str, object]:
    return {
        "case_id": "research-case:sha256:case",
        "selection_run_id": "selection-run:sha256:selection",
        "candidate_instrument_ids": [2_001_724],
        "asset_kind": "etf",
        "objective": "Validate one PIT ETF strategy.",
        "as_of": "2026-09-01T16:21:00Z",
        "knowledge_cutoff": "2026-09-01T16:21:00Z",
        "publication_cutoff": "2026-09-01T16:21:00Z",
        "source_snapshot_ids": ["snapshot:tushare:etf_daily:sha256:selection"],
        "content_hash": "a" * 64,
    }


def _market() -> dict[str, object]:
    return {
        "feature_set_id": "market-regime:sha256:market",
        "status": "degraded",
        "regime_label": "risk_on",
        "regime_score": 0.28,
        "as_of": "2026-09-01T16:21:00Z",
        "knowledge_cutoff": "2026-09-01T16:21:00Z",
        "publication_cutoff": "2026-09-01T16:21:00Z",
        "metrics": [{"name": "breadth", "value": 0.47}],
        "drivers": [{"name": "breadth", "contribution": 0.13}],
        "impacts": [{"target": "cyclical", "direction": "supportive"}],
        "missing_inputs": ["macro_surprise_score"],
        "uncertainties": ["macro_surprise_score_not_derivable"],
        "source_snapshot_set_id": "snapshot-set:sha256:market",
        "source_snapshot_ids": ["snapshot:tushare:index_daily:sha256:market"],
    }


def _technical() -> dict[str, object]:
    return {
        "snapshot_id": "technical-analysis:sha256:technical",
        "status": "degraded",
        "instrument_id": 2_001_724,
        "instrument_name": "华安易富黄金ETF",
        "selection_run_id": "selection-run:sha256:selection",
        "research_case_id": "research-case:sha256:case",
        "as_of": "2026-09-01T16:21:00Z",
        "knowledge_cutoff": "2026-09-01T16:21:00Z",
        "publication_cutoff": "2026-09-01T16:21:00Z",
        "last_visible_bar_at": "2026-07-31T07:00:00Z",
        "source_snapshot_ids": ["snapshot:tushare:etf_daily:sha256:technical"],
        "timeframe_summaries": [{"timeframe": "daily", "trend": "bullish"}],
        "levels": [{"timeframe": "daily", "kind": "support", "price": 7.51}],
        "conflicts": [],
        "missing_inputs": ["daily:benchmark:missing_reference_series"],
        "readings": [
            {
                "timeframe": "daily",
                "name": "rsi",
                "status": "ready",
                "value": 55.0,
            },
            {
                "timeframe": "daily",
                "name": "turnover",
                "status": "ready",
                "value": 123.0,
            },
        ],
    }


def test_author_context_is_minimal_holdout_blind_and_lineage_bound() -> None:
    payload = minimal_author_context(
        selection=_selection(),
        research_case=_research_case(),
        market=_market(),
        technical=_technical(),
    )

    assert payload["holdout_excluded"] is True
    assert payload["selection"]["top_candidate"]["instrument_id"] == 2_001_724
    assert "candidates" not in payload["selection"]
    assert "holdout_metrics" not in repr(payload)
    assert payload["technical"]["selected_readings"] == (
        {
            "timeframe": "daily",
            "name": "rsi",
            "status": "ready",
            "value": 55.0,
        },
    )
    assert payload["lineage"] == {
        "selection_run_id": "selection-run:sha256:selection",
        "research_case_id": "research-case:sha256:case",
        "market_context_feature_set_id": "market-regime:sha256:market",
        "technical_snapshot_id": "technical-analysis:sha256:technical",
    }


def test_author_context_rejects_cross_selection_technical_snapshot() -> None:
    technical = _technical()
    technical["selection_run_id"] = "selection-run:sha256:other"

    with pytest.raises(ValueError, match="selection_run_id"):
        minimal_author_context(
            selection=_selection(),
            research_case=_research_case(),
            market=_market(),
            technical=technical,
        )


def test_author_context_rejects_market_technical_temporal_drift() -> None:
    market = _market()
    market["knowledge_cutoff"] = "2026-09-01T16:20:59Z"

    with pytest.raises(ValueError, match="temporal boundary"):
        minimal_author_context(
            selection=_selection(),
            research_case=_research_case(),
            market=market,
            technical=_technical(),
        )


def test_frozen_author_template_is_valid_and_canonical() -> None:
    preview = AuthoringPreviewFacade(catalog=_NoBaseCatalog()).create_draft(
        spec_json=_AUTHOR_SPEC_TEMPLATE
    )

    assert preview.valid is True
    assert preview.subject_id == "agent_etf_518880_rotation"
    assert preview.payload.value["canonical_hash"] == (
        "2d677219fd4ae439f55ccddffcc512fb2965122f78901311d79ae8884d8a0965"
    )
    assert _validate_author_spec(_AUTHOR_SPEC_TEMPLATE)["params"] == {
        "lookback": 252,
        "vol_window": 60,
    }


def test_exact_save_request_preserves_strategy_number_types_on_disk(
    tmp_path: Path,
) -> None:
    request = _exact_save_request(_AUTHOR_SPEC_TEMPLATE)
    artifact = tmp_path / "proposal.json"

    _write(artifact, {"exact_save_request": request})
    persisted = orjson.loads(artifact.read_bytes())["exact_save_request"]

    assert persisted["arguments_hash"] == canonical_request_hash(persisted["arguments"])
    spec = persisted["arguments"]["spec_json"]
    assert type(spec["constraints"][0]["params"]["max_weight"]) is float
    assert type(spec["execution"]["cost_model"]["slippage_bps"]) is float


def test_author_tool_records_safe_rejection_reason() -> None:
    payload = minimal_author_context(
        selection=_selection(),
        research_case=_research_case(),
        market=_market(),
        technical=_technical(),
    )
    tool = _CapturingAuthorDraftTool()

    with pytest.raises(ValueError, match="parameters escaped"):
        tool.invoke(
            arguments={
                "lookback": 63,
                "vol_window": 60,
                "signal_weights_choice": "balanced",
            },
            context=_context(
                payload=payload,
                decision_time=datetime(2026, 9, 1, 16, 21, tzinfo=UTC),
            ),
        )

    assert tool.rejection_reason == (
        "host_rejected_author_proposal:parameters_outside_frozen_choices"
    )


def test_author_tool_exposes_only_frozen_choices_and_builds_complete_spec() -> None:
    payload = minimal_author_context(
        selection=_selection(),
        research_case=_research_case(),
        market=_market(),
        technical=_technical(),
    )
    tool = _CapturingAuthorDraftTool()

    assert set(tool.spec.input_schema["properties"]) == {
        "lookback",
        "vol_window",
        "signal_weights_choice",
    }
    evidence = tool.invoke(
        arguments={
            "lookback": 126,
            "vol_window": 20,
            "signal_weights_choice": "momentum_tilt",
        },
        context=_context(
            payload=payload,
            decision_time=datetime(2026, 9, 1, 16, 21, tzinfo=UTC),
        ),
    )

    assert evidence.result["valid"] is True
    assert tool.arguments is not None
    assert tool.arguments["spec_json"]["params"] == {
        "lookback": 126,
        "vol_window": 20,
    }
    assert tool.arguments["spec_json"]["signal_weights"] == [0.6, 0.2, 0.2]
