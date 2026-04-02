"""SQLite-backed writer for research control-plane metadata."""

from __future__ import annotations

import orjson
from ditto_analytics.models.research import (
    ResearchDatasetSnapshotRecord,
    ResearchDatasetSpecRecord,
    ResearchSpineSnapshotRecord,
    ResearchSpineSpecRecord,
)
from ditto_data.stores.sqlite_client import SQLiteClient

__all__ = ["SQLiteResearchCatalogWriter"]


class SQLiteResearchCatalogWriter:
    """
    Persist research specs and snapshots into SQLite.

    Each ``write_*`` method executes SQL and immediately commits.
    For batch operations that require a single transaction, use the
    ``execute_*`` methods (SQL without commit) together with
    ``commit()`` / ``rollback()``.
    """

    def __init__(self, sqlite_client: SQLiteClient) -> None:
        self._sqlite_client = sqlite_client

    # --- transaction control (UoW) ---

    def commit(self) -> None:
        """Commit the current transaction."""
        self._sqlite_client.commit()

    def rollback(self) -> None:
        """Roll back the current transaction."""
        self._sqlite_client.rollback()

    # --- execute methods (no commit) ---

    def execute_spine_spec(self, record: ResearchSpineSpecRecord) -> None:
        """Execute spine spec INSERT without committing."""
        self._sqlite_client.execute(
            """
            INSERT OR REPLACE INTO research_spine_spec (
                spine_id, universe_id, calendar, grain,
                entity_key, description, created_at, version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.spine_id,
                record.universe_id,
                record.calendar,
                record.grain,
                record.entity_key,
                record.description,
                record.created_at,
                record.version,
            ),
        )

    def execute_dataset_spec(self, record: ResearchDatasetSpecRecord) -> None:
        """Execute dataset spec INSERT without committing."""
        self._sqlite_client.execute(
            """
            INSERT OR REPLACE INTO research_dataset_spec (
                dataset_id, spine_id, derived_ids, join_policy,
                known_at_policy, late_arrival_policy, description, created_at,
                version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.dataset_id,
                record.spine_id,
                orjson.dumps(record.derived_ids).decode(),
                record.join_policy,
                record.known_at_policy,
                record.late_arrival_policy,
                record.description,
                record.created_at,
                record.version,
            ),
        )

    def execute_spine_snapshot(self, record: ResearchSpineSnapshotRecord) -> None:
        """Execute spine snapshot INSERT without committing."""
        self._sqlite_client.execute(
            """
            INSERT OR REPLACE INTO research_spine_snapshot (
                spine_snapshot_id, spine_id, snapshot_start, snapshot_end,
                row_count, data_path, manifest_hash, created_at, version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.spine_snapshot_id,
                record.spine_id,
                record.snapshot_start,
                record.snapshot_end,
                record.row_count,
                record.data_path,
                record.manifest_hash,
                record.created_at,
                record.version,
            ),
        )

    def execute_dataset_snapshot(self, record: ResearchDatasetSnapshotRecord) -> None:
        """Execute dataset snapshot INSERT without committing."""
        self._sqlite_client.execute(
            """
            INSERT OR REPLACE INTO research_dataset_snapshot (
                snapshot_id, dataset_id, dataset_spec_version, spine_snapshot_id,
                snapshot_start, snapshot_end, row_count, data_path,
                manifest_hash, known_at_policy, effective_cutoff,
                spine_spec_version, resolved_versions, resolved_inputs,
                source_snapshot_ids, builder_version, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.snapshot_id,
                record.dataset_id,
                record.dataset_spec_version,
                record.spine_snapshot_id,
                record.snapshot_start,
                record.snapshot_end,
                record.row_count,
                record.data_path,
                record.manifest_hash,
                record.known_at_policy,
                record.effective_cutoff,
                record.spine_spec_version,
                orjson.dumps(record.resolved_versions).decode(),
                orjson.dumps(record.resolved_inputs).decode(),
                orjson.dumps(record.source_snapshot_ids).decode(),
                record.builder_version,
                record.created_at,
            ),
        )

    # --- write methods (execute + commit, backward-compatible) ---

    def write_spine_spec(self, record: ResearchSpineSpecRecord) -> None:
        """Persist one spine spec row."""
        self.execute_spine_spec(record)
        self.commit()

    def write_dataset_spec(self, record: ResearchDatasetSpecRecord) -> None:
        """Persist one dataset spec row."""
        self.execute_dataset_spec(record)
        self.commit()

    def write_spine_snapshot(self, record: ResearchSpineSnapshotRecord) -> None:
        """Persist one spine snapshot row."""
        self.execute_spine_snapshot(record)
        self.commit()

    def write_dataset_snapshot(self, record: ResearchDatasetSnapshotRecord) -> None:
        """Persist one dataset snapshot row."""
        self.execute_dataset_snapshot(record)
        self.commit()
