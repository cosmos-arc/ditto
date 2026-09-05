"""Operational CLI command for governed Agent raw-content retention."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Never

import orjson
import typer
from ditto_agent.retention import (
    RetentionExecutionResult,
    RetentionPlan,
    RetentionPlanConflict,
)

from ditto_apps.registry.agent.retention import (
    AgentRetentionUnavailable,
    open_agent_retention_service,
)

_retention_service = open_agent_retention_service


def _emit_json(payload: object, *, err: bool = False) -> None:
    encoded = orjson.dumps(
        payload,
        option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS | orjson.OPT_UTC_Z,
    )
    typer.echo(encoded.decode(), err=err)


def _exit_invalid(*, json_output: bool) -> Never:
    if json_output:
        _emit_json(
            {
                "error": {
                    "code": "AGENT_RETENTION_REQUEST_INVALID",
                    "message": "Agent retention request is invalid",
                }
            },
            err=True,
        )
    else:
        typer.echo(
            "AGENT_RETENTION_REQUEST_INVALID: Agent retention request is invalid",
            err=True,
        )
    raise typer.Exit(2)


def _exit_unavailable(*, json_output: bool) -> Never:
    if json_output:
        _emit_json(
            {
                "error": {
                    "code": "AGENT_RETENTION_UNAVAILABLE",
                    "message": "Agent retention service is unavailable",
                }
            },
            err=True,
        )
    else:
        typer.echo(
            "AGENT_RETENTION_UNAVAILABLE: Agent retention service is unavailable",
            err=True,
        )
    raise typer.Exit(3)


def _plan_payload(plan: RetentionPlan) -> dict[str, object]:
    return {
        "mode": "dry_run",
        "schema_version": 1,
        "plan_hash": plan.plan_hash,
        "as_of": plan.as_of.isoformat(),
        "cutoff": plan.cutoff.isoformat(),
        "candidate_count": len(plan.candidates),
        "candidates": [
            {
                "target_kind": candidate.target_kind,
                "target_id": candidate.target_id,
                "content_hash": candidate.content_hash,
                "stored_at": candidate.stored_at.isoformat(),
            }
            for candidate in plan.candidates
        ],
    }


def _execution_payload(result: RetentionExecutionResult) -> dict[str, object]:
    return {
        "mode": "execute",
        "schema_version": 1,
        "plan_hash": result.plan_hash,
        "approval_id": result.approval_id,
        "deleted_count": len(result.deleted_target_ids),
        "deleted_target_ids": list(result.deleted_target_ids),
        "audit_payload_hash": result.audit_payload_hash,
        "executed_at": result.executed_at.isoformat(),
    }


def cleanup_agent_retention(
    data_root: Annotated[
        Path | None,
        typer.Option(help="Agent nominal database data root"),
    ] = None,
    execute: Annotated[
        bool,
        typer.Option("--execute", help="执行已 dry-run 并获批的 exact plan"),
    ] = False,
    expected_plan_hash: Annotated[
        str | None,
        typer.Option(help="人工复核的 dry-run plan SHA-256"),
    ] = None,
    approval_id: Annotated[
        str | None,
        typer.Option(help="本次真实清理的外部审批 evidence ID"),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="输出稳定 JSON"),
    ] = False,
) -> None:
    """默认只列出 30 天到期 raw continuation；执行需 hash 与审批双确认。"""
    try:
        with _retention_service(data_root) as service:
            plan = service.dry_run(as_of=datetime.now(UTC))
            if not execute:
                if json_output:
                    _emit_json(_plan_payload(plan))
                else:
                    typer.echo(
                        " ".join(
                            (
                                "mode=dry_run",
                                f"plan_hash={plan.plan_hash}",
                                f"candidate_count={len(plan.candidates)}",
                            )
                        )
                    )
                return
            if expected_plan_hash is None or approval_id is None:
                _exit_invalid(json_output=json_output)
            result = service.execute(
                plan,
                expected_plan_hash=expected_plan_hash,
                approval_id=approval_id,
                executed_at=datetime.now(UTC),
            )
    except (RetentionPlanConflict, ValueError):
        _exit_invalid(json_output=json_output)
    except AgentRetentionUnavailable:
        _exit_unavailable(json_output=json_output)
    if json_output:
        _emit_json(_execution_payload(result))
        return
    typer.echo(
        " ".join(
            (
                "mode=execute",
                f"plan_hash={result.plan_hash}",
                f"deleted_count={len(result.deleted_target_ids)}",
                f"audit_payload_hash={result.audit_payload_hash}",
            )
        )
    )


__all__ = ["cleanup_agent_retention"]
