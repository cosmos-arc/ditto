"""Signal Package canonical envelope contract tests."""

from __future__ import annotations

from copy import deepcopy

from ditto_application.signal_package_contract import (
    compute_signal_package_checksum,
    verify_signal_package_metadata,
)


def _metadata() -> dict[str, object]:
    batch_key = "eod-2026-01-30-stock-selection-7"
    payload: dict[str, object] = {
        "account_id": "paper-a",
        "cash_target": 0.5,
        "dataset_snapshot_ids": {"stock_daily": "sha256:stock"},
        "factor_ids": ["momentum_1m"],
        "factor_values": {"1": {"momentum_1m": 0.2}},
        "intents": [
            {
                "cash_impact": -2000.0,
                "current_weight": 0.1,
                "delta_weight": 0.2,
                "direction": "buy",
                "instrument_id": 1,
                "lot_size": 100,
                "quantity": 200,
                "raw_quantity": 200,
                "reference_price": 10.0,
                "rounded_quantity": 200,
                "signal_date": "2026-01-30",
                "sizing_readiness": "ready",
                "sizing_reason": "exact_board_lot",
                "status": "pending",
                "strategy_id": "stock-selection",
                "target_weight": 0.3,
            }
        ],
        "risk_flags": ["lot_size_checked"],
        "required_datasets": ["stock_daily"],
        "required_dataset_states": [
            {
                "dataset": "stock_daily",
                "reason": "",
                "snapshot_id": "sha256:stock",
                "status": "ready",
            }
        ],
        "selection_reasons": {
            "1": {
                "composite_score": 0.2,
                "industry": None,
                "instrument_id": 1,
                "negative_contributors": (),
                "positive_contributors": ("momentum_1m",),
                "rank": 1,
                "target_weight": 0.3,
            }
        },
        "signal_date": "2026-01-30",
        "sleeve_id": "manual-paper-a-stock-selection",
        "decision_date": "2026-01-30",
        "intended_trade_date": "2026-02-02",
        "strategy_id": "stock-selection",
        "strategy_version": "7",
    }
    checksum = compute_signal_package_checksum(payload)
    revision = checksum.removeprefix("sha256:")[:12]
    persisted_intents = deepcopy(payload["intents"])
    assert isinstance(persisted_intents, list)
    persisted_intents[0]["intent_id"] = f"sig-{batch_key}-2026-01-30-{revision}-1-buy"
    return {
        **payload,
        "schema_version": "1.0",
        "business_payload": payload,
        "batch_key": batch_key,
        "checksum": checksum,
        "no_rebalance": False,
        "outcome": "completed",
        "intents": persisted_intents,
    }


def test_contract_rejects_outcome_no_rebalance_mismatch() -> None:
    metadata = _metadata()
    metadata["no_rebalance"] = True

    assert verify_signal_package_metadata(metadata) is False


def test_contract_rejects_noncanonical_batch_envelope() -> None:
    metadata = _metadata()
    metadata["batch_key"] = "random-run"

    assert verify_signal_package_metadata(metadata) is False


def test_contract_rejects_unstable_persisted_intent_id() -> None:
    metadata = _metadata()
    intents = metadata["intents"]
    assert isinstance(intents, list)
    assert isinstance(intents[0], dict)
    intents[0]["intent_id"] = "random-intent"

    assert verify_signal_package_metadata(metadata) is False
