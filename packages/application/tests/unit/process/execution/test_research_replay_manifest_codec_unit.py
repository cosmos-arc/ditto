"""Research replay manifest codec preserves exact product context identity."""

from __future__ import annotations

import orjson
from ditto_application.processes.execution._research_replay_codec import (
    deserialize_manifest,
)
from ditto_backtest.context_inputs import ContextInputKind, ReplayContextInputRef
from ditto_backtest.manifest import RunManifest, RunMode, serialize_manifest
from ditto_strategy.alpha.parameters import canonical_parameter_hash


def test_context_inputs_round_trip_through_persisted_manifest_json() -> None:
    context_ref = ReplayContextInputRef(
        context_kind=ContextInputKind.TECHNICAL_ANALYSIS,
        context_id="technical-510300-2026-03-31",
        content_hash="a" * 64,
        as_of="2026-03-31T07:00:00Z",
        knowledge_cutoff="2026-03-31T06:30:00Z",
        publication_cutoff="2026-03-31T06:00:00Z",
        source_snapshot_ids=("bars-snapshot-1",),
    )
    manifest = RunManifest(
        run_id="run-context-codec",
        strategy_id="strategy-1",
        strategy_version="1",
        mode=RunMode.BACKTEST,
        created_at="2026-03-31T08:00:00Z",
        spec_hash="b" * 64,
        base_spec_hash="c" * 64,
        parameter_hash=canonical_parameter_hash(()),
        effective_parameters=(),
        research_snapshot_id=None,
        research_snapshot_manifest_hash=None,
        context_input_refs=(context_ref,),
    )

    raw = orjson.loads(serialize_manifest(manifest))
    restored = deserialize_manifest(raw)

    assert restored.context_input_refs == (context_ref,)
