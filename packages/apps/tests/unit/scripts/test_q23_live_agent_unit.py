"""Minimal approved-research egress for the real Q2/Q3 GLM briefs."""

from __future__ import annotations

from ditto_apps.scripts.q23_live_agent import (
    minimal_market_payload,
    minimal_selection_payload,
    minimal_technical_payload,
)


def test_market_egress_keeps_derived_context_without_raw_provider_rows() -> None:
    payload = minimal_market_payload(
        {
            "status": "degraded",
            "regime_label": "risk_on",
            "regime_score": 0.28,
            "metrics": [{"name": "breadth", "value": 0.47}],
            "drivers": [{"name": "breadth", "contribution": 0.13}],
            "impacts": [{"target": "cyclical", "direction": "supportive"}],
            "missing_inputs": ["macro_surprise_score"],
            "uncertainties": ["macro_surprise_score_not_derivable"],
            "source_snapshot_set_id": "snapshot-set:sha256:market",
            "source_snapshot_ids": ["snapshot:tushare:stock_daily:sha256:one"],
            "raw_rows": [{"close": 1.0}],
        }
    )

    assert payload["regime_label"] == "risk_on"
    assert payload["metrics"] == ({"name": "breadth", "value": 0.47},)
    assert "raw_rows" not in payload


def test_selection_egress_is_top_three_plus_one_exact_exclusion() -> None:
    payload = minimal_selection_payload(
        {
            "run_id": "selection-run:sha256:one",
            "status": "ready",
            "seed": 20240901,
            "source_snapshot_ids": ["snapshot:tushare:stock_daily:sha256:one"],
            "candidates": [
                {
                    "rank": rank,
                    "instrument_id": rank,
                    "instrument_name": f"stock-{rank}",
                    "score": rank / 10,
                }
                for rank in range(1, 6)
            ],
            "exclusions": [
                {
                    "instrument_id": 100,
                    "instrument_name": "other",
                    "reason_code": "suspended",
                    "stage": "hard_filter",
                    "detail": "instrument_is_suspended",
                },
                {
                    "instrument_id": 1_003_251,
                    "instrument_name": "贵州茅台",
                    "reason_code": "below_top_k",
                    "stage": "ranking",
                    "detail": "eligible_score_below_top_k",
                },
            ],
        }
    )

    assert payload["candidate_count"] == 5
    assert payload["exclusion_count"] == 2
    assert len(payload["top_candidates"]) == 3
    assert payload["focus_exclusion"]["instrument_id"] == 1_003_251
    assert "candidates" not in payload
    assert "exclusions" not in payload


def test_technical_egress_omits_full_indicator_matrix() -> None:
    payload = minimal_technical_payload(
        {
            "snapshot_id": "technical-analysis:sha256:one",
            "status": "degraded",
            "instrument_id": 1_003_251,
            "instrument_name": "贵州茅台",
            "selection_run_id": "selection-run:sha256:one",
            "last_visible_bar_at": "2024-03-29T07:00:00Z",
            "source_snapshot_ids": ["snapshot:tushare:stock_daily:sha256:history"],
            "timeframe_summaries": [{"timeframe": "daily", "trend": "bullish"}],
            "levels": [{"timeframe": "daily", "kind": "support", "price": 1700.53}],
            "conflicts": [
                {"dimension": "momentum", "daily": "neutral", "weekly": "bullish"}
            ],
            "missing_inputs": [
                "daily:relative_return_benchmark:missing_reference_series"
            ],
            "readings": [
                {
                    "timeframe": "daily",
                    "name": "rsi",
                    "status": "ready",
                    "value": 52.96,
                },
                {
                    "timeframe": "daily",
                    "name": "turnover",
                    "status": "ready",
                    "value": 2_290_584.0,
                },
            ],
        }
    )

    assert payload["selected_readings"] == (
        {"timeframe": "daily", "name": "rsi", "status": "ready", "value": 52.96},
    )
    assert "readings" not in payload
