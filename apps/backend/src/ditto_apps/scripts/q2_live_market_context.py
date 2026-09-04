"""Certify and replay the bounded Q2 live MarketContext evidence chain."""

from __future__ import annotations

import argparse
import hashlib
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import cast

import orjson
import polars as pl
from ditto_agent._canonical import canonical_bytes, canonical_sha256
from ditto_agent.contracts.temporal import (
    EgressClass,
    TemporalContextInput,
    TemporalToolContext,
)
from ditto_agent.tools.market_context import MarketContextEvidenceTool
from ditto_application.catalog_freshness import aggregate_source_snapshot_ids
from ditto_application.commands.data_product_certification import (
    DataProductCertificationCommands,
)
from ditto_application.commands.data_product_certification_builder import (
    AddressedCertificationEvidence,
    CertificationBuildRequest,
    DataProductCertificationBuilder,
)
from ditto_application.exceptions import AppQueryError
from ditto_application.queries.market_context import (
    MarketContextFacade,
    MarketContextRequest,
)
from ditto_application.queries.market_context_evidence import (
    MarketContextEvidenceQueryFacade,
)
from ditto_data.catalog.certification import (
    CertificationGovernanceStore,
    DatasetCertificationReport,
)
from ditto_data.catalog.metadata import default_dataset_metadata
from ditto_data.catalog.provider_payload import (
    ProviderPayloadArtifact,
    ProviderPayloadReader,
)
from ditto_data.catalog.source_snapshot import (
    ProviderSnapshot,
    ProviderSnapshotReader,
)

from ditto_apps.config.runtime import state_root_matches
from ditto_apps.registry.container import make_app_container
from ditto_apps.registry.contexts.query import create_query_context
from ditto_apps.scripts.r2_live_certification import (
    build_expected_dates,
    probe_consumer_payload,
)

__all__ = [
    "inspect_global_session_visibility",
    "main",
    "run_q2_live_market_context_acceptance",
    "select_interval_snapshot_ids",
]

_PROFILE = "research_daily"
_TARGET_DATE = date(2024, 3, 29)
_WINDOWS = {
    "global_index_daily": (_TARGET_DATE, _TARGET_DATE),
    "index_daily": (date(2024, 2, 1), _TARGET_DATE),
    "macro_indicators": (_TARGET_DATE, _TARGET_DATE),
    "stock_daily": (_TARGET_DATE, _TARGET_DATE),
}
_GLOBAL_DATASET = "global_index_daily"


@dataclass(frozen=True, slots=True)
class _CertifiedProduct:
    dataset_id: str
    report_id: str
    content_hash: str
    target_from: str
    target_to: str
    expected_partition_count: int
    snapshot_ids: tuple[str, ...]
    consumer_probe: Mapping[str, int | str]
    consumer_evidence_sha256: str


@dataclass(frozen=True, slots=True)
class _CertificationAuthority:
    data_root: Path
    evidence_root: Path
    recovery_path: Path
    recovery_hash: str
    generated_at: datetime
    actor: str
    builder: DataProductCertificationBuilder
    commands: DataProductCertificationCommands
    store: CertificationGovernanceStore


def select_interval_snapshot_ids(
    *,
    dataset_id: str,
    target_from: date,
    target_to: date,
    snapshots: Sequence[ProviderSnapshot],
) -> tuple[str, ...]:
    """Select only retained snapshots for the exact certified request interval."""
    selected = tuple(
        sorted(
            snapshot.snapshot_id
            for snapshot in snapshots
            if snapshot.dataset_id == dataset_id
            and date.fromisoformat(snapshot.request_start) == target_from
            and date.fromisoformat(snapshot.request_end) == target_to
            and snapshot.payload_retained
            and snapshot.payload_uri is not None
        )
    )
    if not selected:
        interval = f"{dataset_id}/{target_from.isoformat()}/{target_to.isoformat()}"
        raise ValueError(f"Q2 exact retained snapshot interval is missing: {interval}")
    return selected


def inspect_global_session_visibility(
    frame: pl.DataFrame,
    *,
    a_share_open: datetime,
    a_share_close: datetime,
) -> tuple[dict[str, object], ...]:
    """Prove real global closes are not treated as known before A-share open."""
    if (
        a_share_open.tzinfo is None
        or a_share_close.tzinfo is None
        or a_share_close <= a_share_open
    ):
        raise ValueError("Q2 A-share session boundaries must be ordered and aware")
    required = {"source_ticker", "timezone", "event_time"}
    if not required.issubset(frame.columns) or frame.is_empty():
        raise ValueError("Q2 global payload lacks session-time evidence")
    observations: list[dict[str, object]] = []
    for row in frame.select(sorted(required)).sort("source_ticker").to_dicts():
        event_time = cast("datetime", row["event_time"])
        if event_time.tzinfo is None:
            raise ValueError("Q2 global event_time must be timezone-aware")
        event_utc = event_time.astimezone(UTC)
        observations.append(
            {
                "source_ticker": str(row["source_ticker"]),
                "timezone": str(row["timezone"]),
                "event_time": event_utc.isoformat(),
                "visible_at_a_share_open": event_utc <= a_share_open,
                "visible_at_a_share_close": event_utc <= a_share_close,
            }
        )
    if not any(
        not item["visible_at_a_share_open"] and item["visible_at_a_share_close"]
        for item in observations
    ):
        raise ValueError("Q2 global payload did not exercise the same-day future close")
    return tuple(observations)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_addressed(root: Path, stem: str, payload: object) -> tuple[Path, str]:
    content = canonical_bytes(payload)
    digest = hashlib.sha256(content).hexdigest()
    path = root / f"{stem}.sha256-{digest}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() != content:
        raise ValueError(f"Q2 content-addressed evidence conflict: {path}")
    path.write_bytes(content)
    return path, digest


def _validate_recovery_evidence(path: Path) -> tuple[Path, str]:
    resolved = path.expanduser().resolve(strict=True)
    decoded: object = orjson.loads(resolved.read_bytes())
    if not isinstance(decoded, dict):
        raise ValueError("Q2 recovery evidence must be a passing addressed artifact")
    payload = cast("dict[str, object]", decoded)
    if payload.get("passed") is not True:
        raise ValueError("Q2 recovery evidence must be a passing addressed artifact")
    return resolved, _sha256_file(resolved)


def _validate_active_report(
    report: DatasetCertificationReport,
    *,
    target_from: date,
    target_to: date,
    snapshot_ids: tuple[str, ...],
    store: CertificationGovernanceStore,
) -> None:
    events = store.list_events(report.report_id)
    if (
        report.coverage.target_from != target_from
        or report.coverage.target_to != target_to
        or not report.coverage.is_complete
        or report.evidence.snapshot_ids != snapshot_ids
        or not events
        or events[-1].action != "approved"
    ):
        raise ValueError(f"Q2 active certification drift: {report.dataset_id}")


def _certify_product(
    *,
    dataset_id: str,
    target_from: date,
    target_to: date,
    expected_dates: tuple[date, ...],
    snapshot_ids: tuple[str, ...],
    authority: _CertificationAuthority,
) -> _CertifiedProduct:
    probe = probe_consumer_payload(authority.data_root, dataset_id)
    consumer_path, consumer_hash = _write_addressed(
        authority.evidence_root / "consumer" / dataset_id,
        "consumer-read-smoke",
        {
            "schema": "ditto.q2-consumer-evidence.v1",
            "dataset_id": dataset_id,
            "target_from": target_from.isoformat(),
            "target_to": target_to.isoformat(),
            "snapshot_ids": snapshot_ids,
            "probe": probe,
        },
    )
    active = authority.store.get_active_report(dataset_id, _PROFILE)
    if active is None:
        report = authority.builder.build(
            CertificationBuildRequest(
                dataset_id=dataset_id,
                profile=_PROFILE,
                target_from=target_from,
                target_to=target_to,
                expected_dates=expected_dates,
                snapshot_ids=snapshot_ids,
                generated_at=authority.generated_at,
                recovery_evidence=AddressedCertificationEvidence(
                    name="q1_isolated_backup_restore_hash_parity",
                    evidence_uri=(
                        f"artifact+sha256://q1/recovery/{authority.recovery_hash}"
                    ),
                    local_path=authority.recovery_path,
                    sha256_hex=authority.recovery_hash,
                ),
                consumer_evidence=AddressedCertificationEvidence(
                    name="q2_production_consumer_read_smoke",
                    evidence_uri=(
                        f"artifact+sha256://q2/consumer/{dataset_id}/{consumer_hash}"
                    ),
                    local_path=consumer_path,
                    sha256_hex=consumer_hash,
                ),
            )
        )
        active = authority.commands.freeze(report)
        authority.commands.review(
            active.report_id,
            reviewer=authority.actor,
            reviewed_at=authority.generated_at,
        )
    _validate_active_report(
        active,
        target_from=target_from,
        target_to=target_to,
        snapshot_ids=snapshot_ids,
        store=authority.store,
    )
    return _CertifiedProduct(
        dataset_id=dataset_id,
        report_id=active.report_id,
        content_hash=active.content_hash,
        target_from=target_from.isoformat(),
        target_to=target_to.isoformat(),
        expected_partition_count=len(expected_dates),
        snapshot_ids=snapshot_ids,
        consumer_probe=probe,
        consumer_evidence_sha256=consumer_hash,
    )


def _global_payload(
    snapshot: ProviderSnapshot,
    reader: ProviderPayloadReader,
) -> pl.DataFrame:
    if snapshot.payload_uri is None:
        raise ValueError("Q2 global snapshot lacks retained payload URI")
    return reader.read_payload(
        ProviderPayloadArtifact(
            dataset_id=snapshot.dataset_id,
            source=snapshot.source,
            checksum=snapshot.checksum,
            row_count=snapshot.row_count,
            uri=snapshot.payload_uri,
        )
    )


def _assert_market_context_contract(  # noqa: C901 - bounded evidence checklist
    payload: Mapping[str, object],
) -> None:
    if payload.get("status") not in {"ready", "degraded"}:
        raise ValueError("Q2 MarketContext must be ready or honestly degraded")
    if payload.get("regime_label") is None or payload.get("regime_score") is None:
        raise ValueError("Q2 MarketContext lacks deterministic regime output")
    impacts = payload.get("impacts")
    if not isinstance(impacts, Sequence) or isinstance(impacts, (str, bytes)):
        raise ValueError("Q2 MarketContext impacts are absent")
    domains: set[str] = set()
    for raw_impact in cast("Sequence[object]", impacts):
        if isinstance(raw_impact, Mapping):
            impact = cast("Mapping[str, object]", raw_impact)
            domain = impact.get("target_domain")
            if isinstance(domain, str):
                domains.add(domain)
    if not {"industry", "risk"}.issubset(domains):
        raise ValueError("Q2 regime must explain both industry and risk impacts")
    metrics = payload.get("metrics")
    if (
        not isinstance(metrics, Sequence)
        or isinstance(metrics, (str, bytes))
        or not metrics
    ):
        raise ValueError("Q2 MarketContext metrics are absent")
    for raw_metric in cast("Sequence[object]", metrics):
        if not isinstance(raw_metric, Mapping):
            raise ValueError("Q2 numeric metric lacks direct evidence reference")
        metric = cast("Mapping[str, object]", raw_metric)
        if not isinstance(metric.get("value"), int | float) or not metric.get(
            "evidence_ref"
        ):
            raise ValueError("Q2 numeric metric lacks direct evidence reference")
    if payload.get("status") == "degraded" and not payload.get("missing_inputs"):
        raise ValueError("Q2 degraded context must declare missing inputs")


def run_q2_live_market_context_acceptance(  # noqa: PLR0915 - vertical acceptance flow
    *,
    data_root: Path,
    evidence_root: Path,
    recovery_evidence: Path,
    actor: str,
) -> dict[str, object]:
    """Freeze bounded certifications and prove exact PIT/Agent replay behavior."""
    root = data_root.expanduser().resolve(strict=True)
    if not state_root_matches(root):
        raise ValueError("DITTO_STATE_ROOT must equal the isolated Q2 data root")
    if not actor or actor.strip() != actor:
        raise ValueError("Q2 certification actor is invalid")
    evidence_dir = evidence_root.expanduser().resolve(strict=False)
    recovery_path, recovery_hash = _validate_recovery_evidence(recovery_evidence)
    registry = default_dataset_metadata()

    with create_query_context() as query_context:
        container = make_app_container()
        try:
            snapshot_reader = container.get(ProviderSnapshotReader)
            selected: dict[str, tuple[str, ...]] = {}
            selected_snapshots: list[ProviderSnapshot] = []
            expected: dict[str, tuple[date, ...]] = {}
            for dataset_id, (target_from, target_to) in _WINDOWS.items():
                snapshots = snapshot_reader.list_snapshots(dataset_id=dataset_id)
                ids = select_interval_snapshot_ids(
                    dataset_id=dataset_id,
                    target_from=target_from,
                    target_to=target_to,
                    snapshots=snapshots,
                )
                selected[dataset_id] = ids
                selected_snapshots.extend(
                    snapshot
                    for snapshot in snapshots
                    if snapshot.snapshot_id in frozenset(ids)
                )
                expected[dataset_id] = build_expected_dates(
                    schedule=registry[dataset_id].schedule,
                    target_from=target_from,
                    target_to=target_to,
                    trading_days_provider=query_context.metadata.list_trading_days,
                )
            generated_at = max(
                snapshot.created_at for snapshot in selected_snapshots
            ) + timedelta(minutes=1)
            builder = container.get(DataProductCertificationBuilder)
            commands = container.get(DataProductCertificationCommands)
            store = container.get(CertificationGovernanceStore)
            authority = _CertificationAuthority(
                data_root=root,
                evidence_root=evidence_dir,
                recovery_path=recovery_path,
                recovery_hash=recovery_hash,
                generated_at=generated_at,
                actor=actor,
                builder=builder,
                commands=commands,
                store=store,
            )
            products = tuple(
                _certify_product(
                    dataset_id=dataset_id,
                    target_from=target_from,
                    target_to=target_to,
                    expected_dates=expected[dataset_id],
                    snapshot_ids=selected[dataset_id],
                    authority=authority,
                )
                for dataset_id, (target_from, target_to) in _WINDOWS.items()
            )
            snapshot_ids = tuple(
                sorted(
                    {
                        snapshot_id
                        for product in products
                        for snapshot_id in product.snapshot_ids
                    }
                )
            )
            snapshot_set_id = aggregate_source_snapshot_ids(snapshot_ids)
            if snapshot_set_id is None:
                raise ValueError("Q2 certified snapshot set is empty")

            early_as_of = min(
                snapshot.created_at for snapshot in selected_snapshots
            ) - timedelta(microseconds=1)
            market = container.get(MarketContextFacade)
            try:
                market.get_context(
                    MarketContextRequest(
                        as_of=early_as_of,
                        knowledge_cutoff=early_as_of,
                        publication_cutoff=early_as_of,
                        source_snapshot_ids=snapshot_ids,
                    )
                )
            except AppQueryError as error:
                early_rejection = {
                    "as_of": early_as_of.isoformat(),
                    "error_type": type(error).__name__,
                    "message": str(error),
                    "passed": True,
                }
            else:
                raise ValueError(
                    "Q2 pre-acquisition historical query did not fail closed"
                )

            replay_at = generated_at + timedelta(minutes=1)
            context = TemporalToolContext.from_host(
                TemporalContextInput(
                    decision_time=replay_at,
                    knowledge_cutoff=replay_at,
                    publication_cutoff=replay_at,
                    source_snapshot_id=snapshot_set_id,
                    execution_eligible_at="not_applicable",
                    allowed_universe=("000300.SH", "000852.SH"),
                    license_class="approved-research",
                    egress_class=EgressClass.CLOUD_ALLOWED,
                )
            )
            tool = MarketContextEvidenceTool(
                facade=container.get(MarketContextEvidenceQueryFacade)
            )
            first = tool.invoke(arguments={}, context=context)
            second = tool.invoke(arguments={}, context=context)
            if (
                not first.verify_integrity()
                or not second.verify_integrity()
                or first.integrity_hash != second.integrity_hash
                or canonical_sha256(first.integrity_payload())
                != canonical_sha256(second.integrity_payload())
            ):
                raise ValueError("Q2 historical Agent replay is non-deterministic")
            payload = cast("Mapping[str, object]", first.result["payload"])
            _assert_market_context_contract(payload)

            global_snapshot = next(
                snapshot
                for snapshot in selected_snapshots
                if snapshot.dataset_id == _GLOBAL_DATASET
            )
            global_frame = _global_payload(
                global_snapshot,
                container.get(ProviderPayloadReader),
            )
            session_date = _TARGET_DATE
            global_visibility = inspect_global_session_visibility(
                global_frame,
                a_share_open=datetime.combine(
                    session_date,
                    time(1, 30),
                    tzinfo=UTC,
                ),
                a_share_close=datetime.combine(
                    session_date,
                    time(7),
                    tzinfo=UTC,
                ),
            )
        finally:
            container.close()

    return {
        "schema": "ditto.q2-live-market-context.v1",
        "generated_at": generated_at,
        "data_root": str(root),
        "profile": _PROFILE,
        "certifications": products,
        "source_snapshot_ids": snapshot_ids,
        "source_snapshot_set_id": snapshot_set_id,
        "market_context": payload,
        "regime_to_industry_and_risk": payload["impacts"],
        "missing_data_behavior": {
            "status": payload["status"],
            "missing_inputs": payload["missing_inputs"],
            "uncertainties": payload["uncertainties"],
            "passed": payload["status"] in {"ready", "degraded"},
        },
        "global_session_visibility": global_visibility,
        "historical_replay": {
            "replay_as_of": replay_at,
            "first_integrity_hash": first.integrity_hash,
            "second_integrity_hash": second.integrity_hash,
            "deterministic": first.integrity_hash == second.integrity_hash,
            "pre_acquisition_rejection": early_rejection,
        },
        "agent_evidence": {
            "tool_name": first.tool_name,
            "evidence_id": first.evidence_id,
            "integrity_hash": first.integrity_hash,
            "artifact_refs": first.artifact_refs,
            "lineage": first.lineage,
            "all_numeric_metrics_cited": True,
            "approved_egress_class": context.egress_class,
            "license_class": context.license_class,
        },
        "recovery_evidence": {
            "path": str(recovery_path),
            "sha256": recovery_hash,
        },
        "criteria": {
            "market_context_view": True,
            "regime_industry_risk_explanation": True,
            "global_overnight_timing": True,
            "missing_data_fail_closed_or_degraded": True,
            "agent_evidence_brief_envelope": True,
            "historical_as_of_replay": True,
        },
        "passed": True,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", required=True, type=Path)
    parser.add_argument("--evidence-root", required=True, type=Path)
    parser.add_argument("--recovery-evidence", required=True, type=Path)
    parser.add_argument("--actor", required=True)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Write the canonical Q2 evidence artifact."""
    args = _parser().parse_args(argv)
    result = run_q2_live_market_context_acceptance(
        data_root=args.data_root,
        evidence_root=args.evidence_root,
        recovery_evidence=args.recovery_evidence,
        actor=cast("str", args.actor),
    )
    output = args.output.expanduser().resolve(strict=False)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(
        orjson.dumps(
            orjson.loads(canonical_bytes(result)),
            option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS,
        )
        + b"\n"
    )
    sys.stdout.write(
        orjson.dumps(
            {
                "evidence_sha256": _sha256_file(output),
                "passed": result["passed"],
                "source_snapshot_set_id": result["source_snapshot_set_id"],
            },
            option=orjson.OPT_SORT_KEYS,
        ).decode()
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
