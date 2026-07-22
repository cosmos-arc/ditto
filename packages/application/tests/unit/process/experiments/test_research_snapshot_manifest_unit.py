"""Unit tests for the exact research snapshot manifest trust boundary."""

from __future__ import annotations

import hashlib
from dataclasses import FrozenInstanceError

import orjson
import pytest
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments.execution_bundle import (
    ContentAddressedResearchInput,
    ResearchSnapshotBinding,
)
from ditto_application.processes.experiments.execution_contracts import (
    ExactResearchSnapshot,
)
from ditto_application.processes.experiments.research_snapshot_manifest import (
    VerifiedResearchSnapshotManifest,
)


def _input(
    input_id: str,
    artifact_kind: str,
    *,
    content: str,
    schema: str,
) -> dict[str, object]:
    return {
        "input_id": input_id,
        "artifact_kind": artifact_kind,
        "content_hash": content * 64,
        "schema_hash": schema * 64,
    }


def _payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "snapshot_id": "snapshot-1",
        "dataset_id": "research-stock-daily",
        "source_snapshot_ids": ["provider-a", "provider-b"],
        "known_at_policy": "sample_time",
        "builder_version": "research-snapshot-builder-v1",
        "inputs": [
            _input("bars", "bars", content="1", schema="a"),
            _input("calendar", "calendar", content="2", schema="b"),
            _input(
                "instrument_rules",
                "instrument_rules",
                content="3",
                schema="c",
            ),
            _input("membership", "membership", content="4", schema="d"),
            _input("quality_roe@1", "factor", content="5", schema="e"),
        ],
    }


def _canonical(payload: object) -> bytes:
    return orjson.dumps(payload, option=orjson.OPT_SORT_KEYS)


def _exact(raw: bytes, *, snapshot_id: str = "snapshot-1") -> ExactResearchSnapshot:
    return ExactResearchSnapshot(
        snapshot_id,
        hashlib.sha256(raw).hexdigest(),
    )


def _assert_reason(
    exc_info: pytest.ExceptionInfo[AppProcessError], reason: str
) -> None:
    assert exc_info.value.details == {
        "code": "REPRODUCIBILITY_FAILED",
        "reason": reason,
    }


def test_verified_manifest_derives_immutable_binding_from_exact_bytes() -> None:
    payload = _payload()
    raw = _canonical(payload)

    verified = VerifiedResearchSnapshotManifest(
        exact_snapshot=_exact(raw),
        manifest_bytes=raw,
    )

    assert type(verified.snapshot_binding) is ResearchSnapshotBinding
    assert verified.manifest_bytes == raw
    assert verified.snapshot_binding.exact_snapshot == _exact(raw)
    assert verified.snapshot_binding.dataset_id == "research-stock-daily"
    assert verified.snapshot_binding.source_snapshot_ids == (
        "provider-a",
        "provider-b",
    )
    assert verified.snapshot_binding.known_at_policy == "sample_time"
    assert verified.snapshot_binding.builder_version == "research-snapshot-builder-v1"
    assert verified.snapshot_binding.inputs == (
        ContentAddressedResearchInput("bars", "bars", "1" * 64, "a" * 64),
        ContentAddressedResearchInput("calendar", "calendar", "2" * 64, "b" * 64),
        ContentAddressedResearchInput(
            "instrument_rules",
            "instrument_rules",
            "3" * 64,
            "c" * 64,
        ),
        ContentAddressedResearchInput(
            "membership",
            "membership",
            "4" * 64,
            "d" * 64,
        ),
        ContentAddressedResearchInput(
            "quality_roe@1",
            "factor",
            "5" * 64,
            "e" * 64,
        ),
    )
    with pytest.raises(FrozenInstanceError):
        verified.snapshot_binding = verified.snapshot_binding


@pytest.mark.parametrize("drift", ["input", "source"])
def test_verified_manifest_rejects_drift_while_retaining_old_manifest_hash(
    drift: str,
) -> None:
    original = _payload()
    original_bytes = _canonical(original)
    poisoned = _payload()
    if drift == "input":
        inputs = poisoned["inputs"]
        assert type(inputs) is list
        first = inputs[0]
        assert type(first) is dict
        first["content_hash"] = "9" * 64
    else:
        poisoned["source_snapshot_ids"] = ["provider-a", "provider-c"]

    with pytest.raises(AppProcessError) as exc_info:
        VerifiedResearchSnapshotManifest(
            exact_snapshot=_exact(original_bytes),
            manifest_bytes=_canonical(poisoned),
        )

    _assert_reason(exc_info, "snapshot_manifest_hash_mismatch")


def test_verified_manifest_rejects_noncanonical_exact_bytes() -> None:
    raw = orjson.dumps(_payload())
    assert raw != _canonical(_payload())

    with pytest.raises(AppProcessError) as exc_info:
        VerifiedResearchSnapshotManifest(
            exact_snapshot=_exact(raw),
            manifest_bytes=raw,
        )

    _assert_reason(exc_info, "noncanonical_snapshot_manifest")


@pytest.mark.parametrize("operation", ["extra", "missing"])
def test_verified_manifest_requires_the_exact_top_level_key_set(
    operation: str,
) -> None:
    payload = _payload()
    if operation == "extra":
        payload["path"] = "/mutable/latest.parquet"
    else:
        del payload["builder_version"]
    raw = _canonical(payload)

    with pytest.raises(AppProcessError) as exc_info:
        VerifiedResearchSnapshotManifest(
            exact_snapshot=_exact(raw),
            manifest_bytes=raw,
        )

    _assert_reason(exc_info, "invalid_snapshot_manifest_keys")


@pytest.mark.parametrize("operation", ["extra", "missing"])
def test_verified_manifest_requires_exact_input_payload_keys(operation: str) -> None:
    payload = _payload()
    inputs = payload["inputs"]
    assert type(inputs) is list
    first = inputs[0]
    assert type(first) is dict
    if operation == "extra":
        first["path"] = "/mutable/bars.parquet"
    else:
        del first["schema_hash"]
    raw = _canonical(payload)

    with pytest.raises(AppProcessError) as exc_info:
        VerifiedResearchSnapshotManifest(
            exact_snapshot=_exact(raw),
            manifest_bytes=raw,
        )

    _assert_reason(exc_info, "invalid_snapshot_manifest_input_keys")


def test_verified_manifest_rejects_duplicate_input_identity() -> None:
    payload = _payload()
    inputs = payload["inputs"]
    assert type(inputs) is list
    duplicate = dict(inputs[0])
    inputs.insert(1, duplicate)
    raw = _canonical(payload)

    with pytest.raises(AppProcessError) as exc_info:
        VerifiedResearchSnapshotManifest(
            exact_snapshot=_exact(raw),
            manifest_bytes=raw,
        )

    _assert_reason(exc_info, "duplicate_snapshot_manifest_input")


@pytest.mark.parametrize("kind", ["bars", "calendar", "membership", "instrument_rules"])
def test_verified_manifest_requires_each_execution_input_kind_exactly_once(
    kind: str,
) -> None:
    payload = _payload()
    inputs = payload["inputs"]
    assert type(inputs) is list
    payload["inputs"] = [item for item in inputs if item["artifact_kind"] != kind]
    raw = _canonical(payload)

    with pytest.raises(AppProcessError) as exc_info:
        VerifiedResearchSnapshotManifest(
            exact_snapshot=_exact(raw),
            manifest_bytes=raw,
        )

    _assert_reason(exc_info, "required_snapshot_input_missing_or_ambiguous")


def test_verified_manifest_rejects_duplicate_required_artifact_kind() -> None:
    payload = _payload()
    inputs = payload["inputs"]
    assert type(inputs) is list
    inputs.insert(1, _input("bars-copy", "bars", content="6", schema="f"))
    raw = _canonical(payload)

    with pytest.raises(AppProcessError) as exc_info:
        VerifiedResearchSnapshotManifest(
            exact_snapshot=_exact(raw),
            manifest_bytes=raw,
        )

    _assert_reason(exc_info, "required_snapshot_input_missing_or_ambiguous")


@pytest.mark.parametrize("field", ["source_snapshot_ids", "inputs"])
def test_verified_manifest_requires_stable_ordering(field: str) -> None:
    payload = _payload()
    values = payload[field]
    assert type(values) is list
    payload[field] = list(reversed(values))
    raw = _canonical(payload)

    with pytest.raises(AppProcessError) as exc_info:
        VerifiedResearchSnapshotManifest(
            exact_snapshot=_exact(raw),
            manifest_bytes=raw,
        )

    expected = (
        "noncanonical_snapshot_manifest_sources"
        if field == "source_snapshot_ids"
        else "noncanonical_snapshot_manifest_inputs"
    )
    _assert_reason(exc_info, expected)


def test_verified_manifest_rejects_duplicate_sources() -> None:
    payload = _payload()
    payload["source_snapshot_ids"] = ["provider-a", "provider-a"]
    raw = _canonical(payload)

    with pytest.raises(AppProcessError) as exc_info:
        VerifiedResearchSnapshotManifest(
            exact_snapshot=_exact(raw),
            manifest_bytes=raw,
        )

    _assert_reason(exc_info, "duplicate_snapshot_manifest_source")


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("schema_version", 2, "unsupported_snapshot_manifest_schema"),
        ("schema_version", True, "unsupported_snapshot_manifest_schema"),
        ("known_at_policy", "explicit_cutoff", "unsupported_known_at_policy"),
        ("dataset_id", " research-stock-daily", "invalid_snapshot_manifest_identity"),
        ("builder_version", "", "invalid_snapshot_manifest_identity"),
    ],
)
def test_verified_manifest_rejects_invalid_manifest_semantics(
    field: str,
    value: object,
    reason: str,
) -> None:
    payload = _payload()
    payload[field] = value
    raw = _canonical(payload)

    with pytest.raises(AppProcessError) as exc_info:
        VerifiedResearchSnapshotManifest(
            exact_snapshot=_exact(raw),
            manifest_bytes=raw,
        )

    _assert_reason(exc_info, reason)


def test_verified_manifest_requires_matching_snapshot_identity() -> None:
    raw = _canonical(_payload())

    with pytest.raises(AppProcessError) as exc_info:
        VerifiedResearchSnapshotManifest(
            exact_snapshot=_exact(raw, snapshot_id="snapshot-2"),
            manifest_bytes=raw,
        )

    _assert_reason(exc_info, "snapshot_manifest_identity_drift")


def test_verified_manifest_rejects_invalid_json_and_non_bytes() -> None:
    invalid = b"{not-json}"
    with pytest.raises(AppProcessError) as invalid_json:
        VerifiedResearchSnapshotManifest(
            exact_snapshot=_exact(invalid),
            manifest_bytes=invalid,
        )
    _assert_reason(invalid_json, "invalid_snapshot_manifest_json")

    with pytest.raises(AppProcessError) as invalid_bytes:
        VerifiedResearchSnapshotManifest(
            exact_snapshot=_exact(b"{}"),
            manifest_bytes=bytearray(b"{}"),  # type: ignore[arg-type]
        )
    _assert_reason(invalid_bytes, "invalid_snapshot_manifest_bytes")
