"""Measure live incremental idempotency and the R2 workbench read path."""

from __future__ import annotations

import argparse
import hashlib
import os
import sqlite3
import sys
from collections.abc import Callable, Sequence
from dataclasses import asdict
from pathlib import Path
from time import perf_counter
from typing import cast

import orjson
from ditto_application.processes.experiments.planning_probes import (
    R3_RESEARCH_CERTIFICATION_PROFILE,
)
from ditto_application.queries.data_products import (
    DataProductOverview,
    DataProductsQueryFacade,
)

from ditto_apps.registry.container import make_app_container
from ditto_apps.registry.contexts.ingestion import create_ingestion_bundle
from ditto_apps.scripts.r2_data_acceptance import (
    R2IdempotencySnapshot,
    verify_idempotency_snapshots,
)

__all__ = [
    "collect_live_runtime_evidence",
    "observe_runtime_identity",
]

type Clock = Callable[[], float]
type RuntimeEvidence = dict[str, object]

_EXPECTED_PRODUCT_COUNT = 19


def _snapshot_payload(value: R2IdempotencySnapshot) -> dict[str, object]:
    payload = asdict(value)
    payload["snapshot_ids"] = list(value.snapshot_ids)
    return payload


def collect_live_runtime_evidence(
    *,
    provider_evidence: RuntimeEvidence,
    run_incremental: Callable[[], None],
    observe: Callable[[], R2IdempotencySnapshot],
    query_workbench: Callable[[], Sequence[object]],
    clock: Clock = perf_counter,
) -> RuntimeEvidence:
    """Run one bounded operation twice and bind conservative measured timings."""
    required = {"provider_access", "benchmarks"}
    if not required.issubset(provider_evidence):
        raise ValueError("provider probe evidence is incomplete")

    started = clock()
    run_incremental()
    first_elapsed = max(clock() - started, 0.0)
    first = observe()

    started = clock()
    run_incremental()
    second_elapsed = max(clock() - started, 0.0)
    second = observe()
    idempotency = verify_idempotency_snapshots(first, second)
    if not idempotency.passed:
        raise ValueError(
            "consecutive idempotency failed: " + ",".join(idempotency.reason_codes)
        )

    started = clock()
    products = query_workbench()
    query_elapsed = max(clock() - started, 0.0)
    if len(products) != _EXPECTED_PRODUCT_COUNT:
        raise ValueError("R2 workbench query did not return exactly 19 products")

    return {
        "provider_access": provider_evidence["provider_access"],
        "benchmarks": provider_evidence["benchmarks"],
        "incremental_elapsed_seconds": max(first_elapsed, second_elapsed),
        "workbench_query_seconds": query_elapsed,
        "first_run": _snapshot_payload(first),
        "second_run": _snapshot_payload(second),
    }


def observe_runtime_identity(database: Path) -> R2IdempotencySnapshot:
    """Read durable provider identities and transition attempts from SQLite."""
    path = database.expanduser().resolve(strict=True)
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
        snapshot_ids = tuple(
            str(row[0])
            for row in connection.execute(
                "SELECT snapshot_id FROM provider_snapshots ORDER BY snapshot_id"
            ).fetchall()
        )
        write_attempt_count = int(
            connection.execute(
                "SELECT COUNT(*) FROM ingestion_partition_events"
            ).fetchone()[0]
        )
    return R2IdempotencySnapshot(
        durable_identity_count=len(snapshot_ids),
        write_attempt_count=write_attempt_count,
        snapshot_ids=snapshot_ids,
    )


def _read_provider_evidence(path: Path) -> RuntimeEvidence:
    try:
        decoded = orjson.loads(path.expanduser().resolve(strict=True).read_bytes())
    except (OSError, orjson.JSONDecodeError) as exc:
        raise ValueError("provider probe evidence is invalid") from exc
    if type(decoded) is not dict:
        raise ValueError("provider probe evidence must be a JSON object")
    return cast("RuntimeEvidence", decoded)


def _run_incremental(
    *,
    dataset_id: str,
    start_date: str,
    end_date: str,
    source: str,
    license_record_id: str,
) -> None:
    with create_ingestion_bundle(
        source=source,
        license_record_id=license_record_id,
    ) as bundle:
        bundle.backfill_manager.backfill_range(
            dataset=dataset_id,
            start_date=start_date,
            end_date=end_date,
            parallel=1,
        )


def _query_workbench() -> tuple[DataProductOverview, ...]:
    container = make_app_container()
    try:
        facade = container.get(DataProductsQueryFacade)
        return facade.list_products(profile=R3_RESEARCH_CERTIFICATION_PROFILE)
    finally:
        container.close()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", required=True, type=Path)
    parser.add_argument("--provider-evidence", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--dataset-id", default="stock_daily")
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--source", default="tushare")
    parser.add_argument("--license-record-id", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Write the exact live evidence input consumed by R2 acceptance."""
    args = _parser().parse_args(argv)
    data_root = args.data_root.expanduser().resolve(strict=True)
    configured = (
        Path(os.environ.get("DITTO_DATA_ROOT", "")).expanduser().resolve(strict=False)
    )
    if configured != data_root:
        raise ValueError("DITTO_DATA_ROOT must equal the isolated live data root")
    database = data_root / "metadata" / "metadata.sqlite"
    evidence = collect_live_runtime_evidence(
        provider_evidence=_read_provider_evidence(args.provider_evidence),
        run_incremental=lambda: _run_incremental(
            dataset_id=args.dataset_id,
            start_date=args.start_date,
            end_date=args.end_date,
            source=args.source,
            license_record_id=args.license_record_id,
        ),
        observe=lambda: observe_runtime_identity(database),
        query_workbench=_query_workbench,
    )
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
