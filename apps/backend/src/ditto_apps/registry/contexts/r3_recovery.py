"""Composition helpers for fail-closed R3 recovery verification."""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from ditto_analysis.storage.sqlite.experiments import (
    ResearchExperimentDatabase,
    SQLiteExperimentReader,
)
from ditto_analysis.storage.sqlite.experiments import schema as research_schema
from ditto_data.config.data_store import DataStoreSettings
from ditto_platform.foundation import SQLitePool
from ditto_strategy.governance.service import GovernanceService
from ditto_strategy.storage.sqlite import strategy_governance_schema
from ditto_strategy.storage.sqlite.strategy_governance_store import (
    SQLiteStrategyGovernanceStore,
)

__all__ = [
    "ActiveStrategyRecoveryEvidence",
    "DatabaseSchemaRecoveryEvidence",
    "GovernanceDecisionRecoveryEvidence",
    "HoldoutClaimRecoveryEvidence",
    "PinnedReviewPacketRecoveryEvidence",
    "R3DomainRecoveryEvidence",
    "R3RecoveryVerificationError",
    "R3SchemaRecoveryEvidence",
    "capture_r3_domain_evidence",
    "inspect_r3_schema_evidence",
    "resolve_metadata_database",
    "verify_restored_r3_domain",
]


class R3RecoveryVerificationError(RuntimeError):
    """Raised when schema or domain recovery evidence cannot be proven."""


@dataclass(frozen=True, slots=True)
class DatabaseSchemaRecoveryEvidence:
    """Stable SQLite schema marker and fingerprint evidence."""

    application_id: int
    user_version: int
    schema_fingerprint: str
    schema_row_count: int
    required_tables: tuple[str, ...]
    required_triggers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class R3SchemaRecoveryEvidence:
    """Schema evidence for both members of the R3 recovery unit."""

    governance: DatabaseSchemaRecoveryEvidence
    research: DatabaseSchemaRecoveryEvidence


@dataclass(frozen=True, slots=True)
class ActiveStrategyRecoveryEvidence:
    """Active pointer plus its immutable strategy-version identity."""

    strategy_id: str
    active_version: int
    pointer_revision: int
    activation_event_id: str
    parent_version: int | None
    schema_version: int
    spec_hash: str
    created_at: str


@dataclass(frozen=True, slots=True)
class GovernanceDecisionRecoveryEvidence:
    """One append-only governance decision."""

    event_id: str
    strategy_id: str
    version: int
    decision: str
    actor: str
    reason: str
    decided_at: str


@dataclass(frozen=True, slots=True)
class HoldoutClaimRecoveryEvidence:
    """Canonical identity of one immutable holdout claim."""

    claim_id: str
    experiment_id: str
    candidate_id: str
    fold_id: str
    reproduction_fingerprint: str
    logical_run_id: str
    claim_payload_hash: str


@dataclass(frozen=True, slots=True)
class PinnedReviewPacketRecoveryEvidence:
    """Typed identity needed to reopen one pinned review packet."""

    artifact_id: str
    relative_path: str
    bundle_hash: str
    reproduction_fingerprint: str
    byte_size: int


@dataclass(frozen=True, slots=True)
class R3DomainRecoveryEvidence:
    """Domain-level recovery evidence bound into the backup manifest."""

    active_strategies: tuple[ActiveStrategyRecoveryEvidence, ...]
    decision_history: tuple[GovernanceDecisionRecoveryEvidence, ...]
    holdout_claims: tuple[HoldoutClaimRecoveryEvidence, ...]
    pinned_review_packets: tuple[PinnedReviewPacketRecoveryEvidence, ...]


def resolve_metadata_database(
    data_root: Path,
    *,
    sqlite_path: Path | None = None,
) -> Path:
    """Resolve the metadata DB through ``DataStoreSettings`` and its env override."""
    effective_override = sqlite_path
    if effective_override is None:
        raw_override = os.getenv("SQLITE_PATH")
        if raw_override:
            effective_override = Path(raw_override)
    settings = DataStoreSettings(
        data_root=data_root,
        sqlite_path=effective_override,
    )
    return settings.resolved_sqlite_path.expanduser().resolve(strict=False)


def inspect_r3_schema_evidence(
    *,
    metadata_database: Path,
    research_database: Path,
    include_wal: bool,
) -> R3SchemaRecoveryEvidence:
    """Read and validate canonical governance and Research Schema v1."""
    governance = _inspect_governance_schema(
        metadata_database,
        include_wal=include_wal,
    )
    research = _inspect_research_schema(
        research_database,
        include_wal=include_wal,
    )
    return R3SchemaRecoveryEvidence(governance=governance, research=research)


def capture_r3_domain_evidence(
    *,
    metadata_database: Path,
    research_database: Path,
    include_wal: bool,
) -> R3DomainRecoveryEvidence:
    """Capture exact recovery identities through read-only SQLite connections."""
    with _read_only_connection(
        metadata_database,
        include_wal=include_wal,
    ) as metadata:
        pointer_count = int(
            metadata.execute("SELECT COUNT(*) FROM strategy_active_pointer").fetchone()[
                0
            ]
        )
        active_rows = metadata.execute(
            """
            SELECT pointer.strategy_id, pointer.active_version,
                   pointer.pointer_revision, pointer.activation_event_id,
                   version.parent_version, version.schema_version,
                   version.spec_hash, version.created_at
            FROM strategy_active_pointer AS pointer
            JOIN strategy_version AS version
              ON version.strategy_id=pointer.strategy_id
             AND version.version=pointer.active_version
            ORDER BY pointer.strategy_id
            """
        ).fetchall()
        decision_rows = metadata.execute(
            """
            SELECT event_id, strategy_id, version, decision, actor, reason,
                   decided_at
            FROM strategy_decision_event
            ORDER BY rowid
            """
        ).fetchall()
    with _read_only_connection(
        research_database,
        include_wal=include_wal,
    ) as research:
        claim_rows = research.execute(
            """
            SELECT claim_id, experiment_id, candidate_id, fold_id,
                   reproduction_fingerprint, logical_run_id, claim_payload_hash
            FROM holdout_claim
            ORDER BY claim_id
            """
        ).fetchall()
        packet_rows = research.execute(
            """
            SELECT artifact_id, relative_path, content_hash,
                   reproduction_fingerprint, byte_size
            FROM research_artifact
            WHERE is_pinned=1 AND artifact_kind='review_packet'
            ORDER BY artifact_id
            """
        ).fetchall()
    if not active_rows or len(active_rows) != pointer_count or not decision_rows:
        raise R3RecoveryVerificationError("governance recovery evidence is incomplete")
    if not claim_rows or not packet_rows:
        raise R3RecoveryVerificationError("research recovery evidence is incomplete")
    return R3DomainRecoveryEvidence(
        active_strategies=tuple(
            ActiveStrategyRecoveryEvidence(
                strategy_id=str(row[0]),
                active_version=int(row[1]),
                pointer_revision=int(row[2]),
                activation_event_id=str(row[3]),
                parent_version=None if row[4] is None else int(row[4]),
                schema_version=int(row[5]),
                spec_hash=str(row[6]),
                created_at=str(row[7]),
            )
            for row in active_rows
        ),
        decision_history=tuple(
            GovernanceDecisionRecoveryEvidence(
                event_id=str(row[0]),
                strategy_id=str(row[1]),
                version=int(row[2]),
                decision=str(row[3]),
                actor=str(row[4]),
                reason=str(row[5]),
                decided_at=str(row[6]),
            )
            for row in decision_rows
        ),
        holdout_claims=tuple(
            HoldoutClaimRecoveryEvidence(
                claim_id=str(row[0]),
                experiment_id=str(row[1]),
                candidate_id=str(row[2]),
                fold_id=str(row[3]),
                reproduction_fingerprint=str(row[4]),
                logical_run_id=str(row[5]),
                claim_payload_hash=str(row[6]),
            )
            for row in claim_rows
        ),
        pinned_review_packets=tuple(
            PinnedReviewPacketRecoveryEvidence(
                artifact_id=str(row[0]),
                relative_path=str(row[1]),
                bundle_hash=str(row[2]),
                reproduction_fingerprint=str(row[3]),
                byte_size=int(row[4]),
            )
            for row in packet_rows
        ),
    )


def verify_restored_r3_domain(
    *,
    data_root: Path,
    metadata_database: Path,
    expected: R3DomainRecoveryEvidence,
) -> R3DomainRecoveryEvidence:
    """Reopen canonical services and compare restored domain identities."""
    actual = capture_r3_domain_evidence(
        metadata_database=metadata_database,
        research_database=data_root / "research" / "research.sqlite",
        include_wal=True,
    )
    if actual != expected:
        raise R3RecoveryVerificationError(
            "restored R3 domain evidence does not match backup"
        )

    pool = SQLitePool(str(metadata_database))
    store = SQLiteStrategyGovernanceStore(pool)
    service = GovernanceService(store)
    try:
        for evidence in expected.active_strategies:
            pointer = store.get_active_pointer(evidence.strategy_id)
            version = service.get_version(
                evidence.strategy_id,
                evidence.active_version,
            )
            if (
                pointer is None
                or version is None
                or pointer.active_version != evidence.active_version
                or pointer.pointer_revision != evidence.pointer_revision
                or pointer.activation_event_id != evidence.activation_event_id
                or version.parent_version != evidence.parent_version
                or version.schema_version != evidence.schema_version
                or version.spec_hash != evidence.spec_hash
                or version.created_at != evidence.created_at
            ):
                raise R3RecoveryVerificationError(
                    "restored governance service identity does not match backup"
                )
    finally:
        pool.close_all()

    database = ResearchExperimentDatabase(data_root)
    reader = SQLiteExperimentReader(database)
    try:
        for evidence in expected.holdout_claims:
            claim = reader.get_holdout_claim(evidence.claim_id)
            if (
                claim is None
                or str(claim.fold_key.experiment_id) != evidence.experiment_id
                or str(claim.fold_key.candidate_id) != evidence.candidate_id
                or str(claim.fold_key.fold_id) != evidence.fold_id
                or str(claim.reproduction_fingerprint)
                != evidence.reproduction_fingerprint
                or claim.logical_run_id != evidence.logical_run_id
                or str(claim.claim_payload_hash) != evidence.claim_payload_hash
            ):
                raise R3RecoveryVerificationError(
                    "restored holdout claim does not match backup"
                )
        for evidence in expected.pinned_review_packets:
            artifact = reader.get_artifact(evidence.artifact_id)
            packet = reader.get_review_packet(evidence.bundle_hash)
            if (
                artifact is None
                or packet is None
                or not artifact.is_pinned
                or artifact.relative_path != evidence.relative_path
                or str(artifact.content_hash) != evidence.bundle_hash
                or str(artifact.reproduction_fingerprint)
                != evidence.reproduction_fingerprint
                or artifact.byte_size != evidence.byte_size
                or str(packet.bundle_hash) != evidence.bundle_hash
                or packet.holdout_claim_id
                not in {item.claim_id for item in expected.holdout_claims}
            ):
                raise R3RecoveryVerificationError(
                    "restored pinned review packet does not match backup"
                )
    finally:
        database.close_all()
    return actual


def _inspect_governance_schema(
    database: Path,
    *,
    include_wal: bool,
) -> DatabaseSchemaRecoveryEvidence:
    with _read_only_connection(database, include_wal=include_wal) as connection:
        application_id = int(connection.execute("PRAGMA application_id").fetchone()[0])
        user_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        rows = strategy_governance_schema.schema_rows(connection)
    fingerprint = strategy_governance_schema.schema_fingerprint(rows)
    if (
        application_id != strategy_governance_schema.APPLICATION_ID
        or user_version != strategy_governance_schema.USER_VERSION
        or fingerprint != strategy_governance_schema.SCHEMA_FINGERPRINT
        or len(rows) != strategy_governance_schema.SCHEMA_ROW_COUNT
        or tuple(row[1] for row in rows if row[0] == "table")
        != strategy_governance_schema.REQUIRED_TABLES
    ):
        raise R3RecoveryVerificationError(
            "governance schema marker or fingerprint is not canonical"
        )
    return DatabaseSchemaRecoveryEvidence(
        application_id=application_id,
        user_version=user_version,
        schema_fingerprint=fingerprint,
        schema_row_count=len(rows),
        required_tables=strategy_governance_schema.REQUIRED_TABLES,
        required_triggers=(),
    )


def _inspect_research_schema(
    database: Path,
    *,
    include_wal: bool,
) -> DatabaseSchemaRecoveryEvidence:
    with _read_only_connection(database, include_wal=include_wal) as connection:
        application_id = int(connection.execute("PRAGMA application_id").fetchone()[0])
        user_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        rows = research_schema.schema_rows(connection)
    fingerprint = research_schema.schema_fingerprint(rows)
    if (
        application_id != research_schema.APPLICATION_ID
        or user_version != research_schema.USER_VERSION
        or fingerprint != research_schema.SCHEMA_FINGERPRINT
        or len(rows) != research_schema.SCHEMA_ROW_COUNT
    ):
        raise R3RecoveryVerificationError(
            "research schema marker or fingerprint is not canonical"
        )
    return DatabaseSchemaRecoveryEvidence(
        application_id=application_id,
        user_version=user_version,
        schema_fingerprint=fingerprint,
        schema_row_count=len(rows),
        required_tables=tuple(str(row[1]) for row in rows if str(row[0]) == "table"),
        required_triggers=tuple(
            str(row[1]) for row in rows if str(row[0]) == "trigger"
        ),
    )


@contextmanager
def _read_only_connection(
    database: Path,
    *,
    include_wal: bool,
) -> Generator[sqlite3.Connection]:
    path = database.expanduser().absolute()
    query = "mode=ro" if include_wal else "mode=ro&immutable=1"
    try:
        connection = sqlite3.connect(f"{path.as_uri()}?{query}", uri=True)
    except sqlite3.Error as exc:
        raise R3RecoveryVerificationError(
            f"cannot open recovery database read-only: {path}"
        ) from exc
    try:
        yield connection
    finally:
        connection.close()
