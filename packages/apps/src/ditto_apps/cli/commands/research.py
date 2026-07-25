"""Research experiment CLI commands (query + control)."""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from typing import Annotated

import typer
from ditto_application.commands.experiments import (
    CancelExperimentCommand,
    PauseExperimentCommand,
    ResumeExperimentCommand,
    RetryExperimentFoldCommand,
)
from ditto_application.processes.experiments._coordinator_contract import (
    ExperimentControlReceipt,
)

from ditto_apps.cli.utils.output import output_json_dict
from ditto_apps.registry.contexts import create_research_bundle

app = typer.Typer(help="研究实验查询与控制")


def _receipt_payload(receipt: ExperimentControlReceipt) -> dict[str, object]:
    """将 ExperimentControlReceipt 转 CLI JSON 输出."""
    return {
        "experiment_id": receipt.experiment_id,
        "status": receipt.status,
        "desired_state": receipt.desired_state,
        "revision": receipt.revision,
        "occurred_at": receipt.occurred_at.isoformat(),
        "live_run_ids": list(receipt.live_run_ids),
    }


@app.command("list-experiments")
def list_experiments() -> None:
    """列出研究实验 (newest first)."""
    with create_research_bundle() as bundle:
        summaries = bundle.experiment_query.list_experiments()
    output_json_dict({"experiments": [asdict(summary) for summary in summaries]})


@app.command("get-experiment")
def get_experiment(
    experiment_id: Annotated[str, typer.Argument(help="实验 ID")],
) -> None:
    """获取实验详情."""
    with create_research_bundle() as bundle:
        detail = bundle.experiment_query.get(experiment_id)
    if detail is None:
        typer.echo(f"Experiment not found: {experiment_id}", err=True)
        raise typer.Exit(code=1)
    output_json_dict(asdict(detail))


@app.command("list-gates")
def list_gates(
    experiment_id: Annotated[str, typer.Argument(help="实验 ID")],
) -> None:
    """列出实验的门禁评估."""
    with create_research_bundle() as bundle:
        gates = bundle.experiment_query.list_gate_evaluations(experiment_id)
    output_json_dict({"gates": [asdict(gate) for gate in gates]})


@app.command("pause")
def pause_experiment(
    experiment_id: Annotated[str, typer.Argument(help="实验 ID")],
    expected_revision: Annotated[
        int, typer.Option(help="当前 experiment projection revision")
    ],
) -> None:
    """请求暂停实验 (revision-fenced cooperative pause)."""
    with create_research_bundle() as bundle:
        receipt = bundle.pause_handler.handle(
            PauseExperimentCommand(
                experiment_id=experiment_id,
                expected_revision=expected_revision,
                occurred_at=datetime.now(UTC),
            )
        )
    output_json_dict(_receipt_payload(receipt))


@app.command("cancel")
def cancel_experiment(
    experiment_id: Annotated[str, typer.Argument(help="实验 ID")],
    expected_revision: Annotated[
        int, typer.Option(help="当前 experiment projection revision")
    ],
) -> None:
    """请求取消实验 (revision-fenced terminal cancel)."""
    with create_research_bundle() as bundle:
        receipt = bundle.cancel_handler.handle(
            CancelExperimentCommand(
                experiment_id=experiment_id,
                expected_revision=expected_revision,
                occurred_at=datetime.now(UTC),
            )
        )
    output_json_dict(_receipt_payload(receipt))


@app.command("resume")
def resume_experiment(
    experiment_id: Annotated[str, typer.Argument(help="实验 ID")],
    expected_revision: Annotated[
        int, typer.Option(help="当前 experiment projection revision")
    ],
) -> None:
    """请求恢复实验 (revision-fenced resume of one paused experiment)."""
    with create_research_bundle() as bundle:
        receipt = bundle.resume_handler.handle(
            ResumeExperimentCommand(
                experiment_id=experiment_id,
                expected_revision=expected_revision,
                occurred_at=datetime.now(UTC),
            )
        )
    output_json_dict(_receipt_payload(receipt))


@app.command("retry-fold")
def retry_fold(
    experiment_id: Annotated[str, typer.Argument(help="实验 ID")],
    candidate_id: Annotated[str, typer.Argument(help="候选 ID")],
    fold_id: Annotated[str, typer.Argument(help="fold ID")],
    expected_revision: Annotated[
        int,
        typer.Option(help="当前 fold projection revision (not experiment revision)"),
    ],
) -> None:
    """请求重试一个失败 fold (revision-fenced successor attempt)."""
    with create_research_bundle() as bundle:
        receipt = bundle.retry_fold_handler.handle(
            RetryExperimentFoldCommand(
                experiment_id=experiment_id,
                candidate_id=candidate_id,
                fold_id=fold_id,
                expected_revision=expected_revision,
                occurred_at=datetime.now(UTC),
            )
        )
    output_json_dict(_receipt_payload(receipt))
