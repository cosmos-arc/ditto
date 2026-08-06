"""Unit tests for indexed research execution input resolver and artifact loader."""

from __future__ import annotations

import hashlib
import threading
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, date, datetime
from io import BytesIO
from pathlib import Path
from typing import cast

import orjson
import polars as pl
import pytest
from ditto_analysis.errors import ExperimentConflictError
from ditto_analysis.experiments.artifact_manifest import ArtifactPublicationSpec
from ditto_analysis.experiments.models import (
    AttemptId,
    CandidateId,
    ContentHash,
    ExperimentId,
    FoldId,
)
from ditto_analysis.experiments.persistence import ArtifactRecord, LeaseFence
from ditto_analysis.research.artifact_service import ResearchArtifactService
from ditto_application.builders.code_environment import build_code_environment_lock
from ditto_application.builders.research_artifact_loader import (
    IndexedResearchArtifactLoader,
)
from ditto_application.builders.research_input_resolver import (
    IndexedResearchInputsResolver,
)
from ditto_application.processes.experiments._execution_bundle_inputs import (
    CodeEnvironmentLock,
    ContentAddressedResearchInput,
)
from ditto_application.processes.experiments._execution_resolution_evidence import (
    FrozenResearchExecutionInputs,
    FrozenResearchInputRequest,
)
from ditto_application.processes.experiments.execution_contracts import (
    ExactResearchSnapshot,
    ExactUniverseIdentity,
)
from ditto_application.processes.experiments.research_data_artifacts import (
    VerifiedResearchFrame,
)
from ditto_application.processes.experiments.research_policy_artifact import (
    VerifiedInstrumentRulesArtifact,
)
from ditto_kernel.exceptions import DittoError

NOW = datetime(2026, 7, 26, 1, 2, 3, 456789, tzinfo=UTC)
NOW_US = 1_778_000_000_000_000
FENCE = LeaseFence(
    experiment_id=ExperimentId("experiment-inputs"),
    owner_token="resolver-test",
    revision=1,
    lease_until_epoch_us=NOW_US + 1_000,
)
SNAPSHOT_ID = "certified-snapshot-inputs"
DATASET_ID = "research-etf-rotation"
SOURCE_SNAPSHOT_ID = "provider-snapshot-inputs"


class _MemoryArtifactIndex:
    """Thread-safe test port mirroring the SQLite artifact index contract."""

    def __init__(self, artifact_root: Path | None = None) -> None:
        self.artifact_root = None if artifact_root is None else artifact_root.resolve()
        self.records: dict[str, ArtifactRecord] = {}
        self._lock = threading.Lock()

    def get_artifact(self, artifact_id: str) -> ArtifactRecord | None:
        with self._lock:
            return self.records.get(artifact_id)

    def get_artifact_by_relative_path(
        self,
        relative_path: str,
    ) -> ArtifactRecord | None:
        with self._lock:
            return next(
                (
                    record
                    for record in self.records.values()
                    if record.relative_path == relative_path
                ),
                None,
            )

    def add_artifact(
        self,
        record: ArtifactRecord,
        *,
        lease_fence: LeaseFence,
        now_epoch_us: int,
        commit_guard: Callable[[], None],
    ) -> None:
        _ = (lease_fence, now_epoch_us)
        with self._lock:
            commit_guard()
            matches = tuple(
                item
                for item in self.records.values()
                if item.artifact_id == record.artifact_id
                or item.relative_path == record.relative_path
            )
            if not matches:
                self.records[record.artifact_id] = record
                return
            existing = matches[0]
            if replace(existing, is_pinned=False, pinned_at=None, revision=0) != record:
                raise ExperimentConflictError(
                    "artifact replay drift",
                    details={"reason_code": "artifact_replay_drift"},
                )

    def pin_artifact(
        self,
        artifact_id: str,
        *,
        expected_revision: int,
        pinned_at: datetime,
        commit_guard: Callable[[], None],
    ) -> ArtifactRecord:
        with self._lock:
            current = self.records.get(artifact_id)
            if (
                current is None
                or current.is_pinned
                or current.revision != expected_revision
            ):
                raise ExperimentConflictError(
                    "artifact pin revision is stale",
                    details={"reason_code": "stale_artifact_revision"},
                )
            commit_guard()
            pinned = replace(
                current,
                is_pinned=True,
                pinned_at=pinned_at,
                revision=expected_revision + 1,
            )
            self.records[artifact_id] = pinned
            return pinned


def _publication_spec(
    artifact_id: str,
    *,
    kind: str,
    suffix: str,
) -> ArtifactPublicationSpec:
    return ArtifactPublicationSpec(
        artifact_id=artifact_id,
        experiment_id=ExperimentId("experiment-inputs"),
        candidate_id=CandidateId("candidate-inputs"),
        fold_id=FoldId("fold-inputs"),
        attempt_id=AttemptId("attempt-inputs"),
        artifact_kind=kind,
        relative_path=(
            "experiments/experiment-inputs/candidates/candidate-inputs/"
            f"folds/fold-inputs/attempts/attempt-inputs/{artifact_id}.{suffix}"
        ),
        reproduction_fingerprint=ContentHash("a" * 64),
        audit={
            "run_id": "run-inputs",
            "attempt_id": "attempt-inputs",
            "created_at": NOW.isoformat(),
        },
        created_at=NOW,
    )


def _indexed_service(
    tmp_path: Path,
    index: _MemoryArtifactIndex,
) -> ResearchArtifactService:
    return ResearchArtifactService(
        artifact_root=tmp_path,
        artifact_reader=index,
        artifact_writer=index,
    )


def _rules_frame(source_snapshot_id: str = SOURCE_SNAPSHOT_ID) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "instrument_code": ["510300.SH"],
            "instrument_id": [2_000_001],
            "asset_class": ["etf"],
            "exchange": ["XSHG"],
            "currency": ["CNY"],
            "tick_size": [0.001],
            "lot_size": [100],
            "multiplier": [1.0],
            "board_segment": ["fund"],
            "lifecycle_state": ["normal"],
            "ipo_date": [date(2012, 5, 28)],
            "delisting_date": [None],
            "as_of_date": [date(2026, 1, 1)],
            "known_at": [date(2025, 12, 31)],
            "settlement_cycle": [1],
            "fund_settlement_cycle": [0],
            "price_limit_pct": [0.1],
            "order_types_supported": [["market", "limit"]],
            "call_auction_sessions": [["open", "close"]],
            "commission_rate": [0.0003],
            "min_commission": [5.0],
            "stamp_duty_rate": [0.0],
            "transfer_fee_rate": [0.00001],
            "source_snapshot_id": [source_snapshot_id],
        },
        schema={
            "instrument_code": pl.String,
            "instrument_id": pl.Int64,
            "asset_class": pl.String,
            "exchange": pl.String,
            "currency": pl.String,
            "tick_size": pl.Float64,
            "lot_size": pl.Int64,
            "multiplier": pl.Float64,
            "board_segment": pl.String,
            "lifecycle_state": pl.String,
            "ipo_date": pl.Date,
            "delisting_date": pl.Date,
            "as_of_date": pl.Date,
            "known_at": pl.Date,
            "settlement_cycle": pl.Int64,
            "fund_settlement_cycle": pl.Int64,
            "price_limit_pct": pl.Float64,
            "order_types_supported": pl.List(pl.String),
            "call_auction_sessions": pl.List(pl.String),
            "commission_rate": pl.Float64,
            "min_commission": pl.Float64,
            "stamp_duty_rate": pl.Float64,
            "transfer_fee_rate": pl.Float64,
            "source_snapshot_id": pl.String,
        },
    )


def _rules_artifact_evidence(
    source_snapshot_id: str = SOURCE_SNAPSHOT_ID,
) -> tuple[ContentAddressedResearchInput, bytes]:
    frame = _rules_frame(source_snapshot_id)
    buffer = BytesIO()
    frame.write_parquet(buffer)
    artifact_bytes = buffer.getvalue()
    schema_hash = hashlib.sha256(
        orjson.dumps(tuple((name, str(dtype)) for name, dtype in frame.schema.items()))
    ).hexdigest()
    evidence = ContentAddressedResearchInput(
        input_id="instrument_rules",
        artifact_kind="instrument_rules",
        content_hash=hashlib.sha256(artifact_bytes).hexdigest(),
        schema_hash=schema_hash,
    )
    return evidence, artifact_bytes


def _bars_frame(source_snapshot_id: str = SOURCE_SNAPSHOT_ID) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "trade_date": [date(2026, 1, 5), date(2026, 1, 6)],
            "instrument_id": [2_000_001, 2_000_001],
            "open": [1.0, 1.1],
            "high": [1.1, 1.2],
            "low": [0.9, 1.0],
            "close": [1.05, 1.15],
            "prev_close": [0.95, 1.05],
            "volume": [1000.0, 1100.0],
            "amount": [1050.0, 1265.0],
            "is_suspended": [False, False],
            "limit_up": [False, False],
            "limit_down": [False, False],
            "avg_volume_20d": [950.0, 980.0],
            "source_snapshot_id": [source_snapshot_id, source_snapshot_id],
        },
    )


def _bars_artifact_evidence(
    source_snapshot_id: str = SOURCE_SNAPSHOT_ID,
) -> tuple[ContentAddressedResearchInput, bytes]:
    frame = _bars_frame(source_snapshot_id)
    buffer = BytesIO()
    frame.write_parquet(buffer)
    artifact_bytes = buffer.getvalue()
    schema_hash = hashlib.sha256(
        orjson.dumps(tuple((name, str(dtype)) for name, dtype in frame.schema.items()))
    ).hexdigest()
    evidence = ContentAddressedResearchInput(
        input_id="etf_daily",
        artifact_kind="bars",
        content_hash=hashlib.sha256(artifact_bytes).hexdigest(),
        schema_hash=schema_hash,
    )
    return evidence, artifact_bytes


def _snapshot_manifest_inputs(
    rules_evidence: ContentAddressedResearchInput,
    *,
    bars_evidence: ContentAddressedResearchInput | None = None,
    membership_hash: str = "9" * 64,
) -> tuple[ContentAddressedResearchInput, ...]:
    """Build the canonical input tuple embedded in the snapshot manifest.

    The resolver only loads the manifest and the instrument_rules artifact.
    Bars/calendar/membership content hashes are still embedded in the manifest
    so the resolver's trust boundary can attest the complete input set; their
    bytes are only published by tests that actually exercise the loader.
    """
    bars = bars_evidence or ContentAddressedResearchInput(
        "etf_daily",
        "bars",
        "1" * 64,
        "2" * 64,
    )
    return (
        ContentAddressedResearchInput("calendar", "calendar", "3" * 64, "4" * 64),
        bars,
        rules_evidence,
        ContentAddressedResearchInput(
            "membership",
            "membership",
            membership_hash,
            "8" * 64,
        ),
    )


def _snapshot_manifest_bytes(
    inputs: tuple[ContentAddressedResearchInput, ...],
) -> bytes:
    return orjson.dumps(
        {
            "schema_version": 1,
            "snapshot_id": SNAPSHOT_ID,
            "dataset_id": DATASET_ID,
            "source_snapshot_ids": [SOURCE_SNAPSHOT_ID],
            "known_at_policy": "sample_time",
            "builder_version": "research-builder-v1",
            "inputs": [
                dict(item.as_payload())
                for item in sorted(inputs, key=lambda item: item.input_id)
            ],
        },
        option=orjson.OPT_SORT_KEYS,
    )


def _frozen_input_request(
    manifest_bytes: bytes,
    *,
    membership_hash: str = "9" * 64,
    manifest_hash_override: str | None = None,
) -> FrozenResearchInputRequest:
    snapshot = ExactResearchSnapshot(
        SNAPSHOT_ID,
        manifest_hash_override
        if manifest_hash_override is not None
        else hashlib.sha256(manifest_bytes).hexdigest(),
    )
    return FrozenResearchInputRequest(
        snapshot=snapshot,
        dataset_id=DATASET_ID,
        source_snapshot_ids=(SOURCE_SNAPSHOT_ID,),
        known_at_policy="sample_time",
        builder_version="research-builder-v1",
        universe=ExactUniverseIdentity("research-universe", membership_hash),
        membership_projection_hash="b" * 64,
    )


def _publish_indexed_parquet(
    service: ResearchArtifactService,
    artifact_id: str,
    frame: pl.DataFrame,
) -> ArtifactRecord:
    return service.publish_indexed_parquet(
        _publication_spec(artifact_id, kind=artifact_id, suffix="parquet"),
        frame,
        lease_fence=FENCE,
        now_epoch_us=NOW_US,
    )


def _publish_indexed_json(
    service: ResearchArtifactService,
    artifact_id: str,
    payload: dict[str, object],
) -> ArtifactRecord:
    return service.publish_indexed_json(
        _publication_spec(artifact_id, kind=artifact_id, suffix="json"),
        payload,
        lease_fence=FENCE,
        now_epoch_us=NOW_US,
    )


class TestIndexedResearchInputsResolver:
    """Verify the indexed resolver rebuilds frozen inputs from real artifact bytes."""

    def test_resolve_returns_verified_frozen_research_execution_inputs(
        self,
        tmp_path: Path,
    ) -> None:
        index = _MemoryArtifactIndex(tmp_path)
        service = _indexed_service(tmp_path, index)
        rules_evidence, rules_bytes = _rules_artifact_evidence()
        _publish_indexed_parquet(service, rules_evidence.input_id, _rules_frame())
        manifest_inputs = _snapshot_manifest_inputs(rules_evidence)
        manifest_bytes = _snapshot_manifest_bytes(manifest_inputs)
        _publish_indexed_json(service, SNAPSHOT_ID, orjson.loads(manifest_bytes))
        resolver = IndexedResearchInputsResolver(artifact_service=service)
        request = _frozen_input_request(manifest_bytes)

        result = resolver.resolve(request)

        assert type(result) is FrozenResearchExecutionInputs
        assert result.universe == request.universe
        assert result.membership_projection_hash == request.membership_projection_hash
        snapshot_binding = result.snapshot_manifest.snapshot_binding
        assert snapshot_binding.exact_snapshot == request.snapshot
        assert snapshot_binding.dataset_id == DATASET_ID
        assert snapshot_binding.source_snapshot_ids == (SOURCE_SNAPSHOT_ID,)
        assert result.instrument_rules.input_evidence == rules_evidence
        assert (
            result.instrument_rules.evidence.verified_content_hash
            == hashlib.sha256(rules_bytes).hexdigest()
        )
        assert result.instrument_rules.source_snapshot_ids == (SOURCE_SNAPSHOT_ID,)

    def test_resolve_fails_closed_on_manifest_hash_drift(
        self,
        tmp_path: Path,
    ) -> None:
        index = _MemoryArtifactIndex(tmp_path)
        service = _indexed_service(tmp_path, index)
        rules_evidence, _rules_bytes = _rules_artifact_evidence()
        _publish_indexed_parquet(service, rules_evidence.input_id, _rules_frame())
        manifest_inputs = _snapshot_manifest_inputs(rules_evidence)
        manifest_bytes = _snapshot_manifest_bytes(manifest_inputs)
        _publish_indexed_json(service, SNAPSHOT_ID, orjson.loads(manifest_bytes))
        resolver = IndexedResearchInputsResolver(artifact_service=service)
        request = _frozen_input_request(
            manifest_bytes,
            manifest_hash_override="0" * 64,
        )

        with pytest.raises(DittoError) as exc_info:
            resolver.resolve(request)

        assert exc_info.value.details["reason"] == "snapshot_manifest_hash_mismatch"

    def test_resolve_fails_closed_when_manifest_artifact_missing(
        self,
        tmp_path: Path,
    ) -> None:
        index = _MemoryArtifactIndex(tmp_path)
        service = _indexed_service(tmp_path, index)
        rules_evidence, _rules_bytes = _rules_artifact_evidence()
        _publish_indexed_parquet(service, rules_evidence.input_id, _rules_frame())
        manifest_inputs = _snapshot_manifest_inputs(rules_evidence)
        manifest_bytes = _snapshot_manifest_bytes(manifest_inputs)
        resolver = IndexedResearchInputsResolver(artifact_service=service)
        request = _frozen_input_request(manifest_bytes)

        with pytest.raises(DittoError) as exc_info:
            resolver.resolve(request)

        # Manifest artifact was never published, so the indexed lookup must fail
        # closed before the manifest trust boundary executes. Analysis-layer
        # integrity errors surface ``reason_code`` rather than ``reason``.
        assert exc_info.value.details["reason_code"] == "artifact_not_indexed"

    def test_resolve_fails_closed_when_rules_artifact_missing(
        self,
        tmp_path: Path,
    ) -> None:
        index = _MemoryArtifactIndex(tmp_path)
        service = _indexed_service(tmp_path, index)
        rules_evidence, _rules_bytes = _rules_artifact_evidence()
        # Publish the manifest referencing rules evidence, but never publish the
        # actual rules artifact bytes. The resolver must fail closed on the
        # missing instrument_rules artifact lookup.
        manifest_inputs = _snapshot_manifest_inputs(rules_evidence)
        manifest_bytes = _snapshot_manifest_bytes(manifest_inputs)
        _publish_indexed_json(service, SNAPSHOT_ID, orjson.loads(manifest_bytes))
        resolver = IndexedResearchInputsResolver(artifact_service=service)
        request = _frozen_input_request(manifest_bytes)

        with pytest.raises(DittoError) as exc_info:
            resolver.resolve(request)

        assert exc_info.value.details["reason_code"] == "artifact_not_indexed"
        assert exc_info.value.details["artifact_id"] == rules_evidence.input_id


class TestIndexedResearchArtifactLoader:
    """Verify the indexed loader rebuilds verified artifacts from real bytes."""

    def test_load_frame_returns_verified_research_frame(
        self,
        tmp_path: Path,
    ) -> None:
        index = _MemoryArtifactIndex(tmp_path)
        service = _indexed_service(tmp_path, index)
        evidence, artifact_bytes = _bars_artifact_evidence()
        _publish_indexed_parquet(service, evidence.input_id, _bars_frame())
        loader = IndexedResearchArtifactLoader(artifact_service=service)

        result = loader.load_frame(evidence)

        assert type(result) is VerifiedResearchFrame
        assert result.input_evidence == evidence
        assert (
            result.verified_content_hash == hashlib.sha256(artifact_bytes).hexdigest()
        )
        assert result.source_snapshot_ids == (SOURCE_SNAPSHOT_ID,)
        assert result.frame["instrument_id"].to_list() == [2_000_001, 2_000_001]

    def test_load_instrument_rules_returns_verified_artifact(
        self,
        tmp_path: Path,
    ) -> None:
        index = _MemoryArtifactIndex(tmp_path)
        service = _indexed_service(tmp_path, index)
        evidence, artifact_bytes = _rules_artifact_evidence()
        _publish_indexed_parquet(service, evidence.input_id, _rules_frame())
        loader = IndexedResearchArtifactLoader(artifact_service=service)

        result = loader.load_instrument_rules(evidence)

        assert type(result) is VerifiedInstrumentRulesArtifact
        assert result.input_evidence == evidence
        assert (
            result.evidence.verified_content_hash
            == hashlib.sha256(artifact_bytes).hexdigest()
        )
        assert result.source_snapshot_ids == (SOURCE_SNAPSHOT_ID,)
        assert result.resolve_instrument_id("510300.SH") == 2_000_001

    def test_load_frame_fails_closed_on_hash_drift(
        self,
        tmp_path: Path,
    ) -> None:
        index = _MemoryArtifactIndex(tmp_path)
        service = _indexed_service(tmp_path, index)
        evidence, _artifact_bytes = _bars_artifact_evidence()
        _publish_indexed_parquet(service, evidence.input_id, _bars_frame())
        loader = IndexedResearchArtifactLoader(artifact_service=service)
        drifted = replace(evidence, content_hash="0" * 64)

        with pytest.raises(DittoError) as exc_info:
            loader.load_frame(drifted)

        assert exc_info.value.details["reason"] == "frame_content_hash_mismatch"

    def test_load_instrument_rules_fails_closed_when_artifact_missing(
        self,
        tmp_path: Path,
    ) -> None:
        index = _MemoryArtifactIndex(tmp_path)
        service = _indexed_service(tmp_path, index)
        evidence, _artifact_bytes = _rules_artifact_evidence()
        loader = IndexedResearchArtifactLoader(artifact_service=service)

        with pytest.raises(DittoError) as exc_info:
            loader.load_instrument_rules(evidence)

        assert exc_info.value.details["reason_code"] == "artifact_not_indexed"

    def test_load_frame_fails_closed_when_artifact_missing(
        self,
        tmp_path: Path,
    ) -> None:
        index = _MemoryArtifactIndex(tmp_path)
        service = _indexed_service(tmp_path, index)
        evidence, _artifact_bytes = _bars_artifact_evidence()
        loader = IndexedResearchArtifactLoader(artifact_service=service)

        with pytest.raises(DittoError) as exc_info:
            loader.load_frame(evidence)

        assert exc_info.value.details["reason_code"] == "artifact_not_indexed"


class TestBuildCodeEnvironmentLock:
    """Verify the composition-root code environment lock helper."""

    def test_build_code_environment_lock_returns_typed_lock(self) -> None:
        git_commit_sha = "a" * 40
        environment_lock_hash = "b" * 64

        lock = build_code_environment_lock(
            git_commit_sha=git_commit_sha,
            environment_lock_hash=environment_lock_hash,
        )

        assert type(lock) is CodeEnvironmentLock
        assert lock.code_version == git_commit_sha
        assert lock.environment_lock_hash == environment_lock_hash
        assert lock.as_payload() == {
            "code_version": git_commit_sha,
            "environment_lock_hash": environment_lock_hash,
        }

    def test_build_code_environment_lock_propagates_validation_errors(
        self,
    ) -> None:
        """Weak composition-root inputs surface typed errors from the lock."""
        with pytest.raises(DittoError):
            build_code_environment_lock(
                git_commit_sha="",
                environment_lock_hash="b" * 64,
            )

        with pytest.raises(DittoError):
            build_code_environment_lock(
                git_commit_sha="a" * 40,
                environment_lock_hash="not-a-sha",
            )


def test_resolver_and_loader_round_trip_through_indexed_artifacts(
    tmp_path: Path,
) -> None:
    """Drive resolver and loader from the same indexed publication in one flow."""
    index = _MemoryArtifactIndex(tmp_path)
    service = _indexed_service(tmp_path, index)
    rules_evidence, _rules_bytes = _rules_artifact_evidence()
    bars_evidence, _bars_bytes = _bars_artifact_evidence()
    _publish_indexed_parquet(service, rules_evidence.input_id, _rules_frame())
    _publish_indexed_parquet(service, bars_evidence.input_id, _bars_frame())
    manifest_inputs = _snapshot_manifest_inputs(
        rules_evidence,
        bars_evidence=bars_evidence,
    )
    manifest_bytes = _snapshot_manifest_bytes(manifest_inputs)
    _publish_indexed_json(service, SNAPSHOT_ID, orjson.loads(manifest_bytes))
    resolver = IndexedResearchInputsResolver(artifact_service=service)
    loader = IndexedResearchArtifactLoader(artifact_service=service)
    request = _frozen_input_request(manifest_bytes)

    inputs = resolver.resolve(request)
    rules = loader.load_instrument_rules(inputs.instrument_rules.input_evidence)
    bars = loader.load_frame(
        cast(
            "ContentAddressedResearchInput",
            next(
                item
                for item in inputs.snapshot_binding.inputs
                if item.artifact_kind == "bars"
            ),
        ),
    )

    assert rules.input_evidence == inputs.instrument_rules.input_evidence
    assert bars.input_evidence.artifact_kind == "bars"
    assert bars.source_snapshot_ids == (SOURCE_SNAPSHOT_ID,)
