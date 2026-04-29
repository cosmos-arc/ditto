"""SQLite-backed reader for research control-plane metadata."""

from __future__ import annotations

import orjson
from ditto_kernel.research import (
    ResearchDatasetSnapshotRecord,
    ResearchDatasetSpecRecord,
    ResearchSpineSnapshotRecord,
    ResearchSpineSpecRecord,
)

from ditto_data.storage.sqlite_client import SQLiteClient

__all__ = ["SQLiteResearchCatalogReader"]


class SQLiteResearchCatalogReader:
    """Read research specs and snapshots from SQLite."""

    def __init__(self, sqlite_client: SQLiteClient) -> None:
        self._sqlite_client = sqlite_client

    def read_spine_spec(self, spine_id: str) -> ResearchSpineSpecRecord | None:
        """Read one research spine spec record."""
        row = self._sqlite_client.fetchone(
            """
            SELECT spine_id, universe_id, calendar, grain, entity_key,
                   description, created_at, version
            FROM research_spine_spec
            WHERE spine_id = ?
            """,
            (spine_id,),
        )
        if row is None:
            return None
        return ResearchSpineSpecRecord(
            spine_id=row["spine_id"],
            universe_id=row["universe_id"],
            calendar=row["calendar"],
            grain=row["grain"],
            entity_key=row["entity_key"],
            description=row["description"],
            created_at=row["created_at"],
            version=row["version"],
        )

    def read_dataset_spec(
        self,
        dataset_id: str,
    ) -> ResearchDatasetSpecRecord | None:
        """Read one research dataset spec record."""
        row = self._sqlite_client.fetchone(
            """
            SELECT dataset_id, spine_id, derived_ids, join_policy,
                   known_at_policy, late_arrival_policy, description, created_at,
                   version
            FROM research_dataset_spec
            WHERE dataset_id = ?
            """,
            (dataset_id,),
        )
        if row is None:
            return None
        return ResearchDatasetSpecRecord(
            dataset_id=row["dataset_id"],
            spine_id=row["spine_id"],
            derived_ids=tuple(orjson.loads(row["derived_ids"])),
            join_policy=row["join_policy"],
            known_at_policy=row["known_at_policy"],
            late_arrival_policy=row["late_arrival_policy"],
            description=row["description"],
            created_at=row["created_at"],
            version=row["version"],
        )

    def read_spine_snapshot(
        self,
        spine_snapshot_id: str,
    ) -> ResearchSpineSnapshotRecord | None:
        """Read one research spine snapshot record."""
        row = self._sqlite_client.fetchone(
            """
            SELECT spine_snapshot_id, spine_id, snapshot_start, snapshot_end,
                   row_count, data_path, manifest_hash, created_at, version
            FROM research_spine_snapshot
            WHERE spine_snapshot_id = ?
            """,
            (spine_snapshot_id,),
        )
        if row is None:
            return None
        return ResearchSpineSnapshotRecord(
            spine_snapshot_id=row["spine_snapshot_id"],
            spine_id=row["spine_id"],
            snapshot_start=row["snapshot_start"],
            snapshot_end=row["snapshot_end"],
            row_count=row["row_count"],
            data_path=row["data_path"],
            manifest_hash=row["manifest_hash"],
            created_at=row["created_at"],
            version=row["version"],
        )

    def read_dataset_snapshot(
        self,
        snapshot_id: str,
    ) -> ResearchDatasetSnapshotRecord | None:
        """Read one research dataset snapshot record."""
        row = self._sqlite_client.fetchone(
            """
            SELECT snapshot_id, dataset_id, dataset_spec_version, spine_snapshot_id,
                   snapshot_start, snapshot_end, row_count, data_path,
                   manifest_hash, known_at_policy, effective_cutoff,
                   spine_spec_version, resolved_versions, resolved_inputs,
                   source_snapshot_ids, builder_version, created_at
            FROM research_dataset_snapshot
            WHERE snapshot_id = ?
            """,
            (snapshot_id,),
        )
        if row is None:
            return None
        return ResearchDatasetSnapshotRecord(
            snapshot_id=row["snapshot_id"],
            dataset_id=row["dataset_id"],
            dataset_spec_version=row["dataset_spec_version"],
            spine_snapshot_id=row["spine_snapshot_id"],
            snapshot_start=row["snapshot_start"],
            snapshot_end=row["snapshot_end"],
            row_count=row["row_count"],
            data_path=row["data_path"],
            manifest_hash=row["manifest_hash"],
            known_at_policy=row["known_at_policy"],
            effective_cutoff=row["effective_cutoff"],
            spine_spec_version=row["spine_spec_version"],
            resolved_versions={
                str(key): int(value)
                for key, value in orjson.loads(row["resolved_versions"]).items()
            },
            resolved_inputs=tuple(orjson.loads(row["resolved_inputs"])),
            source_snapshot_ids=tuple(orjson.loads(row["source_snapshot_ids"])),
            builder_version=row["builder_version"],
            created_at=row["created_at"],
        )

    def get_latest_spine_snapshot(
        self,
        spine_id: str,
    ) -> ResearchSpineSnapshotRecord | None:
        """Read the latest spine snapshot for one spine id."""
        row = self._sqlite_client.fetchone(
            """
            SELECT spine_snapshot_id, spine_id, snapshot_start, snapshot_end,
                   row_count, data_path, manifest_hash, created_at, version
            FROM research_spine_snapshot
            WHERE spine_id = ?
            ORDER BY created_at DESC, spine_snapshot_id DESC
            LIMIT 1
            """,
            (spine_id,),
        )
        if row is None:
            return None
        return ResearchSpineSnapshotRecord(
            spine_snapshot_id=row["spine_snapshot_id"],
            spine_id=row["spine_id"],
            snapshot_start=row["snapshot_start"],
            snapshot_end=row["snapshot_end"],
            row_count=row["row_count"],
            data_path=row["data_path"],
            manifest_hash=row["manifest_hash"],
            created_at=row["created_at"],
            version=row["version"],
        )

    def get_latest_dataset_snapshot(
        self,
        dataset_id: str,
    ) -> ResearchDatasetSnapshotRecord | None:
        """Read the latest dataset snapshot for one dataset id."""
        row = self._sqlite_client.fetchone(
            """
            SELECT snapshot_id, dataset_id, dataset_spec_version, spine_snapshot_id,
                   snapshot_start, snapshot_end, row_count, data_path,
                   manifest_hash, known_at_policy, effective_cutoff,
                   spine_spec_version, resolved_versions, resolved_inputs,
                   source_snapshot_ids, builder_version, created_at
            FROM research_dataset_snapshot
            WHERE dataset_id = ?
            ORDER BY created_at DESC, snapshot_id DESC
            LIMIT 1
            """,
            (dataset_id,),
        )
        if row is None:
            return None
        return ResearchDatasetSnapshotRecord(
            snapshot_id=row["snapshot_id"],
            dataset_id=row["dataset_id"],
            dataset_spec_version=row["dataset_spec_version"],
            spine_snapshot_id=row["spine_snapshot_id"],
            snapshot_start=row["snapshot_start"],
            snapshot_end=row["snapshot_end"],
            row_count=row["row_count"],
            data_path=row["data_path"],
            manifest_hash=row["manifest_hash"],
            known_at_policy=row["known_at_policy"],
            effective_cutoff=row["effective_cutoff"],
            spine_spec_version=row["spine_spec_version"],
            resolved_versions={
                str(key): int(value)
                for key, value in orjson.loads(row["resolved_versions"]).items()
            },
            resolved_inputs=tuple(orjson.loads(row["resolved_inputs"])),
            source_snapshot_ids=tuple(orjson.loads(row["source_snapshot_ids"])),
            builder_version=row["builder_version"],
            created_at=row["created_at"],
        )
