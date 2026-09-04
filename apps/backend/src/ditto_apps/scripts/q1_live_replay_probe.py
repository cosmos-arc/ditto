"""Prove Q1 live-ingestion replay without serializing provider payloads."""

from __future__ import annotations

import argparse
import hashlib
import sqlite3
import sys
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import orjson

from ditto_apps.config.runtime import state_root_matches
from ditto_apps.registry.contexts.ingestion import create_ingestion_bundle

__all__ = [
    "ReplayPartition",
    "ReplayRunObservation",
    "collect_live_replay_evidence",
    "observe_runtime_state",
]

type RuntimeState = dict[str, object]

_Q1_DATASETS = (
    "calendar",
    "stock_basic",
    "etf_basic",
    "index_basic",
    "stock_daily",
    "etf_daily",
    "index_daily",
    "global_index_daily",
    "industry_classification",
    "industry_mapping",
    "stock_status",
    "adj_factor",
    "fund_adj",
    "macro_indicators",
)
_DURABLE_PAYLOAD_ROOTS = ("market", "provider_payloads")
_INGESTION_LOG_QUERY = """
SELECT dataset, source, trade_date, status, checksum, rows,
       error_code, attempts
FROM ingestion_log
ORDER BY dataset, source, trade_date
"""


@dataclass(frozen=True, slots=True)
class ReplayPartition:
    """One exact previously-ingested dataset partition to replay."""

    dataset: str
    trade_date: str


@dataclass(frozen=True, slots=True)
class ReplayRunObservation:
    """Redacted result of replaying one already-successful partition."""

    dataset: str
    trade_date: str
    status: str
    row_count: int | None


def _canonical(value: object) -> bytes:
    return orjson.dumps(value, option=orjson.OPT_SORT_KEYS)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _state_sha256(state: RuntimeState) -> str:
    return hashlib.sha256(_canonical(state)).hexdigest()


def _is_durable_payload(name: str) -> bool:
    """Exclude SQLite connection sidecars that disappear when the process exits."""
    return not name.endswith(("-wal", "-shm"))


def _iter_durable_payload_paths(data_root: Path) -> tuple[Path, ...]:
    """Return canonical and retained-provider files, excluding DB sidecars."""
    return tuple(
        path
        for subtree in _DURABLE_PAYLOAD_ROOTS
        for path in sorted((data_root / subtree).rglob("*"))
        if path.is_file() and _is_durable_payload(path.name)
    )


def _observe_sqlite_tables(connection: sqlite3.Connection) -> dict[str, object]:
    """Hash every logical SQLite table without serializing provider-facing rows."""
    table_names = tuple(
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
        ).fetchall()
    )
    observations: dict[str, object] = {}
    for table in table_names:
        # The identifier comes exclusively from this connection's sqlite_master.
        statement = f'SELECT * FROM "{table}"'  # noqa: S608
        rows = [
            _canonical(dict(row)) for row in connection.execute(statement).fetchall()
        ]
        rows.sort()
        digest = hashlib.sha256()
        for row in rows:
            digest.update(len(row).to_bytes(8, byteorder="big"))
            digest.update(row)
        observations[table] = {
            "row_count": len(rows),
            "content_sha256": digest.hexdigest(),
        }
    return observations


def observe_runtime_state(
    data_root: Path,
    datasets: Sequence[str] = _Q1_DATASETS,
) -> RuntimeState:
    """Read logical identities, row counts, and payload hashes from one data root."""
    root = data_root.expanduser().resolve(strict=True)
    database = root / "metadata" / "metadata.sqlite"
    if not database.is_file():
        raise ValueError("Q1 metadata database is missing")
    selected_datasets = frozenset(datasets)
    with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        records = [
            dict(row)
            for row in connection.execute(_INGESTION_LOG_QUERY).fetchall()
            if str(row["dataset"]) in selected_datasets
        ]
        sqlite_tables = _observe_sqlite_tables(connection)
    payloads = [
        {
            "path": str(path.relative_to(root)),
            "sha256": _sha256_file(path),
            "size_bytes": path.stat().st_size,
        }
        for path in _iter_durable_payload_paths(root)
    ]
    return {
        "ingestion_records": records,
        "payloads": payloads,
        "sqlite_tables": sqlite_tables,
    }


def collect_live_replay_evidence(
    *,
    partitions: Sequence[ReplayPartition],
    run_replay: Callable[[], Sequence[ReplayRunObservation]],
    observe: Callable[[], RuntimeState],
) -> dict[str, object]:
    """Fail closed unless every replay skips and durable state stays identical."""
    before = observe()
    before_hash = _state_sha256(before)
    replay_results = tuple(run_replay())
    expected = tuple((item.dataset, item.trade_date) for item in partitions)
    observed = tuple((item.dataset, item.trade_date) for item in replay_results)
    if observed != expected or any(item.status != "skipped" for item in replay_results):
        raise ValueError("Q1 replay was not a complete partition skip")
    after = observe()
    after_hash = _state_sha256(after)
    if before_hash != after_hash:
        raise ValueError("Q1 replay mutated durable runtime state")
    return {
        "schema": "ditto.q1-live-replay.v3",
        "partitions": [asdict(item) for item in partitions],
        "before_state_sha256": before_hash,
        "after_state_sha256": after_hash,
        "replay_results": [asdict(item) for item in replay_results],
        "runtime_state": after,
        "passed": True,
    }


def _run_replay(
    partitions: Sequence[ReplayPartition],
) -> tuple[ReplayRunObservation, ...]:
    observations: list[ReplayRunObservation] = []
    with create_ingestion_bundle(source="tushare") as bundle:
        for partition in partitions:
            result = bundle.coordinator.ingest_date(
                partition.dataset,
                partition.trade_date,
            )
            observations.append(
                ReplayRunObservation(
                    dataset=partition.dataset,
                    trade_date=partition.trade_date,
                    status=result.status,
                    row_count=result.row_count,
                )
            )
    return tuple(observations)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", required=True, type=Path)
    parser.add_argument("--trade-date", required=True)
    parser.add_argument("--corporate-actions-date", required=True)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Write one redacted, content-addressable Q1 replay artifact."""
    args = _parser().parse_args(argv)
    data_root = args.data_root.expanduser().resolve(strict=True)
    if not state_root_matches(data_root):
        raise ValueError("DITTO_STATE_ROOT must equal the isolated Q1 data root")
    partitions = (
        *(
            ReplayPartition(dataset, cast("str", args.trade_date))
            for dataset in _Q1_DATASETS
        ),
        ReplayPartition(
            "corporate_actions",
            cast("str", args.corporate_actions_date),
        ),
    )
    datasets = tuple(partition.dataset for partition in partitions)
    evidence = collect_live_replay_evidence(
        partitions=partitions,
        run_replay=lambda: _run_replay(partitions),
        observe=lambda: observe_runtime_state(data_root, datasets),
    )
    evidence["data_root"] = str(data_root)
    evidence["generated_at"] = datetime.now(UTC).isoformat()
    output = args.output.expanduser().resolve(strict=False)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        orjson.dumps(
            evidence,
            option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS,
        )
        + b"\n"
    )
    output.write_bytes(payload)
    sys.stdout.write(
        orjson.dumps(
            {
                "partition_count": len(partitions),
                "output": str(output),
                "sha256": hashlib.sha256(payload).hexdigest(),
            },
            option=orjson.OPT_SORT_KEYS,
        ).decode()
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
