"""Guarded R2 data-product bootstrap, repair, and governance commands."""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, cast

import orjson
import typer
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
from ditto_application.commands.data_product_license import (
    DataProductLicenseCommands,
    DataProductLicensePermission,
    ReviewDataProductLicense,
)
from ditto_application.commands.data_product_operations import (
    DataProductOperation,
    confirm_data_product_operation,
    preview_data_product_operation,
)
from ditto_application.exceptions import AppCommandError

from ditto_apps.cli.utils.output import output_json_dict
from ditto_apps.registry.container import make_app_container
from ditto_apps.registry.contexts.ingestion import create_ingestion_bundle

app = typer.Typer(help="R2 数据产品回补、认证与晋级治理")


@dataclass(frozen=True, slots=True)
class DataProductOperationOptions:
    """Execution-only options shared by the guarded operation entrypoints."""

    source: str = "tushare"
    license_record_id: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    parallel: int = 1
    instrument_ids: tuple[int, ...] = ()
    report_id: str | None = None
    actor: str | None = None
    criterion: str | None = None
    evidence_uri: str | None = None
    reason: str | None = None
    terms_version: str | None = None
    effective_from: str | None = None
    effective_to: str | None = None
    local_cache: str | None = None
    derivative_compute: str | None = None
    display: str | None = None
    redistribution: str | None = None
    notes: str | None = None
    profile: str | None = None
    target_from: str | None = None
    target_to: str | None = None
    expected_dates_file: str | None = None
    snapshot_ids_file: str | None = None
    recovery_evidence_path: str | None = None
    recovery_evidence_uri: str | None = None
    recovery_evidence_sha256: str | None = None
    consumer_evidence_path: str | None = None
    consumer_evidence_uri: str | None = None
    consumer_evidence_sha256: str | None = None


def _required(value: str | None, option: str, operation: str) -> str:
    if value is None or not value.strip():
        raise AppCommandError(
            f"{option} is required to execute {operation}",
            command=f"execute_data_product_{operation}",
        )
    return value.strip()


def _date(value: str | None, option: str, operation: str) -> date:
    raw = _required(value, option, operation)
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise AppCommandError(
            f"{option} must use YYYY-MM-DD",
            command=f"execute_data_product_{operation}",
        ) from exc


def _optional_date(value: str | None, option: str, operation: str) -> date | None:
    return None if value is None else _date(value, option, operation)


def _permission(
    value: str | None,
    option: str,
    operation: str,
) -> DataProductLicensePermission:
    raw = _required(value, option, operation)
    if raw not in {"allowed", "restricted", "prohibited"}:
        raise AppCommandError(
            f"{option} must be allowed, restricted, or prohibited",
            command=f"execute_data_product_{operation}",
        )
    return cast("DataProductLicensePermission", raw)


def _expected_dates(value: str | None, operation: str) -> tuple[date, ...]:
    path = Path(_required(value, "--expected-dates-file", operation))
    try:
        decoded = orjson.loads(path.read_bytes())
        if type(decoded) is not list:
            raise ValueError
        raw_dates = cast("list[object]", decoded)
        if not all(type(item) is str for item in raw_dates):
            raise ValueError
        dates = tuple(date.fromisoformat(item) for item in cast("list[str]", raw_dates))
    except (OSError, TypeError, ValueError, orjson.JSONDecodeError) as exc:
        raise AppCommandError(
            "--expected-dates-file must contain a JSON array of ISO dates",
            command=f"execute_data_product_{operation}",
        ) from exc
    if not dates or dates != tuple(sorted(set(dates))):
        raise AppCommandError(
            "--expected-dates-file dates must be non-empty, unique, and sorted",
            command=f"execute_data_product_{operation}",
        )
    return dates


def _snapshot_ids(value: str | None, operation: str) -> tuple[str, ...]:
    if value is None:
        return ()
    path = Path(value)
    try:
        decoded = orjson.loads(path.read_bytes())
        if type(decoded) is not list:
            raise ValueError
        raw_ids = cast("list[object]", decoded)
        if not all(type(item) is str and item for item in raw_ids):
            raise ValueError
        snapshot_ids = tuple(cast("list[str]", raw_ids))
    except (OSError, ValueError, orjson.JSONDecodeError) as exc:
        raise AppCommandError(
            "--snapshot-ids-file must contain a JSON array of snapshot IDs",
            command=f"execute_data_product_{operation}",
        ) from exc
    if not snapshot_ids or snapshot_ids != tuple(sorted(set(snapshot_ids))):
        raise AppCommandError(
            "--snapshot-ids-file IDs must be non-empty, unique, and sorted",
            command=f"execute_data_product_{operation}",
        )
    return snapshot_ids


def _addressed_evidence(
    *,
    name: str,
    path: str | None,
    uri: str | None,
    sha256_hex: str | None,
    operation: str,
) -> AddressedCertificationEvidence:
    return AddressedCertificationEvidence(
        name=name,
        evidence_uri=_required(uri, f"--{name}-evidence-uri", operation),
        local_path=Path(_required(path, f"--{name}-evidence-path", operation)),
        sha256_hex=_required(
            sha256_hex,
            f"--{name}-evidence-sha256",
            operation,
        ),
    )


def _result_payload(value: object) -> dict[str, Any]:
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    return {"result": str(value)}


def execute_data_product_operation(
    operation: DataProductOperation,
    dataset_id: str,
    options: DataProductOperationOptions,
) -> dict[str, Any]:
    """Execute one already-confirmed operation through application services."""
    if operation in {"bootstrap", "repair"}:
        with create_ingestion_bundle(
            source=options.source,
            license_record_id=options.license_record_id,
        ) as bundle:
            if operation == "bootstrap":
                result = bundle.backfill_manager.backfill_range(
                    dataset=dataset_id,
                    start_date=_required(
                        options.start_date,
                        "--start-date",
                        operation,
                    ),
                    end_date=_required(options.end_date, "--end-date", operation),
                    parallel=options.parallel,
                    instrument_ids=options.instrument_ids,
                )
            else:
                result = bundle.backfill_manager.backfill_missing(
                    dataset=dataset_id,
                    source=options.source,
                    parallel=options.parallel,
                )
        return {"status": "completed", **_result_payload(result)}

    container = make_app_container()
    try:
        if operation == "license":
            command = container.get(DataProductLicenseCommands)
            result = command.review(
                ReviewDataProductLicense(
                    dataset_id=dataset_id,
                    source=options.source,
                    terms_version=_required(
                        options.terms_version,
                        "--terms-version",
                        operation,
                    ),
                    effective_from=_date(
                        options.effective_from,
                        "--effective-from",
                        operation,
                    ),
                    effective_to=_optional_date(
                        options.effective_to,
                        "--effective-to",
                        operation,
                    ),
                    local_cache=_permission(
                        options.local_cache,
                        "--local-cache",
                        operation,
                    ),
                    derivative_compute=_permission(
                        options.derivative_compute,
                        "--derivative-compute",
                        operation,
                    ),
                    display=_permission(options.display, "--display", operation),
                    redistribution=_permission(
                        options.redistribution,
                        "--redistribution",
                        operation,
                    ),
                    notes=_required(options.notes, "--notes", operation),
                    reviewed_by=_required(options.actor, "--actor", operation),
                    reviewed_at=datetime.now(UTC),
                )
            )
        elif operation == "build-certification":
            builder = container.get(DataProductCertificationBuilder)
            command = container.get(DataProductCertificationCommands)
            report = builder.build(
                CertificationBuildRequest(
                    dataset_id=dataset_id,
                    profile=_required(options.profile, "--profile", operation),
                    target_from=_optional_date(
                        options.target_from,
                        "--target-from",
                        operation,
                    ),
                    target_to=_date(options.target_to, "--target-to", operation),
                    expected_dates=_expected_dates(
                        options.expected_dates_file,
                        operation,
                    ),
                    snapshot_ids=_snapshot_ids(
                        options.snapshot_ids_file,
                        operation,
                    ),
                    generated_at=datetime.now(UTC),
                    recovery_evidence=_addressed_evidence(
                        name="recovery",
                        path=options.recovery_evidence_path,
                        uri=options.recovery_evidence_uri,
                        sha256_hex=options.recovery_evidence_sha256,
                        operation=operation,
                    ),
                    consumer_evidence=_addressed_evidence(
                        name="consumer",
                        path=options.consumer_evidence_path,
                        uri=options.consumer_evidence_uri,
                        sha256_hex=options.consumer_evidence_sha256,
                        operation=operation,
                    ),
                )
            )
            result = command.freeze(report)
        elif operation == "certify":
            command = container.get(DataProductCertificationCommands)
            result = command.review(
                _required(options.report_id, "--report-id", operation),
                reviewer=_required(options.actor, "--actor", operation),
                reviewed_at=datetime.now(UTC),
            )
        elif operation == "promotion":
            handler = container.get(ReviewDatasetPromotionEvidenceHandler)
            result = handler.handle(
                DatasetPromotionReviewCommand(
                    dataset_id=dataset_id,
                    criterion=_required(
                        options.criterion,
                        "--criterion",
                        operation,
                    ),
                    evidence_uri=_required(
                        options.evidence_uri,
                        "--evidence-uri",
                        operation,
                    ),
                    reviewed_by=_required(options.actor, "--actor", operation),
                )
            )
        else:
            command = container.get(DataProductCertificationCommands)
            result = command.revoke(
                _required(options.report_id, "--report-id", operation),
                revoked_by=_required(options.actor, "--actor", operation),
                revoked_at=datetime.now(UTC),
                reason=_required(options.reason, "--reason", operation),
            )
        return {"status": "completed", **_result_payload(result)}
    finally:
        container.close()


def _run(
    operation: DataProductOperation,
    dataset_id: str,
    confirm: str | None,
    options: DataProductOperationOptions,
) -> None:
    preview = preview_data_product_operation(operation, dataset_id)
    if confirm is None:
        output_json_dict(asdict(preview))
        return
    try:
        confirm_data_product_operation(preview, confirm)
        result = execute_data_product_operation(
            operation,
            dataset_id,
            options,
        )
    except AppCommandError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(2) from exc
    output_json_dict(result)
    failed_count = result.get("failed_count")
    if (
        operation in {"bootstrap", "repair"}
        and isinstance(failed_count, int)
        and failed_count > 0
    ):
        raise typer.Exit(1)


@app.command("bootstrap")
def bootstrap(  # noqa: PLR0913 — CLI 命令回调，参数由 Typer 注入
    dataset_id: str = typer.Argument(..., help="R2 数据产品 ID"),
    start_date: str | None = typer.Option(None, "--start-date"),
    end_date: str | None = typer.Option(None, "--end-date"),
    source: str = typer.Option("tushare", "--source"),
    license_record_id: str | None = typer.Option(None, "--license-record-id"),
    parallel: int = typer.Option(1, "--parallel", min=1),
    instrument_id: list[int] | None = typer.Option(None, "--instrument-id"),
    confirm: str | None = typer.Option(None, "--confirm"),
) -> None:
    """Preview or execute a bounded historical bootstrap."""
    _run(
        "bootstrap",
        dataset_id,
        confirm,
        DataProductOperationOptions(
            source=source,
            license_record_id=license_record_id,
            start_date=start_date,
            end_date=end_date,
            parallel=parallel,
            instrument_ids=tuple(instrument_id or ()),
        ),
    )


@app.command("repair")
def repair(
    dataset_id: str = typer.Argument(..., help="R2 数据产品 ID"),
    source: str = typer.Option("tushare", "--source"),
    license_record_id: str | None = typer.Option(None, "--license-record-id"),
    parallel: int = typer.Option(1, "--parallel", min=1),
    confirm: str | None = typer.Option(None, "--confirm"),
) -> None:
    """Preview or execute schedule-aware missing partition repair."""
    _run(
        "repair",
        dataset_id,
        confirm,
        DataProductOperationOptions(
            source=source,
            license_record_id=license_record_id,
            parallel=parallel,
        ),
    )


@app.command("certify")
def certify(
    dataset_id: str = typer.Argument(..., help="R2 数据产品 ID"),
    report_id: str | None = typer.Option(None, "--report-id"),
    actor: str | None = typer.Option(None, "--actor"),
    confirm: str | None = typer.Option(None, "--confirm"),
) -> None:
    """Preview or approve one immutable certification report."""
    _run(
        "certify",
        dataset_id,
        confirm,
        DataProductOperationOptions(report_id=report_id, actor=actor),
    )


@app.command("license")
def license_review(  # noqa: PLR0913 — CLI 命令回调，参数由 Typer 注入
    dataset_id: str = typer.Argument(..., help="R2 数据产品 ID"),
    source: str = typer.Option("tushare", "--source"),
    terms_version: str | None = typer.Option(None, "--terms-version"),
    effective_from: str | None = typer.Option(None, "--effective-from"),
    effective_to: str | None = typer.Option(None, "--effective-to"),
    local_cache: str | None = typer.Option(None, "--local-cache"),
    derivative_compute: str | None = typer.Option(None, "--derivative-compute"),
    display: str | None = typer.Option(None, "--display"),
    redistribution: str | None = typer.Option(None, "--redistribution"),
    notes: str | None = typer.Option(None, "--notes"),
    actor: str | None = typer.Option(None, "--actor"),
    confirm: str | None = typer.Option(None, "--confirm"),
) -> None:
    """Preview or append one explicit, human-reviewed provider license record."""
    _run(
        "license",
        dataset_id,
        confirm,
        DataProductOperationOptions(
            source=source,
            terms_version=terms_version,
            effective_from=effective_from,
            effective_to=effective_to,
            local_cache=local_cache,
            derivative_compute=derivative_compute,
            display=display,
            redistribution=redistribution,
            notes=notes,
            actor=actor,
        ),
    )


@app.command("build-certification")
def build_certification(  # noqa: PLR0913 — CLI 命令回调，参数由 Typer 注入
    dataset_id: str = typer.Argument(..., help="R2 数据产品 ID"),
    profile: str | None = typer.Option(None, "--profile"),
    target_from: str | None = typer.Option(None, "--target-from"),
    target_to: str | None = typer.Option(None, "--target-to"),
    expected_dates_file: str | None = typer.Option(None, "--expected-dates-file"),
    snapshot_ids_file: str | None = typer.Option(None, "--snapshot-ids-file"),
    recovery_evidence_path: str | None = typer.Option(None, "--recovery-evidence-path"),
    recovery_evidence_uri: str | None = typer.Option(None, "--recovery-evidence-uri"),
    recovery_evidence_sha256: str | None = typer.Option(
        None, "--recovery-evidence-sha256"
    ),
    consumer_evidence_path: str | None = typer.Option(None, "--consumer-evidence-path"),
    consumer_evidence_uri: str | None = typer.Option(None, "--consumer-evidence-uri"),
    consumer_evidence_sha256: str | None = typer.Option(
        None, "--consumer-evidence-sha256"
    ),
    confirm: str | None = typer.Option(None, "--confirm"),
) -> None:
    """Preview or freeze one machine-built certification report."""
    _run(
        "build-certification",
        dataset_id,
        confirm,
        DataProductOperationOptions(
            profile=profile,
            target_from=target_from,
            target_to=target_to,
            expected_dates_file=expected_dates_file,
            snapshot_ids_file=snapshot_ids_file,
            recovery_evidence_path=recovery_evidence_path,
            recovery_evidence_uri=recovery_evidence_uri,
            recovery_evidence_sha256=recovery_evidence_sha256,
            consumer_evidence_path=consumer_evidence_path,
            consumer_evidence_uri=consumer_evidence_uri,
            consumer_evidence_sha256=consumer_evidence_sha256,
        ),
    )


@app.command("promotion")
def promotion(
    dataset_id: str = typer.Argument(..., help="R2 数据产品 ID"),
    criterion: str | None = typer.Option(None, "--criterion"),
    evidence_uri: str | None = typer.Option(None, "--evidence-uri"),
    actor: str | None = typer.Option(None, "--actor"),
    confirm: str | None = typer.Option(None, "--confirm"),
) -> None:
    """Preview or append one independent maturity-promotion decision."""
    _run(
        "promotion",
        dataset_id,
        confirm,
        DataProductOperationOptions(
            actor=actor,
            criterion=criterion,
            evidence_uri=evidence_uri,
        ),
    )


@app.command("revoke")
def revoke(
    dataset_id: str = typer.Argument(..., help="R2 数据产品 ID"),
    report_id: str | None = typer.Option(None, "--report-id"),
    actor: str | None = typer.Option(None, "--actor"),
    reason: str | None = typer.Option(None, "--reason"),
    confirm: str | None = typer.Option(None, "--confirm"),
) -> None:
    """Preview or revoke one active certification without deleting history."""
    _run(
        "revoke",
        dataset_id,
        confirm,
        DataProductOperationOptions(
            report_id=report_id,
            actor=actor,
            reason=reason,
        ),
    )
