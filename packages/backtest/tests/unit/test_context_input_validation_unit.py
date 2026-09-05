"""PIT visibility and identity tests for replay context evidence."""

from __future__ import annotations

from typing import cast

import pytest
from ditto_backtest.context_inputs import (
    ContextInputKind,
    ReplayContextInputRef,
    normalize_context_input_refs,
)

_DIGEST = "a" * 64


def _ref(**overrides: object) -> ReplayContextInputRef:
    values: dict[str, object] = {
        "context_kind": ContextInputKind.MARKET_CONTEXT,
        "context_id": "market-cn",
        "content_hash": _DIGEST,
        "as_of": "2026-09-04T09:30:00Z",
        "knowledge_cutoff": "2026-09-04T09:30:00Z",
        "publication_cutoff": "2026-09-04T09:29:59Z",
        "source_snapshot_ids": ("snapshot:b", "snapshot:a"),
    }
    values.update(overrides)
    return ReplayContextInputRef(
        context_kind=cast(ContextInputKind, values["context_kind"]),
        context_id=cast(str, values["context_id"]),
        content_hash=cast(str, values["content_hash"]),
        as_of=cast(str, values["as_of"]),
        knowledge_cutoff=cast(str, values["knowledge_cutoff"]),
        publication_cutoff=cast(str, values["publication_cutoff"]),
        source_snapshot_ids=cast(tuple[str, ...], values["source_snapshot_ids"]),
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("context_id", ""),
        ("context_id", " market-cn"),
        ("context_id", "market/cn"),
        ("context_id", "market\\cn"),
        ("source_snapshot_ids", ("",)),
        ("source_snapshot_ids", ("snapshot/a",)),
    ],
)
def test_context_identities_reject_ambiguous_values(field: str, value: object) -> None:
    with pytest.raises(ValueError, match="canonical identity"):
        _ref(**{field: value})


@pytest.mark.parametrize("value", ["", "A" * 64, "a" * 63, 7])
def test_context_hash_requires_exact_lowercase_sha256(value: object) -> None:
    with pytest.raises(ValueError, match="lowercase SHA-256"):
        _ref(content_hash=value)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("as_of", ""),
        ("as_of", "not-a-timestamp"),
        ("as_of", "2026-09-04T09:30:00"),
        ("knowledge_cutoff", "2026-02-30T00:00:00Z"),
    ],
)
def test_context_timestamps_require_valid_timezone_aware_rfc3339(
    field: str,
    value: object,
) -> None:
    with pytest.raises(ValueError, match=r"timestamp|timezone aware"):
        _ref(**{field: value})


def test_context_kind_requires_exact_enum_member() -> None:
    with pytest.raises(ValueError, match="exact ContextInputKind"):
        _ref(context_kind="market_context")


@pytest.mark.pit
def test_future_publication_sentinel_is_rejected_at_decision_boundary() -> None:
    """A fact published one microsecond after T must never enter replay evidence."""
    boundary = _ref(
        as_of="2026-09-04T09:30:00.000000Z",
        knowledge_cutoff="2026-09-04T09:30:00.000000Z",
        publication_cutoff="2026-09-04T09:30:00.000000Z",
    )
    assert boundary.as_of == "2026-09-04T09:30:00Z"

    with pytest.raises(ValueError, match="PIT cutoffs exceed"):
        _ref(
            as_of="2026-09-04T09:30:00.000000Z",
            knowledge_cutoff="2026-09-04T09:30:00.000000Z",
            publication_cutoff="2026-09-04T09:30:00.000001Z",
        )


def test_context_snapshots_are_nonempty_unique_and_canonically_sorted() -> None:
    assert _ref().source_snapshot_ids == ("snapshot:a", "snapshot:b")
    with pytest.raises(ValueError, match="non-empty and unique"):
        _ref(source_snapshot_ids=())
    with pytest.raises(ValueError, match="non-empty and unique"):
        _ref(source_snapshot_ids=("snapshot:a", "snapshot:a"))


def test_context_reference_collection_is_typed_unique_and_sorted() -> None:
    market = _ref()
    technical = _ref(
        context_kind=ContextInputKind.TECHNICAL_ANALYSIS,
        context_id="technical-cn",
        content_hash="b" * 64,
    )
    assert normalize_context_input_refs((technical, market)) == (market, technical)

    with pytest.raises(ValueError, match="must be a tuple"):
        normalize_context_input_refs([market])
    with pytest.raises(ValueError, match="must contain"):
        normalize_context_input_refs((object(),))
    with pytest.raises(ValueError, match="unique kind and context identity"):
        normalize_context_input_refs((market, market))
