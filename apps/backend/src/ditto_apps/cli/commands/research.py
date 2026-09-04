"""Research experiment CLI commands (query + control)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, fields, is_dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Annotated, cast

import orjson
import typer
from ditto_application.commands.experiments import (
    CancelExperimentCommand,
    LaunchExperimentCommand,
    PauseExperimentCommand,
    ResumeExperimentCommand,
    RetryExperimentFoldCommand,
)
from ditto_application.processes.experiments._coordinator_contract import (
    ExperimentControlReceipt,
)
from ditto_application.processes.experiments.planning_process import (
    ExperimentLaunchReceipt,
    ExperimentPreflightReport,
)
from ditto_application.processes.experiments.planning_request_builder import (
    build_experiment_planning_request,
)
from pydantic import ValidationError

from ditto_apps.cli.utils.output import output_json_dict
from ditto_apps.models.research import ExperimentPlanningRequest
from ditto_apps.registry.contexts import create_research_bundle

app = typer.Typer(help="研究实验查询与控制")

type JsonScalar = str | bool | int | float | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]


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


def _to_json_value(value: object) -> JsonValue:
    """Convert immutable application values to JSON-native containers."""
    if isinstance(value, Mapping):
        mapping = cast("Mapping[object, object]", value)
        result: dict[str, JsonValue] = {}
        for key, item in mapping.items():
            if type(key) is not str:
                raise TypeError(
                    "research planning output mapping key must be exact str"
                )
            result[key] = _to_json_value(item)
        return result
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        sequence = cast("Sequence[object]", value)
        return [_to_json_value(item) for item in sequence]
    if value is None or type(value) in {str, bool, int, float}:
        return cast("JsonScalar", value)
    raise TypeError("research planning output must be JSON-compatible")


def _to_cli_value(value: object) -> object:
    """Serialize immutable read models without dataclasses deepcopy semantics."""
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _to_cli_value(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, Mapping):
        mapping = cast("Mapping[object, object]", value)
        result: dict[str, object] = {}
        for key, item in mapping.items():
            if type(key) is not str:
                raise TypeError("research CLI output mapping key must be exact str")
            result[key] = _to_cli_value(item)
        return result
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        sequence = cast("Sequence[object]", value)
        return [_to_cli_value(item) for item in sequence]
    if isinstance(value, date):
        return value.isoformat()
    if value is None or type(value) in {str, bool, int, float}:
        return value
    raise TypeError("research CLI output must be JSON-compatible")


def _read_model_payload(value: object) -> dict[str, object]:
    payload = _to_cli_value(value)
    if not isinstance(payload, dict):
        raise TypeError("research CLI read model must serialize to an object")
    return cast("dict[str, object]", payload)


def _preflight_payload(report: ExperimentPreflightReport) -> dict[str, object]:
    """Serialize the same typed preflight surface exposed over HTTP."""
    return {
        "status": report.status.value,
        "plan_hash": report.plan_hash,
        "checks": [
            {
                "rule_id": check.rule_id,
                "outcome": check.outcome.value,
                "code": check.code,
                "reason": check.reason,
                "remediation": check.remediation,
                "observed": _to_json_value(check.observed),
                "policy": _to_json_value(check.policy),
            }
            for check in report.checks
        ],
        "candidate_count": report.candidate_count,
        "planned_fold_count": report.planned_fold_count,
        "budget_run_count": report.budget_run_count,
        "estimated_trading_sessions": report.estimated_trading_sessions,
        "estimated_disk_bytes": report.estimated_disk_bytes,
        "eligible_month_count": report.eligible_month_count,
        "isolation_width_sessions": report.isolation_width_sessions,
    }


def _launch_payload(receipt: ExperimentLaunchReceipt) -> dict[str, object]:
    """Serialize durable launch server truth for both commit and exact replay."""
    return {
        "experiment_id": receipt.experiment_id,
        "status": receipt.status,
        "queue_ordinal": receipt.queue_ordinal,
        "revision": receipt.revision,
        "candidate_count": receipt.candidate_count,
        "fold_count": receipt.fold_count,
        "plan_hash": receipt.plan_hash,
    }


def _load_planning_document(document: Path) -> dict[str, object]:
    """Load and strictly validate one canonical planning document."""
    try:
        decoded = orjson.loads(document.read_bytes())
        request = ExperimentPlanningRequest.model_validate(decoded)
    except (OSError, orjson.JSONDecodeError, ValidationError) as exc:
        raise typer.BadParameter(
            "document must contain one strict canonical planning request",
            param_hint="--document",
        ) from exc
    return request.model_dump(mode="python")


@app.command("preflight")
def preflight_planning_document(
    document: Annotated[
        Path,
        typer.Option(
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            help="完整 canonical planning document JSON",
        ),
    ],
) -> None:
    """执行只读 experiment preflight."""
    request = build_experiment_planning_request(_load_planning_document(document))
    with create_research_bundle() as bundle:
        report = bundle.planning_process.preflight(request)
    output_json_dict(_preflight_payload(report))


@app.command("launch")
def launch_planning_document(
    document: Annotated[
        Path,
        typer.Option(
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            help="完整 canonical planning document JSON",
        ),
    ],
    confirmed_plan_hash: Annotated[
        str,
        typer.Option(help="操作者确认的 preflight plan_hash"),
    ],
) -> None:
    """重新构建并启动一个已确认计划."""
    request = build_experiment_planning_request(_load_planning_document(document))
    with create_research_bundle() as bundle:
        receipt = bundle.launch_handler.handle(
            LaunchExperimentCommand(
                request=request,
                confirmed_plan_hash=confirmed_plan_hash,
            )
        )
    output_json_dict(_launch_payload(receipt))


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
    output_json_dict(_read_model_payload(detail))


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
