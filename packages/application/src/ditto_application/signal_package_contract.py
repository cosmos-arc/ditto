"""Signal Package 的确定性 checksum 共享契约。"""

from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
from typing import cast

import orjson

__all__ = [
    "canonical_signal_package_metadata",
    "compute_signal_package_checksum",
    "verify_signal_package_metadata",
]


def compute_signal_package_checksum(payload: Mapping[str, object]) -> str:
    """对不含 ID/生成时间的确定性业务 payload 计算 checksum。"""
    data = orjson.dumps(payload, option=orjson.OPT_SORT_KEYS)
    return f"sha256:{sha256(data).hexdigest()}"


def verify_signal_package_metadata(metadata: Mapping[str, object]) -> bool:
    """校验持久化 package metadata，缺少可复算证据时 fail closed。"""
    expected = metadata.get("checksum")
    if not isinstance(expected, str) or not expected:
        return False
    payload = _business_payload(metadata)
    if payload is None:
        return False
    return (
        compute_signal_package_checksum(payload) == expected
        and _top_level_matches_payload(metadata, payload)
        and _outcome_matches_payload(metadata, payload)
        and _envelope_matches_payload(metadata, payload)
        and _stable_intent_ids_match(metadata, payload)
    )


def canonical_signal_package_metadata(
    metadata: Mapping[str, object],
) -> dict[str, object]:
    """
    Return checksum-covered facts from one canonical payload.

    The duplicated top-level metadata is never a business-fact source. Stable
    intent IDs are admitted only when their remaining payload exactly matches
    the canonical business intents; verification separately fails closed on
    any duplicated-field divergence.
    """
    payload = _business_payload(metadata)
    if payload is None:
        return {}
    canonical = dict(payload)
    canonical["intents"] = _validated_persisted_intents(
        metadata.get("intents"),
        payload.get("intents"),
    )
    expected = metadata.get("checksum")
    if isinstance(expected, str) and expected:
        canonical["checksum"] = expected
    return canonical


def _business_payload(metadata: Mapping[str, object]) -> dict[str, object] | None:
    raw_payload = metadata.get("business_payload")
    if isinstance(raw_payload, dict):
        return dict(cast(dict[str, object], raw_payload))
    return _legacy_business_payload(metadata)


def _top_level_matches_payload(
    metadata: Mapping[str, object],
    payload: Mapping[str, object],
) -> bool:
    for key, value in payload.items():
        if key == "intents":
            if not _persisted_intents_match(metadata.get(key), value):
                return False
        elif key not in metadata or metadata[key] != value:
            return False
    return True


def _outcome_matches_payload(
    metadata: Mapping[str, object],
    payload: Mapping[str, object],
) -> bool:
    intents = payload.get("intents")
    no_rebalance = metadata.get("no_rebalance")
    outcome = metadata.get("outcome")
    if not isinstance(intents, list) or not isinstance(no_rebalance, bool):
        return False
    expected_no_rebalance = not intents
    if no_rebalance is not expected_no_rebalance:
        return False
    expected_outcome = "no_rebalance" if expected_no_rebalance else "completed"
    return outcome in (expected_outcome, "rerun_conflict")


def _envelope_matches_payload(
    metadata: Mapping[str, object],
    payload: Mapping[str, object],
) -> bool:
    if metadata.get("schema_version") != "1.0" or not isinstance(
        metadata.get("business_payload"), dict
    ):
        return False
    strategy_id = payload.get("strategy_id")
    strategy_version = payload.get("strategy_version")
    signal_date = payload.get("signal_date")
    if not all(
        isinstance(value, str) and value
        for value in (strategy_id, strategy_version, signal_date)
    ):
        return False
    expected_batch = f"eod-{signal_date}-{strategy_id}-{strategy_version}"
    return metadata.get("batch_key") == expected_batch


def _stable_intent_ids_match(
    metadata: Mapping[str, object],
    payload: Mapping[str, object],
) -> bool:
    persisted = metadata.get("intents")
    batch_key = metadata.get("batch_key")
    checksum = metadata.get("checksum")
    signal_date = payload.get("signal_date")
    if not (
        isinstance(persisted, list)
        and isinstance(batch_key, str)
        and isinstance(checksum, str)
        and checksum.startswith("sha256:")
        and isinstance(signal_date, str)
    ):
        return False
    revision = checksum.removeprefix("sha256:")[:12]
    for raw_intent in cast(list[object], persisted):
        if not isinstance(raw_intent, dict):
            return False
        intent = cast(dict[str, object], raw_intent)
        instrument_id = intent.get("instrument_id")
        direction = intent.get("direction")
        if not isinstance(instrument_id, int) or not isinstance(direction, str):
            return False
        expected = (
            f"sig-{batch_key}-{signal_date}-{revision}-{instrument_id}-{direction}"
        )
        if intent.get("intent_id") != expected:
            return False
    return True


def _persisted_intents_match(persisted: object, business: object) -> bool:
    return bool(_validated_persisted_intents(persisted, business)) or (
        isinstance(persisted, list)
        and isinstance(business, list)
        and not persisted
        and not business
    )


def _validated_persisted_intents(  # noqa: PLR0911 - malformed evidence fails closed
    persisted: object,
    business: object,
) -> list[dict[str, object]]:
    if not isinstance(persisted, list) or not isinstance(business, list):
        return []
    persisted_items = cast(list[object], persisted)
    business_items = cast(list[object], business)
    if len(persisted_items) != len(business_items):
        return []

    normalized_persisted: list[dict[str, object]] = []
    persisted_payloads: list[bytes] = []
    intent_ids: set[str] = set()
    for raw_item in persisted_items:
        if not isinstance(raw_item, dict):
            return []
        item = dict(cast(dict[str, object], raw_item))
        intent_id = item.get("intent_id")
        if not isinstance(intent_id, str) or not intent_id or intent_id in intent_ids:
            return []
        intent_ids.add(intent_id)
        payload = {key: value for key, value in item.items() if key != "intent_id"}
        persisted_payloads.append(orjson.dumps(payload, option=orjson.OPT_SORT_KEYS))
        normalized_persisted.append(item)

    business_payloads: list[bytes] = []
    for raw_item in business_items:
        if not isinstance(raw_item, dict):
            return []
        business_payloads.append(orjson.dumps(raw_item, option=orjson.OPT_SORT_KEYS))
    if sorted(persisted_payloads) != sorted(business_payloads):
        return []
    return normalized_persisted


def _legacy_business_payload(
    metadata: Mapping[str, object],
) -> dict[str, object] | None:
    """复算 R1 schema 1.0 package；无法无歧义恢复时返回 None。"""
    required_keys = (
        "dataset_snapshot_ids",
        "factor_ids",
        "factor_values",
        "intents",
        "risk_flags",
        "selection_reasons",
        "signal_date",
        "strategy_id",
        "strategy_version",
    )
    if any(key not in metadata for key in required_keys):
        return None
    raw_intents = metadata["intents"]
    if not isinstance(raw_intents, list):
        return None
    intents: list[dict[str, object]] = []
    for raw_intent in cast(list[object], raw_intents):
        if not isinstance(raw_intent, dict):
            return None
        intent = {
            str(key): value
            for key, value in cast(dict[object, object], raw_intent).items()
            if str(key) != "intent_id"
        }
        intents.append(dict(sorted(intent.items())))
    return {
        "dataset_snapshot_ids": metadata["dataset_snapshot_ids"],
        "factor_ids": metadata["factor_ids"],
        "factor_values": metadata["factor_values"],
        "intents": intents,
        "risk_flags": metadata["risk_flags"],
        "selection_reasons": metadata["selection_reasons"],
        "signal_date": metadata["signal_date"],
        "strategy_id": metadata["strategy_id"],
        "strategy_version": metadata["strategy_version"],
    }
