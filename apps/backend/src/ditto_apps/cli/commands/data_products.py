"""Guarded R2 data-product bootstrap and repair commands."""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path
from typing import Any

import typer
from ditto_application.commands.data_product_operations import (
    DataProductOperation,
    confirm_data_product_operation,
    preview_data_product_operation,
)
from ditto_application.exceptions import AppCommandError, AppProcessError, AppQueryError
from ditto_application.queries.provider_snapshot import (
    ProviderSnapshotQuery,
    SnapshotReplayRequest,
)
from pydantic import TypeAdapter, ValidationError

from ditto_apps.cli.utils.output import output_json_dict
from ditto_apps.registry.container import make_app_container
from ditto_apps.registry.contexts.ingestion import create_ingestion_bundle

app = typer.Typer(help="R2 数据产品回补与修复")


@dataclass(frozen=True, slots=True)
class DataProductOperationOptions:
    """Execution-only options shared by the guarded operation entrypoints."""

    source: str = "tushare"
    start_date: str | None = None
    end_date: str | None = None
    parallel: int = 1
    instrument_ids: tuple[int, ...] = ()


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
                instrument_ids=options.instrument_ids,
            )
        else:
            result = bundle.backfill_manager.backfill_missing(
                dataset=dataset_id,
                source=options.source,
                parallel=options.parallel,
            )
    return {"status": "completed", **_result_payload(result)}


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
    except (AppCommandError, AppProcessError) as exc:
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
def bootstrap(
    dataset_id: str = typer.Argument(..., help="R2 数据产品 ID"),
    start_date: str | None = typer.Option(None, "--start-date"),
    end_date: str | None = typer.Option(None, "--end-date"),
    source: str = typer.Option("tushare", "--source"),
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
            parallel=parallel,
        ),
    )


@app.command("read-snapshot")
def read_snapshot(snapshot_id: str = typer.Argument(...)) -> None:
    """Read completed immutable evidence for audit, without granting new eligibility."""
    container = make_app_container()
    try:
        contents = container.get(ProviderSnapshotQuery).read_for_audit(snapshot_id)
        output_json_dict(
            {
                "use": "audit",
                "snapshot": asdict(contents.snapshot),
                "previous_snapshot_id": contents.previous_snapshot_id,
                "observed_at": contents.observed_at,
                "rows": contents.frame.to_dicts(),
            }
        )
    except AppQueryError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(2) from error
    finally:
        container.close()


@app.command("replay-snapshots")
def replay_snapshots(
    request_file: Path = typer.Argument(..., exists=True, dir_okay=False),
) -> None:
    """Read qualified fields at explicit snapshot identities and PIT cutoffs."""
    container = make_app_container()
    try:
        request = TypeAdapter(SnapshotReplayRequest).validate_json(
            request_file.read_bytes()
        )
        result = container.get(ProviderSnapshotQuery).replay(request)
        output_json_dict(
            {
                "request": asdict(request),
                "readiness": asdict(result.readiness),
                "snapshots": {
                    key: frame.to_dicts() for key, frame in result.frames.items()
                },
            }
        )
    except (OSError, ValidationError, AppQueryError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(2) from error
    finally:
        container.close()


__all__ = [
    "DataProductOperationOptions",
    "app",
    "bootstrap",
    "execute_data_product_operation",
    "read_snapshot",
    "repair",
    "replay_snapshots",
]
