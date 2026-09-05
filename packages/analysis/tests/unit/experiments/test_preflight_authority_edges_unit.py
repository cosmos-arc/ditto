"""Strict decoding edges for persisted preflight authority evidence."""

from __future__ import annotations

from collections.abc import Callable
from typing import cast

import pytest
from ditto_analysis.errors import ExperimentIntegrityError
from ditto_analysis.experiments import preflight_authority
from ditto_analysis.experiments.models import ContentHash
from ditto_analysis.experiments.persistence import canonical_payload


def _hash(character: str = "a") -> str:
    return character * 64


def _window(start: str = "2024-01-01", end: str = "2024-01-31") -> dict[str, object]:
    return {"start": start, "end": end}


def _fold(
    *,
    ordinal: int = 1,
    role: str = "exploration",
    train_window: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "ordinal": ordinal,
        "role": role,
        "train_window": train_window,
        "test_window": _window(),
        "purge_sessions": 0,
        "embargo_sessions": 0,
    }


def _holdout(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "train_window": _window("2023-01-01", "2023-12-31"),
        "test_window": _window("2024-01-01", "2024-01-31"),
        "purge_sessions": 0,
        "embargo_sessions": 0,
    }
    value.update(overrides)
    return value


def _validation_plan(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "eligibility": "promotion_eligible",
        "reason_codes": [],
        "coverage_policy": {},
        "calendar_complete_month_count": 1,
        "eligible_months": [],
        "isolation_width_sessions": 0,
        "folds": [_fold()],
        "reserved_holdout": _holdout(),
    }
    value.update(overrides)
    return value


def _certification(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "ready": True,
        "profile": "strict",
        "required_from": "2024-01-01",
        "required_to": "2024-01-31",
        "dataset_ids": [],
        "report_ids": [],
        "reason_codes": [],
        "snapshot_evidence": {
            "snapshot_id": "snapshot-1",
            "dataset_id": "dataset-1",
            "manifest_hash": _hash("b"),
            "source_snapshot_ids": [],
            "snapshot_start": "2024-01-01",
            "snapshot_end": "2024-01-31",
            "known_at_policy": "strict",
            "builder_version": "1",
        },
    }
    value.update(overrides)
    return value


def _identities(**overrides: object) -> dict[str, object]:
    certification = _certification()
    value: dict[str, object] = {
        "request_hash": _hash("c"),
        "research_cycle_id": "cycle-1",
        "research_cycle_hash": _hash("d"),
        "strategy_id": "strategy-1",
        "strategy_version": 1,
        "snapshot_identity": {
            "snapshot_id": "snapshot-1",
            "manifest_hash": _hash("b"),
        },
        "dataset_requirements": [],
        "certification": certification,
    }
    value.update(overrides)
    return value


def _preflight(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schema_version": 1,
        "policy_version": "1",
        "status": "ready",
        "checks": [],
        "counts": {"planned_fold_count": 1},
        "validation": {
            "protocol": {},
            "plan": _validation_plan(),
            "fold_protocol": {},
        },
        "work": {},
        "executor": {},
        "authority": {
            "snapshot_identity": {
                "snapshot_id": "snapshot-1",
                "manifest_hash": _hash("b"),
            },
        },
        "identities": _identities(),
    }
    value.update(overrides)
    return value


def _plan(schema_version: int = 1, **overrides: object) -> dict[str, object]:
    keys = (
        preflight_authority._PLAN_PREIMAGE_KEYS_V1
        if schema_version == 1
        else preflight_authority._PLAN_PREIMAGE_KEYS_V2
    )
    value = dict.fromkeys(keys)
    value["schema_version"] = schema_version
    value.update(overrides)
    return value


def _detail(preflight: dict[str, object], plan: dict[str, object]) -> dict[str, object]:
    return {
        "plan_hash": str(canonical_payload(plan).content_hash),
        "plan_preimage": plan,
        "preflight": preflight,
        "preflight_hash": str(canonical_payload(preflight).content_hash),
    }


def _assert_invalid(action: Callable[[], object]) -> ExperimentIntegrityError:
    with pytest.raises(ExperimentIntegrityError) as exc_info:
        action()
    assert (
        exc_info.value.details["reason_code"] == "holdout_preflight_authority_invalid"
    )
    return exc_info.value


def test_scalar_decoders_reject_container_and_type_lookalikes() -> None:
    _assert_invalid(lambda: preflight_authority._mapping([], "value"))
    _assert_invalid(lambda: preflight_authority._list((), "value"))
    _assert_invalid(lambda: preflight_authority._integer(True, "value"))


def test_hash_date_window_and_json_comparison_fail_closed() -> None:
    _assert_invalid(lambda: preflight_authority._hash("not-a-hash", "hash"))
    _assert_invalid(lambda: preflight_authority._date("2024-02-30", "date"))
    _assert_invalid(
        lambda: preflight_authority._window(
            _window("2024-02-02", "2024-02-01"),
            "window",
        )
    )
    _assert_invalid(lambda: preflight_authority._same({"value": object()}, {}))


def test_hash_collection_is_nonempty_unless_explicitly_allowed() -> None:
    error = _assert_invalid(lambda: preflight_authority._hashes([], "hashes"))
    assert "must not be empty" in str(error)
    assert preflight_authority._hashes([], "hashes", allow_empty=True) == ()


def test_mutation_receipt_rejects_invalid_identity_before_accepting_detail() -> None:
    receipt = {
        "schema_version": 2,
        "kind": "ditto_mutation_receipt",
        "operation_id": "launch",
        "resource_id": "experiment-1",
        "key_hash": _hash("a"),
        "request_hash": _hash("b"),
        "response": {},
        "receipt_hash": _hash("c"),
    }
    detail = {
        "plan_hash": _hash("d"),
        "plan_preimage": {},
        "preflight": {},
        "preflight_hash": _hash("e"),
        "mutation_idempotency": receipt,
    }

    error = _assert_invalid(lambda: preflight_authority._detail_root(detail))

    assert "mutation receipt identity" in str(error)


@pytest.mark.parametrize(
    "check",
    [
        {
            "rule_id": "matrix",
            "outcome": "unknown",
            "code": None,
            "reason": None,
            "remediation": None,
            "observed": {},
            "policy": {},
        },
        {
            "rule_id": "matrix",
            "outcome": "pass",
            "code": "unexpected",
            "reason": None,
            "remediation": None,
            "observed": {},
            "policy": {},
        },
    ],
)
def test_check_authority_rejects_invalid_outcome_semantics(
    check: dict[str, object],
) -> None:
    _assert_invalid(lambda: preflight_authority._check_authority(check))


def test_fold_authority_rejects_role_and_window_semantic_mismatch() -> None:
    fold = _fold(role="walk_forward", train_window=None)

    error = _assert_invalid(lambda: preflight_authority._fold_authority(fold, "fold"))

    assert "invalid fold semantics" in str(error)


def test_fold_collection_requires_ordered_exploration_and_nonnegative_holdout() -> None:
    _assert_invalid(
        lambda: preflight_authority._fold_authorities(
            {"folds": []},
            _holdout(),
        )
    )
    _assert_invalid(
        lambda: preflight_authority._fold_authorities(
            {"folds": [_fold()]},
            _holdout(purge_sessions=-1),
        )
    )


def test_plan_links_fail_closed_on_first_cross_link_mismatch() -> None:
    preflight = _preflight()
    plan = {
        "validation_authority": {},
        "research_cycle_id": "different-cycle",
    }

    error = _assert_invalid(
        lambda: preflight_authority._verify_plan_links(plan, preflight)
    )

    assert "plan preimage does not match" in str(error)


def test_identity_links_reject_snapshot_cross_link_mismatch() -> None:
    preflight = _preflight(
        authority={
            "snapshot_identity": {
                "snapshot_id": "different-snapshot",
                "manifest_hash": _hash("b"),
            }
        }
    )

    error = _assert_invalid(lambda: preflight_authority._identity_links(preflight))

    assert "snapshot identities do not cross-link" in str(error)


def test_consumption_requires_certification_to_cover_holdout() -> None:
    preflight = _preflight()
    identity = preflight_authority._identity_links(preflight)
    certification = cast("dict[str, object]", identity.certification)
    certification["required_to"] = "2024-01-30"

    error = _assert_invalid(
        lambda: preflight_authority._consumption_links(
            preflight,
            identity,
            require_canonical_cycle_hash=False,
        )
    )

    assert "cutoff does not cover" in str(error)


def test_protocol_hash_must_bind_the_exact_validation_plan() -> None:
    validation_plan = _validation_plan()
    validation = {
        "plan": validation_plan,
        "fold_protocol": {
            "protocol_id": "walk-forward-v1",
            "protocol_version": 1,
            "protocol_hash": _hash("f"),
        },
    }

    error = _assert_invalid(lambda: preflight_authority._protocol_links(validation, {}))

    assert "protocol hash" in str(error)


def _check(
    rule_id: str,
    outcome: str = "pass",
) -> preflight_authority.PreflightCheckAuthority:
    return preflight_authority.PreflightCheckAuthority(
        rule_id=rule_id,
        outcome=outcome,
        code=None,
        reason=None,
        remediation=None,
        observed_json="{}",
        policy_json="{}",
    )


def test_launchable_status_requires_ready_certification() -> None:
    validation = {"plan": _validation_plan()}

    _assert_invalid(
        lambda: preflight_authority._validate_status_semantics(
            "ready",
            validation,
            {"ready": False},
            (),
        )
    )


def test_launchable_status_rejects_failed_gate() -> None:
    checks = tuple(
        _check(rule_id, "fail" if rule_id == "budget" else "pass")
        for rule_id in preflight_authority.PREFLIGHT_HARD_GATE_RULE_IDS
    )

    _assert_invalid(
        lambda: preflight_authority._validate_status_semantics(
            "research_only",
            {"plan": _validation_plan(eligibility="research_only")},
            {"ready": True},
            checks,
        )
    )


def test_ready_status_rejects_warning_gate() -> None:
    checks = tuple(
        _check(rule_id, "warn" if rule_id == "budget" else "pass")
        for rule_id in preflight_authority.PREFLIGHT_HARD_GATE_RULE_IDS
    )

    _assert_invalid(
        lambda: preflight_authority._validate_status_semantics(
            "ready",
            {"plan": _validation_plan()},
            {"ready": True},
            checks,
        )
    )


def test_certification_check_is_required_exactly_once_and_must_pass() -> None:
    identity = preflight_authority._identity_links(_preflight())

    error = _assert_invalid(
        lambda: preflight_authority._validate_certification_check_preimage(
            identity,
            (),
        )
    )

    assert "certification hard gate" in str(error)


def test_decode_rejects_unknown_plan_schema_shape() -> None:
    detail = {
        "plan_hash": _hash("a"),
        "plan_preimage": {"schema_version": 3},
        "preflight": _preflight(),
        "preflight_hash": _hash("b"),
    }

    _assert_invalid(lambda: preflight_authority.decode_preflight_authority(detail))


def test_decode_rejects_preflight_and_plan_hash_drift() -> None:
    preflight = _preflight()
    plan = _plan(preflight_hash=str(canonical_payload(preflight).content_hash))
    detail = _detail(preflight, plan)
    detail["preflight_hash"] = _hash("a")
    _assert_invalid(lambda: preflight_authority.decode_preflight_authority(detail))

    detail = _detail(preflight, plan)
    detail["plan_hash"] = _hash("b")
    _assert_invalid(lambda: preflight_authority.decode_preflight_authority(detail))


def test_decode_rejects_status_outside_closed_vocabulary() -> None:
    preflight = _preflight(status="unknown")
    preflight_hash = str(canonical_payload(preflight).content_hash)
    plan = _plan(preflight_hash=preflight_hash)

    _assert_invalid(
        lambda: preflight_authority.decode_preflight_authority(_detail(preflight, plan))
    )


def test_decode_wraps_unexpected_reconstruction_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def explode(_detail: object) -> tuple[dict[str, object], ContentHash]:
        raise RuntimeError("unexpected")

    monkeypatch.setattr(preflight_authority, "_detail_root", explode)

    error = _assert_invalid(lambda: preflight_authority.decode_preflight_authority({}))

    assert "cannot be reconstructed" in str(error)
