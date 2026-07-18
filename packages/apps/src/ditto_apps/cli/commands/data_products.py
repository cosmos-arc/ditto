"""Guarded R2 data-product bootstrap, repair, and governance commands."""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import UTC, datetime
from typing import Any

import typer
from ditto_application.commands.catalog import (
    DatasetPromotionReviewCommand,
    ReviewDatasetPromotionEvidenceHandler,
)
from ditto_application.commands.data_product_certification import (
    DataProductCertificationCommands,
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
    start_date: str | None = None
    end_date: str | None = None
    parallel: int = 1
    report_id: str | None = None
    actor: str | None = None
    criterion: str | None = None
    evidence_uri: str | None = None
    reason: str | None = None


def _required(value: str | None, option: str, operation: str) -> str:
    if value is None or not value.strip():
        raise AppCommandError(
            f"{option} is required to execute {operation}",
            command=f"execute_data_product_{operation}",
        )
    return value.strip()


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
        with create_ingestion_bundle(source=options.source) as bundle:
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
        if operation == "certify":
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


@app.command("bootstrap")
def bootstrap(
    dataset_id: str = typer.Argument(..., help="R2 数据产品 ID"),
    start_date: str | None = typer.Option(None, "--start-date"),
    end_date: str | None = typer.Option(None, "--end-date"),
    source: str = typer.Option("tushare", "--source"),
    parallel: int = typer.Option(1, "--parallel", min=1),
    confirm: str | None = typer.Option(None, "--confirm"),
) -> None:
    """Preview or execute a bounded historical bootstrap."""
    _run(
        "bootstrap",
        dataset_id,
        confirm,
        DataProductOperationOptions(
            source=source,
            start_date=start_date,
            end_date=end_date,
            parallel=parallel,
        ),
    )


@app.command("repair")
def repair(
    dataset_id: str = typer.Argument(..., help="R2 数据产品 ID"),
    source: str = typer.Option("tushare", "--source"),
    parallel: int = typer.Option(1, "--parallel", min=1),
    confirm: str | None = typer.Option(None, "--confirm"),
) -> None:
    """Preview or execute schedule-aware missing partition repair."""
    _run(
        "repair",
        dataset_id,
        confirm,
        DataProductOperationOptions(source=source, parallel=parallel),
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
