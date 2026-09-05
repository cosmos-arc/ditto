"""Signal Package canonical envelope contract tests."""

from __future__ import annotations

from copy import deepcopy

import pytest
from ditto_application.signal_package_contract import (
    canonical_signal_package_metadata,
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


def _payload(metadata: dict[str, object]) -> dict[str, object]:
    payload = metadata["business_payload"]
    assert isinstance(payload, dict)
    return payload


def _intents(metadata: dict[str, object]) -> list[object]:
    intents = metadata["intents"]
    assert isinstance(intents, list)
    return intents


def test_contract_requires_checksum_and_recomputable_business_payload() -> None:
    for checksum in (None, ""):
        metadata = _metadata()
        metadata["checksum"] = checksum
        assert verify_signal_package_metadata(metadata) is False

    metadata = _metadata()
    metadata["checksum"] = "sha256:" + "0" * 64
    assert verify_signal_package_metadata(metadata) is False

    metadata = _metadata()
    del metadata["business_payload"]
    del metadata["factor_ids"]
    assert verify_signal_package_metadata(metadata) is False
    assert canonical_signal_package_metadata(metadata) == {}


def test_every_duplicated_business_fact_must_equal_the_checksum_payload() -> None:
    metadata = _metadata()
    metadata["cash_target"] = 0.4
    assert verify_signal_package_metadata(metadata) is False

    metadata = _metadata()
    persisted = _intents(metadata)[0]
    assert isinstance(persisted, dict)
    persisted["quantity"] = 100
    assert verify_signal_package_metadata(metadata) is False


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("no_rebalance", "false"),
        ("outcome", "unknown"),
        ("schema_version", "2.0"),
        ("business_payload", []),
        ("strategy_id", ""),
        ("strategy_version", 7),
        ("signal_date", None),
    ],
)
def test_outcome_and_envelope_fields_are_exactly_typed(
    field_name: str,
    value: object,
) -> None:
    metadata = _metadata()
    metadata[field_name] = value

    assert verify_signal_package_metadata(metadata) is False


def test_checksum_valid_payload_still_requires_nonempty_envelope_identity() -> None:
    metadata = _metadata()
    payload = _payload(metadata)
    payload["strategy_id"] = ""
    metadata["strategy_id"] = ""
    metadata["checksum"] = compute_signal_package_checksum(payload)

    assert verify_signal_package_metadata(metadata) is False


def test_no_rebalance_is_the_only_valid_empty_intent_outcome() -> None:
    metadata = _metadata()
    payload = _payload(metadata)
    payload["intents"] = []
    metadata["intents"] = []
    metadata["no_rebalance"] = True
    metadata["outcome"] = "no_rebalance"
    metadata["checksum"] = compute_signal_package_checksum(payload)

    assert verify_signal_package_metadata(metadata) is True

    metadata["outcome"] = "rerun_conflict"
    assert verify_signal_package_metadata(metadata) is True


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("intents", "not-a-list"),
        ("batch_key", 1),
        ("checksum", "not-sha256"),
    ],
)
def test_stable_intent_identity_requires_a_complete_envelope(
    field_name: str,
    value: object,
) -> None:
    metadata = _metadata()
    metadata[field_name] = value

    assert verify_signal_package_metadata(metadata) is False


def test_stable_intent_identity_rejects_untyped_business_keys() -> None:
    metadata = _metadata()
    metadata["intents"] = ["not-an-object"]
    assert verify_signal_package_metadata(metadata) is False

    metadata = _metadata()
    intent = _intents(metadata)[0]
    assert isinstance(intent, dict)
    intent["instrument_id"] = "1"
    assert verify_signal_package_metadata(metadata) is False

    metadata = _metadata()
    intent = _intents(metadata)[0]
    assert isinstance(intent, dict)
    intent["direction"] = 1
    assert verify_signal_package_metadata(metadata) is False


@pytest.mark.parametrize(
    ("field_name", "value"), [("instrument_id", "1"), ("direction", 1)]
)
def test_checksum_valid_intent_still_requires_typed_identity_components(
    field_name: str,
    value: object,
) -> None:
    metadata = _metadata()
    payload = _payload(metadata)
    business_intents = payload["intents"]
    assert isinstance(business_intents, list)
    business_intent = business_intents[0]
    persisted_intent = _intents(metadata)[0]
    assert isinstance(business_intent, dict)
    assert isinstance(persisted_intent, dict)
    business_intent[field_name] = value
    persisted_intent[field_name] = value
    metadata["checksum"] = compute_signal_package_checksum(payload)

    assert verify_signal_package_metadata(metadata) is False


def test_persisted_intents_require_unique_ids_and_exact_business_multiset() -> None:
    metadata = _metadata()
    payload = _payload(metadata)
    business_intent = payload["intents"]
    assert isinstance(business_intent, list)
    payload["intents"] = [*business_intent, *business_intent]
    assert canonical_signal_package_metadata(metadata)["intents"] == []

    metadata = _metadata()
    intent = _intents(metadata)[0]
    assert isinstance(intent, dict)
    intent["intent_id"] = ""
    assert canonical_signal_package_metadata(metadata)["intents"] == []

    metadata = _metadata()
    payload = _payload(metadata)
    business_intent = payload["intents"]
    assert isinstance(business_intent, list)
    persisted = _intents(metadata)[0]
    assert isinstance(persisted, dict)
    duplicate = dict(persisted)
    metadata["intents"] = [persisted, duplicate]
    payload["intents"] = [*business_intent, *business_intent]
    assert canonical_signal_package_metadata(metadata)["intents"] == []

    metadata = _metadata()
    _payload(metadata)["intents"] = ["not-an-object"]
    assert canonical_signal_package_metadata(metadata)["intents"] == []


def test_canonical_projection_recovers_only_unambiguous_legacy_business_facts() -> None:
    metadata = _metadata()
    del metadata["business_payload"]
    canonical = canonical_signal_package_metadata(metadata)

    assert canonical["strategy_id"] == "stock-selection"
    intent = canonical["intents"]
    assert isinstance(intent, list)
    assert isinstance(intent[0], dict)
    assert str(intent[0]["intent_id"]).startswith("sig-eod-")

    metadata = _metadata()
    del metadata["business_payload"]
    metadata["intents"] = "not-a-list"
    assert canonical_signal_package_metadata(metadata) == {}

    metadata = _metadata()
    del metadata["business_payload"]
    metadata["intents"] = ["not-an-object"]
    assert canonical_signal_package_metadata(metadata) == {}
