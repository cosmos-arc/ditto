"""Certify and promote all 19 R2 products from one isolated live data root."""

from __future__ import annotations

import argparse
import hashlib
import os
import sqlite3
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import cast

import orjson
import polars as pl
from ditto_application.commands.catalog import (
    DatasetPromotionReviewCommand,
    ReviewDatasetPromotionEvidenceHandler,
)
from ditto_application.commands.data_product_certification import (
    DataProductCertificationCommands,
)
from ditto_application.commands.data_product_certification_builder import (
    AddressedCertificationEvidence,
    CertificationBuildRequest,
    DataProductCertificationBuilder,
)
from ditto_application.processes.ingestion.r2_preflight import (
    R2_ACCEPTANCE_CERTIFICATION_PROFILE,
)
from ditto_data.catalog import DataCatalogEntry, DataCatalogReader
from ditto_data.catalog.certification import (
    CertificationGovernanceStore,
    DatasetCertificationReport,
)
from ditto_data.catalog.metadata import DatasetSchedule, default_dataset_metadata
from ditto_data.catalog.source_snapshot import (
    ProviderSnapshot,
    ProviderSnapshotReader,
)

from ditto_apps.registry.container import make_app_container
from ditto_apps.registry.contexts.query import create_query_context

__all__ = [
    "R2LiveCertificationBundle",
    "R2LiveProductCertification",
    "ReusableCertificationRequest",
    "build_expected_dates",
    "certify_live_products",
    "load_passing_recovery_evidence",
    "probe_consumer_payload",
    "resolve_reusable_certification",
    "select_current_snapshot_ids",
]

type ConsumerProbe = dict[str, int | str]


@dataclass(frozen=True, slots=True)
class _SQLiteConsumerContract:
    table: str
    object_label: str
    where_clause: str = ""
    parameters: tuple[str, ...] = ()


_DEFAULT_TARGET_FROM = date(2015, 1, 1)
_EXPECTED_PRODUCT_COUNT = 19
_SHA256_HEX_LENGTH = 64
_SQLITE_CONSUMERS = {
    "calendar": _SQLiteConsumerContract("trading_calendar", "trading_calendar"),
    "stock_basic": _SQLiteConsumerContract(
        "instrument",
        "instrument[asset_class=stock]",
        " WHERE asset_class = ?",
        ("stock",),
    ),
    "etf_basic": _SQLiteConsumerContract(
        "instrument",
        "instrument[asset_class=etf]",
        " WHERE asset_class = ?",
        ("etf",),
    ),
    "index_basic": _SQLiteConsumerContract(
        "instrument",
        "instrument[asset_class=index]",
        " WHERE asset_class = ?",
        ("index",),
    ),
    "index_weight": _SQLiteConsumerContract("index_weight", "index_weight"),
    "corporate_actions": _SQLiteConsumerContract(
        "corporate_actions", "corporate_actions"
    ),
    "balance_sheet": _SQLiteConsumerContract("balance_sheet", "balance_sheet"),
    "income_statement": _SQLiteConsumerContract("income_statement", "income_statement"),
    "cash_flow": _SQLiteConsumerContract("cash_flow", "cash_flow"),
    "dividend": _SQLiteConsumerContract("dividend", "dividend"),
    "valuation_metrics": _SQLiteConsumerContract(
        "valuation_metrics", "valuation_metrics"
    ),
    "macro_indicators": _SQLiteConsumerContract(
        "macro_indicator_data", "macro_indicator_data"
    ),
}
_PARQUET_CONSUMERS = {
    "stock_daily": "market/stock/bars",
    "etf_daily": "market/etf/bars",
    "index_daily": "market/index/bars",
    "stock_status": "market/stock/status",
    "adj_factor": "market/stock/adj",
    "fund_adj": "market/etf/adj",
    "commodity_daily": "market/commodity/bars",
}


@dataclass(frozen=True, slots=True)
class R2LiveProductCertification:
    """Immutable identities and reviewed state for one live R2 product."""

    dataset_id: str
    report_id: str
    content_hash: str
    certified_from: str
    certified_through: str
    snapshot_ids: tuple[str, ...]
    consumer_evidence_path: str
    consumer_evidence_sha256: str
    promotion_criteria: tuple[str, ...]
    maturity_after: str


@dataclass(frozen=True, slots=True)
class R2LiveCertificationBundle:
    """Content-addressed result for all hard-scope R2 data products."""

    schema: str
    profile: str
    data_root: str
    target_to: str
    actor: str
    generated_at: str
    recovery_evidence_path: str
    recovery_evidence_sha256: str
    products: tuple[R2LiveProductCertification, ...]


@dataclass(frozen=True, slots=True)
class ReusableCertificationRequest:
    """Current live inputs that an approved certification must still bind."""

    dataset_id: str
    profile: str
    target_from: date
    target_to: date
    snapshot_ids: tuple[str, ...]
    recovery_evidence_uri: str
    data_root: Path
    evidence_root: Path


@dataclass(frozen=True, slots=True)
class _LiveCertificationRequest:
    dataset_id: str
    profile: str
    target_from: date
    target_to: date
    expected_dates: tuple[date, ...]
    snapshot_ids: tuple[str, ...]
    recovery_evidence_uri: str
    recovery_path: Path
    recovery_hash: str
    data_root: Path
    evidence_root: Path
    generated_at: datetime
    actor: str


def select_current_snapshot_ids(
    *,
    dataset_id: str,
    catalog_entries: tuple[DataCatalogEntry, ...],
    snapshots: tuple[ProviderSnapshot, ...],
) -> tuple[str, ...]:
    """Bind every current catalog asset to exactly one immutable provider snapshot."""
    metadata = default_dataset_metadata().get(dataset_id)
    if metadata is None or metadata.schema_version is None:
        raise ValueError(f"current dataset schema is undefined: {dataset_id}")
    entries = tuple(
        entry
        for entry in catalog_entries
        if entry.asset.dataset_id == dataset_id
        and entry.schema.schema_version == metadata.schema_version
    )
    if not entries:
        raise ValueError(f"current catalog evidence is empty: {dataset_id}")
    selected: list[str] = []
    for entry in entries:
        created_at = entry.schema.created_at
        if created_at is None or entry.schema.schema_version is None:
            raise ValueError(
                f"current catalog schema evidence is incomplete: {dataset_id}"
            )
        matches = tuple(
            snapshot
            for snapshot in snapshots
            if snapshot.dataset_id == dataset_id
            and snapshot.canonical_asset == entry.asset
            and snapshot.source == entry.source
            and snapshot.schema_version == entry.schema.schema_version
            and snapshot.row_count == entry.schema.row_count
            and snapshot.created_at == created_at
            and snapshot.payload_retained
            and snapshot.payload_uri is not None
        )
        if len(matches) != 1:
            raise ValueError(
                "catalog asset must bind exactly one current provider snapshot: "
                + f"{dataset_id}/{entry.asset.partition_keys}"
            )
        selected.append(matches[0].snapshot_id)
    return tuple(sorted(selected))


def build_expected_dates(
    *,
    schedule: DatasetSchedule,
    target_from: date,
    target_to: date,
    trading_days_provider: Callable[[str, str], list[str]],
) -> tuple[date, ...]:
    """Build the explicit schedule used by the immutable coverage report."""
    if target_to < target_from:
        raise ValueError("R2 certification target interval is reversed")
    if schedule == "trading_days":
        values = tuple(
            date.fromisoformat(value)
            for value in trading_days_provider(
                target_from.isoformat(), target_to.isoformat()
            )
        )
    else:
        days = (target_to - target_from).days
        values = tuple(
            target_from + timedelta(days=offset) for offset in range(days + 1)
        )
    expected = tuple(
        sorted({value for value in values if target_from <= value <= target_to})
    )
    if not expected:
        raise ValueError("R2 certification expected schedule is empty")
    return expected


def probe_consumer_payload(data_root: Path, dataset_id: str) -> ConsumerProbe:
    """Read one canonical storage object through its production physical contract."""
    root = data_root.expanduser().resolve(strict=False)
    sqlite_contract = _SQLITE_CONSUMERS.get(dataset_id)
    if sqlite_contract is not None:
        sqlite_path = root / "metadata" / "metadata.sqlite"
        if not sqlite_path.is_file():
            raise ValueError(f"consumer SQLite database is missing: {sqlite_path}")
        with sqlite3.connect(sqlite_path) as connection:
            row_count = int(
                connection.execute(
                    f'SELECT COUNT(*) FROM "{sqlite_contract.table}"'  # noqa: S608
                    + sqlite_contract.where_clause,
                    sqlite_contract.parameters,
                ).fetchone()[0]
            )
        probe: ConsumerProbe = {
            "kind": "sqlite",
            "object": sqlite_contract.object_label,
            "row_count": row_count,
        }
    else:
        relative = _PARQUET_CONSUMERS.get(dataset_id)
        if relative is None:
            raise ValueError(f"no production consumer probe is declared: {dataset_id}")
        payload_root = root / relative
        files = tuple(sorted(payload_root.glob("*.parquet")))
        if not files:
            raise ValueError(f"consumer Parquet payload is missing: {dataset_id}")
        row_count = int(
            pl.scan_parquet(list(files)).select(pl.len().alias("rows")).collect().item()
        )
        probe = {
            "file_count": len(files),
            "kind": "parquet",
            "object": relative,
            "row_count": row_count,
        }
    if cast(int, probe["row_count"]) <= 0:
        raise ValueError(f"consumer payload is empty: {dataset_id}")
    return probe


def _canonical(value: object) -> bytes:
    return orjson.dumps(value, option=orjson.OPT_SORT_KEYS)


def _write_addressed(root: Path, stem: str, payload: object) -> tuple[Path, str]:
    content = _canonical(payload)
    digest = hashlib.sha256(content).hexdigest()
    path = root / f"{stem}.sha256-{digest}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() != content:
        raise ValueError(f"content-addressed evidence conflict: {path}")
    path.write_bytes(content)
    return path, digest


def _literal_target_from(dataset_id: str) -> date:
    contract = default_dataset_metadata()[dataset_id].product_contract
    if contract is None or contract.r2_scope != "hard":
        raise ValueError(f"dataset is outside hard R2 scope: {dataset_id}")
    raw = contract.raw_target_from
    if raw is None:
        raise ValueError(f"dataset has no R2 raw target: {dataset_id}")
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return _DEFAULT_TARGET_FROM


def load_passing_recovery_evidence(path: Path) -> tuple[Path, str]:
    """Validate the exact addressed recoverability group emitted by R2 acceptance."""
    resolved = path.expanduser().resolve(strict=True)
    decoded = orjson.loads(resolved.read_bytes())
    if type(decoded) is not dict:
        raise ValueError("recovery evidence must be an addressed R2 gate group")
    payload = cast("dict[str, object]", decoded)
    if (
        payload.get("schema") != "ditto.r2-live-gate-artifact"
        or payload.get("version") != 1
        or payload.get("kind") != "recoverability"
    ):
        raise ValueError("recovery evidence must be an addressed R2 gate group")
    recoverability = payload.get("recoverability")
    if type(recoverability) is not dict:
        raise ValueError("recovery evidence must contain passing recoverability")
    recovery = cast("dict[str, object]", recoverability)
    row_counts = recovery.get("sqlite_table_row_counts")
    if (
        recovery.get("passed") is not True
        or recovery.get("reason_codes") not in ([], ())
        or not isinstance(row_counts, dict)
        or not row_counts
        or not isinstance(recovery.get("payload_root_sha256"), str)
    ):
        raise ValueError("recovery evidence must contain passing recoverability")
    return resolved, hashlib.sha256(resolved.read_bytes()).hexdigest()


def resolve_reusable_certification(
    *,
    active_report: DatasetCertificationReport,
    request: ReusableCertificationRequest,
) -> tuple[Path, str]:
    """Fail closed unless an approved report exactly matches resumable live inputs."""
    product = f"{request.dataset_id}/{request.profile}"
    if (
        active_report.dataset_id != request.dataset_id
        or active_report.profile != request.profile
    ):
        raise ValueError(f"active certification product drift: {product}")
    coverage = active_report.coverage
    if (
        coverage.target_from != request.target_from
        or coverage.target_to != request.target_to
        or not coverage.is_complete
    ):
        raise ValueError(f"active certification coverage drift: {product}")
    if tuple(active_report.evidence.snapshot_ids) != tuple(request.snapshot_ids):
        raise ValueError(f"active certification snapshot binding drift: {product}")

    recovery_checks = tuple(
        check
        for check in active_report.evidence.recovery_results
        if check.name == "isolated_backup_restore_hash_parity"
        and check.evidence_uri == request.recovery_evidence_uri
        and check.passed
    )
    if len(recovery_checks) != 1:
        raise ValueError(f"active certification recovery evidence drift: {product}")

    consumer_checks = tuple(
        check
        for check in active_report.evidence.consumer_results
        if check.name == "production_consumer_read_smoke" and check.passed
    )
    if len(consumer_checks) != 1:
        raise ValueError(f"active certification consumer evidence drift: {product}")
    prefix = f"artifact+sha256://r2-live/consumer/{request.dataset_id}/"
    uri = consumer_checks[0].evidence_uri
    digest = uri.removeprefix(prefix) if uri.startswith(prefix) else ""
    if len(digest) != _SHA256_HEX_LENGTH or any(
        char not in "0123456789abcdef" for char in digest
    ):
        raise ValueError(f"active certification consumer URI drift: {product}")

    path = (
        request.evidence_root.expanduser().resolve(strict=False)
        / "products"
        / request.dataset_id
        / f"consumer-read-smoke.sha256-{digest}.json"
    ).resolve(strict=True)
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != digest:
        raise ValueError(f"active certification consumer hash drift: {product}")
    decoded = orjson.loads(content)
    if type(decoded) is not dict:
        raise ValueError(f"active certification consumer payload drift: {product}")
    payload = cast("dict[str, object]", decoded)
    probe = payload.get("probe")
    expected_root = str(request.data_root.expanduser().resolve(strict=False))
    if (
        payload.get("schema") != "ditto.r2-live-consumer-evidence.v1"
        or payload.get("dataset_id") != request.dataset_id
        or payload.get("data_root") != expected_root
        or payload.get("snapshot_ids") != list(request.snapshot_ids)
        or type(probe) is not dict
        or type(cast("dict[str, object]", probe).get("row_count")) is not int
        or cast("int", cast("dict[str, object]", probe)["row_count"]) <= 0
    ):
        raise ValueError(f"active certification consumer payload drift: {product}")
    return path, digest


def _freeze_or_resume_product(
    request: _LiveCertificationRequest,
    certification_store: CertificationGovernanceStore,
    certification_commands: DataProductCertificationCommands,
    builder: DataProductCertificationBuilder,
) -> tuple[DatasetCertificationReport, Path, str]:
    active = certification_store.get_active_report(request.dataset_id, request.profile)
    if active is not None:
        events = certification_store.list_events(active.report_id)
        if not events or events[-1].action != "approved":
            raise ValueError(f"active certification review drift: {request.dataset_id}")
        if events[-1].actor != request.actor:
            raise ValueError(
                f"active certification reviewer drift: {request.dataset_id}"
            )
        consumer_path, consumer_hash = resolve_reusable_certification(
            active_report=active,
            request=ReusableCertificationRequest(
                dataset_id=request.dataset_id,
                profile=request.profile,
                target_from=request.target_from,
                target_to=request.target_to,
                snapshot_ids=request.snapshot_ids,
                recovery_evidence_uri=request.recovery_evidence_uri,
                data_root=request.data_root,
                evidence_root=request.evidence_root,
            ),
        )
        return active, consumer_path, consumer_hash

    probe = probe_consumer_payload(request.data_root, request.dataset_id)
    consumer_path, consumer_hash = _write_addressed(
        request.evidence_root / "products" / request.dataset_id,
        "consumer-read-smoke",
        {
            "schema": "ditto.r2-live-consumer-evidence.v1",
            "dataset_id": request.dataset_id,
            "data_root": str(request.data_root),
            "generated_at": request.generated_at.isoformat(),
            "probe": probe,
            "snapshot_ids": list(request.snapshot_ids),
        },
    )
    report = builder.build(
        CertificationBuildRequest(
            dataset_id=request.dataset_id,
            profile=request.profile,
            target_to=request.target_to,
            expected_dates=request.expected_dates,
            snapshot_ids=request.snapshot_ids,
            generated_at=request.generated_at,
            recovery_evidence=AddressedCertificationEvidence(
                name="isolated_backup_restore_hash_parity",
                evidence_uri=request.recovery_evidence_uri,
                local_path=request.recovery_path,
                sha256_hex=request.recovery_hash,
            ),
            consumer_evidence=AddressedCertificationEvidence(
                name="production_consumer_read_smoke",
                evidence_uri=(
                    "artifact+sha256://r2-live/consumer/"
                    f"{request.dataset_id}/{consumer_hash}"
                ),
                local_path=consumer_path,
                sha256_hex=consumer_hash,
            ),
        )
    )
    frozen = certification_commands.freeze(report)
    certification_commands.review(
        frozen.report_id,
        reviewer=request.actor,
        reviewed_at=request.generated_at,
    )
    return frozen, consumer_path, consumer_hash


def certify_live_products(
    *,
    data_root: Path,
    evidence_root: Path,
    recovery_evidence_path: Path,
    recovery_evidence_uri: str,
    target_to: date,
    actor: str,
    generated_at: datetime | None = None,
) -> R2LiveCertificationBundle:
    """Build, freeze, review, and promote every hard-scope R2 product."""
    root = data_root.expanduser().resolve(strict=True)
    configured_root = (
        Path(os.environ.get("DITTO_DATA_ROOT", "")).expanduser().resolve(strict=False)
    )
    if configured_root != root:
        raise ValueError("DITTO_DATA_ROOT must equal the isolated live data root")
    if not actor or actor.strip() != actor:
        raise ValueError("certification actor is invalid")
    if not recovery_evidence_uri.strip():
        raise ValueError("recovery evidence URI is required")
    now = generated_at or datetime.now(UTC)
    if now.tzinfo is None:
        raise ValueError("certification generated_at must be timezone-aware")
    recovery_path, recovery_hash = load_passing_recovery_evidence(
        recovery_evidence_path
    )
    evidence_dir = evidence_root.expanduser().resolve(strict=False)

    registry = default_dataset_metadata()
    dataset_ids = tuple(
        sorted(
            metadata.dataset_id
            for metadata in registry.values()
            if metadata.product_contract is not None
            and metadata.product_contract.r2_scope == "hard"
        )
    )
    if len(dataset_ids) != _EXPECTED_PRODUCT_COUNT:
        raise ValueError(
            f"R2 hard-scope registry must contain 19 products: {len(dataset_ids)}"
        )

    with create_query_context() as query_context:
        container = make_app_container()
        try:
            catalog_reader = container.get(DataCatalogReader)
            snapshot_reader = container.get(ProviderSnapshotReader)
            builder = container.get(DataProductCertificationBuilder)
            certification_commands = container.get(DataProductCertificationCommands)
            certification_store = container.get(CertificationGovernanceStore)
            promotion_handler = container.get(ReviewDatasetPromotionEvidenceHandler)
            products: list[R2LiveProductCertification] = []
            catalog_entries = catalog_reader.list_assets()
            for dataset_id in dataset_ids:
                metadata = registry[dataset_id]
                snapshots = snapshot_reader.list_snapshots(dataset_id=dataset_id)
                snapshot_ids = select_current_snapshot_ids(
                    dataset_id=dataset_id,
                    catalog_entries=catalog_entries,
                    snapshots=snapshots,
                )
                target_from = _literal_target_from(dataset_id)
                expected_dates = build_expected_dates(
                    schedule=metadata.schedule,
                    target_from=target_from,
                    target_to=target_to,
                    trading_days_provider=query_context.metadata.list_trading_days,
                )
                frozen, consumer_path, consumer_hash = _freeze_or_resume_product(
                    _LiveCertificationRequest(
                        dataset_id=dataset_id,
                        profile=R2_ACCEPTANCE_CERTIFICATION_PROFILE,
                        target_from=target_from,
                        target_to=target_to,
                        expected_dates=expected_dates,
                        snapshot_ids=snapshot_ids,
                        recovery_evidence_uri=recovery_evidence_uri,
                        recovery_path=recovery_path,
                        recovery_hash=recovery_hash,
                        data_root=root,
                        evidence_root=evidence_dir,
                        generated_at=now,
                        actor=actor,
                    ),
                    certification_store,
                    certification_commands,
                    builder,
                )
                promotion_uri = (
                    "artifact+sha256://r2-live/certification/"
                    f"{frozen.report_id}/{frozen.content_hash}"
                )
                maturity_after = metadata.maturity
                for criterion in metadata.promotion_criteria:
                    result = promotion_handler.handle(
                        DatasetPromotionReviewCommand(
                            dataset_id=dataset_id,
                            criterion=criterion,
                            evidence_uri=promotion_uri,
                            reviewed_by=actor,
                            notes=(
                                "Approved from immutable R2 live certification "
                                "evidence."
                            ),
                        )
                    )
                    maturity_after = result.dataset_maturity_after
                products.append(
                    R2LiveProductCertification(
                        dataset_id=dataset_id,
                        report_id=frozen.report_id,
                        content_hash=frozen.content_hash,
                        certified_from=frozen.coverage.complete_from.isoformat()
                        if frozen.coverage.complete_from is not None
                        else "",
                        certified_through=frozen.coverage.target_to.isoformat(),
                        snapshot_ids=frozen.evidence.snapshot_ids,
                        consumer_evidence_path=str(consumer_path),
                        consumer_evidence_sha256=consumer_hash,
                        promotion_criteria=metadata.promotion_criteria,
                        maturity_after=maturity_after,
                    )
                )
        finally:
            container.close()

    return R2LiveCertificationBundle(
        schema="ditto.r2-live-certification-bundle.v1",
        profile=R2_ACCEPTANCE_CERTIFICATION_PROFILE,
        data_root=str(root),
        target_to=target_to.isoformat(),
        actor=actor,
        generated_at=now.isoformat(),
        recovery_evidence_path=str(recovery_path),
        recovery_evidence_sha256=recovery_hash,
        products=tuple(products),
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--recovery-evidence", type=Path, required=True)
    parser.add_argument("--recovery-evidence-uri", required=True)
    parser.add_argument("--target-to", type=date.fromisoformat, required=True)
    parser.add_argument("--actor", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run live certification without serializing provider credentials."""
    args = _parser().parse_args(argv)
    bundle = certify_live_products(
        data_root=args.data_root,
        evidence_root=args.evidence_root,
        recovery_evidence_path=args.recovery_evidence,
        recovery_evidence_uri=args.recovery_evidence_uri,
        target_to=args.target_to,
        actor=args.actor,
    )
    output = args.output.expanduser().resolve(strict=False)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(_canonical(asdict(bundle)))
    rendered = orjson.dumps(
        asdict(bundle), option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS
    ).decode()
    sys.stdout.write(rendered + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
