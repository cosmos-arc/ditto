"""SQLite-backed data lineage implementation."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, cast

from ditto_platform.foundation import SQLiteClient

from ditto_data.catalog.contracts import DataAssetRef
from ditto_data.lineage.contracts import (
    LineageEvent,
    LineageInputRef,
    LineageOutputRef,
)

__all__ = ["SQLiteDataLineage"]


def _partition_keys_json(partition_keys: tuple[str, ...]) -> str:
    return json.dumps(list(partition_keys), ensure_ascii=True, separators=(",", ":"))


def _partition_keys_from_json(value: str) -> tuple[str, ...]:
    parsed: object = json.loads(value)
    if not isinstance(parsed, list):
        raise ValueError("lineage asset partition keys must be a JSON string list")
    values = cast(list[object], parsed)
    partition_keys: list[str] = []
    for item in values:
        if not isinstance(item, str):
            raise ValueError("lineage asset partition keys must be a JSON string list")
        partition_keys.append(item)
    return tuple(partition_keys)


def _asset_params(asset: DataAssetRef) -> tuple[str, str, str]:
    return (
        asset.namespace,
        asset.dataset_id,
        _partition_keys_json(asset.partition_keys),
    )


def _asset_from_row(row: dict[str, Any]) -> DataAssetRef:
    return DataAssetRef(
        dataset_id=str(row["asset_dataset_id"]),
        namespace=str(row["asset_namespace"]),
        partition_keys=_partition_keys_from_json(str(row["asset_partition_keys"])),
    )


class SQLiteDataLineage:
    """Append-only SQLite lineage store for durable audit/replay facts."""

    def __init__(self, client: SQLiteClient) -> None:
        self._client = client
        self._create_tables()

    def _create_tables(self) -> None:
        self._client.execute(
            """
            CREATE TABLE IF NOT EXISTS data_lineage_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                operation TEXT NOT NULL,
                timestamp TEXT NOT NULL
            )
            """,
        )
        self._client.execute(
            """
            CREATE TABLE IF NOT EXISTS data_lineage_inputs (
                event_id INTEGER NOT NULL,
                position INTEGER NOT NULL,
                asset_namespace TEXT NOT NULL,
                asset_dataset_id TEXT NOT NULL,
                asset_partition_keys TEXT NOT NULL,
                role TEXT NOT NULL,
                PRIMARY KEY (event_id, position),
                FOREIGN KEY (event_id)
                    REFERENCES data_lineage_events(id)
                    ON DELETE CASCADE
            )
            """,
        )
        self._client.execute(
            """
            CREATE TABLE IF NOT EXISTS data_lineage_outputs (
                event_id INTEGER NOT NULL,
                position INTEGER NOT NULL,
                asset_namespace TEXT NOT NULL,
                asset_dataset_id TEXT NOT NULL,
                asset_partition_keys TEXT NOT NULL,
                role TEXT NOT NULL,
                PRIMARY KEY (event_id, position),
                FOREIGN KEY (event_id)
                    REFERENCES data_lineage_events(id)
                    ON DELETE CASCADE
            )
            """,
        )
        for table in ("data_lineage_inputs", "data_lineage_outputs"):
            self._client.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_{table}_asset
                ON {table}(
                    asset_namespace,
                    asset_dataset_id,
                    asset_partition_keys
                )
                """,
            )
        self._client.commit()

    def record_event(self, event: LineageEvent) -> None:
        """Append one lineage event and its asset relationships."""
        try:
            cursor = self._client.execute(
                """
                INSERT INTO data_lineage_events (run_id, operation, timestamp)
                VALUES (?, ?, ?)
                """,
                [event.run_id, event.operation, event.timestamp.isoformat()],
            )
            event_id = cursor.lastrowid
            if event_id is None:
                raise RuntimeError("SQLite did not return a lineage event id")

            self._insert_inputs(event_id, event.inputs)
            self._insert_outputs(event_id, event.outputs)
            self._client.commit()
        except Exception:
            self._client.rollback()
            raise

    def _insert_inputs(
        self,
        event_id: int,
        inputs: tuple[LineageInputRef, ...],
    ) -> None:
        self._client.executemany(
            """
            INSERT INTO data_lineage_inputs (
                event_id,
                position,
                asset_namespace,
                asset_dataset_id,
                asset_partition_keys,
                role
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    event_id,
                    position,
                    ref.asset.namespace,
                    ref.asset.dataset_id,
                    _partition_keys_json(ref.asset.partition_keys),
                    ref.role,
                )
                for position, ref in enumerate(inputs)
            ],
        )

    def _insert_outputs(
        self,
        event_id: int,
        outputs: tuple[LineageOutputRef, ...],
    ) -> None:
        self._client.executemany(
            """
            INSERT INTO data_lineage_outputs (
                event_id,
                position,
                asset_namespace,
                asset_dataset_id,
                asset_partition_keys,
                role
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    event_id,
                    position,
                    ref.asset.namespace,
                    ref.asset.dataset_id,
                    _partition_keys_json(ref.asset.partition_keys),
                    ref.role,
                )
                for position, ref in enumerate(outputs)
            ],
        )

    def list_events_for_asset(self, asset: DataAssetRef) -> tuple[LineageEvent, ...]:
        """Return lineage events that mention ``asset`` in append order."""
        namespace, dataset_id, partition_keys = _asset_params(asset)
        rows = self._client.fetchall(
            """
            SELECT e.id, e.run_id, e.operation, e.timestamp
            FROM data_lineage_events AS e
            WHERE EXISTS (
                SELECT 1
                FROM data_lineage_inputs AS i
                WHERE i.event_id = e.id
                  AND i.asset_namespace = ?
                  AND i.asset_dataset_id = ?
                  AND i.asset_partition_keys = ?
            )
            OR EXISTS (
                SELECT 1
                FROM data_lineage_outputs AS o
                WHERE o.event_id = e.id
                  AND o.asset_namespace = ?
                  AND o.asset_dataset_id = ?
                  AND o.asset_partition_keys = ?
            )
            ORDER BY e.id ASC
            """,
            [
                namespace,
                dataset_id,
                partition_keys,
                namespace,
                dataset_id,
                partition_keys,
            ],
        )
        return tuple(self._event_from_row(row) for row in rows)

    def list_events_for_run(self, run_id: str) -> tuple[LineageEvent, ...]:
        """Return lineage events recorded for ``run_id`` in append order."""
        rows = self._client.fetchall(
            """
            SELECT id, run_id, operation, timestamp
            FROM data_lineage_events
            WHERE run_id = ?
            ORDER BY id ASC
            """,
            [run_id],
        )
        return tuple(self._event_from_row(row) for row in rows)

    def _event_from_row(self, row: dict[str, Any]) -> LineageEvent:
        event_id = int(row["id"])
        return LineageEvent(
            run_id=str(row["run_id"]),
            operation=str(row["operation"]),
            inputs=self._inputs_for_event(event_id),
            outputs=self._outputs_for_event(event_id),
            timestamp=datetime.fromisoformat(str(row["timestamp"])),
        )

    def _inputs_for_event(self, event_id: int) -> tuple[LineageInputRef, ...]:
        rows = self._client.fetchall(
            """
            SELECT asset_namespace, asset_dataset_id, asset_partition_keys, role
            FROM data_lineage_inputs
            WHERE event_id = ?
            ORDER BY position ASC
            """,
            [event_id],
        )
        return tuple(
            LineageInputRef(asset=_asset_from_row(row), role=str(row["role"]))
            for row in rows
        )

    def _outputs_for_event(self, event_id: int) -> tuple[LineageOutputRef, ...]:
        rows = self._client.fetchall(
            """
            SELECT asset_namespace, asset_dataset_id, asset_partition_keys, role
            FROM data_lineage_outputs
            WHERE event_id = ?
            ORDER BY position ASC
            """,
            [event_id],
        )
        return tuple(
            LineageOutputRef(asset=_asset_from_row(row), role=str(row["role"]))
            for row in rows
        )
