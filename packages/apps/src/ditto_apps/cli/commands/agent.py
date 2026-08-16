"""Governed Agent CLI over the shared transport-neutral runtime."""

from __future__ import annotations

import time
from collections.abc import Generator
from contextlib import contextmanager
from decimal import Decimal
from typing import Annotated, Never

import orjson
import typer
from ditto_agent.contracts.runtime import ModelProfile, RetentionClass, RunStatus
from ditto_agent.runtime.service import (
    AgentApprovalDecision,
    AgentApprovalDecisionCommand,
    AgentEventView,
    AgentInvalidRequest,
    AgentRequestConflict,
    AgentResourceNotFound,
    AgentRunCancelCommand,
    AgentRunCreateCommand,
    AgentRuntimeError,
    AgentRuntimePort,
    AgentRuntimeUnavailable,
    AgentRunView,
    AgentSessionCreateCommand,
    AgentSessionView,
    ApprovalDecisionKind,
)

from ditto_apps.registry.container import make_app_container

app = typer.Typer(
    help="治理型量化研究 Agent (experimental, 默认关闭)",
    no_args_is_help=True,
)

_TERMINAL_RUN_STATUSES = frozenset(
    {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED}
)


def _json_bytes(payload: object, *, pretty: bool) -> bytes:
    options = orjson.OPT_SORT_KEYS | orjson.OPT_UTC_Z
    if pretty:
        options |= orjson.OPT_INDENT_2
    return orjson.dumps(payload, option=options)


def _emit_json(payload: object, *, err: bool = False, pretty: bool = True) -> None:
    typer.echo(_json_bytes(payload, pretty=pretty).decode(), err=err)


def _runtime_exit_code(exc: AgentRuntimeError) -> int:
    if isinstance(exc, AgentRuntimeUnavailable):
        return 3
    if isinstance(exc, AgentResourceNotFound):
        return 4
    if isinstance(exc, AgentRequestConflict):
        return 5
    if isinstance(exc, AgentInvalidRequest):
        return 2
    return 1


def _exit_runtime_error(exc: AgentRuntimeError, *, json_output: bool) -> Never:
    code = exc.reason_code.upper()
    if json_output:
        _emit_json(
            {"error": {"code": code, "message": str(exc)}},
            err=True,
        )
    else:
        typer.echo(f"{code}: {exc}", err=True)
    raise typer.Exit(_runtime_exit_code(exc))


def _exit_invalid_request(*, json_output: bool) -> Never:
    error = AgentInvalidRequest(
        "Agent CLI request is invalid",
        reason_code="agent_request_invalid",
    )
    _exit_runtime_error(error, json_output=json_output)


@contextmanager
def _agent_runtime(*, json_output: bool) -> Generator[AgentRuntimePort]:
    try:
        container = make_app_container()
    except Exception:
        error = AgentRuntimeUnavailable("agent_runtime_resolution_failed")
        _exit_runtime_error(error, json_output=json_output)
    try:
        try:
            runtime = container.get(AgentRuntimePort)
        except Exception:
            error = AgentRuntimeUnavailable("agent_runtime_resolution_failed")
            _exit_runtime_error(error, json_output=json_output)
        try:
            yield runtime
        except AgentRuntimeError as exc:
            _exit_runtime_error(exc, json_output=json_output)
        except ValueError:
            _exit_invalid_request(json_output=json_output)
    finally:
        container.close()


def _session_payload(session: AgentSessionView) -> dict[str, object]:
    return {
        "session_id": session.session_id,
        "created_at": session.created_at.isoformat(),
        "retention_class": session.retention_class.value,
    }


def _run_payload(run: AgentRunView) -> dict[str, object]:
    return {
        "run_id": run.run_id,
        "session_id": run.session_id,
        "status": run.status.value,
        "objective_hash": run.objective_hash,
        "authority_hash": run.authority_hash,
        "max_model_tokens": run.max_model_tokens,
        "max_model_spend_usd": str(run.max_model_spend_usd),
        "model_profile": run.model_profile.value,
        "manifest_hash": run.manifest_hash,
        "created_at": run.created_at.isoformat(),
        "started_at": None if run.started_at is None else run.started_at.isoformat(),
        "finished_at": (
            None if run.finished_at is None else run.finished_at.isoformat()
        ),
        "revision": run.revision,
    }


def _event_payload(event: AgentEventView) -> dict[str, object]:
    return {
        "schema_version": event.schema_version,
        "event_id": event.event_id,
        "run_id": event.run_id,
        "run_sequence": event.run_sequence,
        "event_type": event.event_type,
        "payload_hash": event.payload_hash,
        "occurred_at": event.occurred_at.isoformat(),
        "prev_hash": event.prev_hash,
        "event_hash": event.event_hash,
    }


def _approval_payload(decision: AgentApprovalDecision) -> dict[str, object]:
    return {
        "approval_id": decision.approval_id,
        "run_id": decision.run_id,
        "action_hash": decision.action_hash,
        "status": decision.status.value,
        "operator_id": decision.operator_id,
        "reason": decision.reason,
        "decided_at": decision.decided_at.isoformat(),
    }


def _parse_spend_budget(value: str) -> Decimal:
    try:
        budget = Decimal(value)
    except ArithmeticError as exc:
        raise ValueError("max_model_spend_usd must be a decimal") from exc
    if not budget.is_finite() or budget < 0:
        raise ValueError("max_model_spend_usd must be finite and non-negative")
    return budget


def _emit_run(run: AgentRunView, *, json_output: bool) -> None:
    if json_output:
        _emit_json(_run_payload(run))
        return
    typer.echo(f"run_id={run.run_id} status={run.status.value} revision={run.revision}")


def _emit_event(
    event: AgentEventView,
    *,
    json_output: bool,
    streaming: bool,
) -> None:
    if json_output:
        _emit_json(_event_payload(event), pretty=not streaming)
        return
    typer.echo(
        " ".join(
            (
                f"event_id={event.event_id}",
                f"sequence={event.run_sequence}",
                f"type={event.event_type}",
                f"payload_hash={event.payload_hash}",
            )
        )
    )


@app.command("run")
def run_agent(
    objective: Annotated[str, typer.Argument(help="研究目标 (不会写入持久化)")],
    authority_hash: Annotated[
        str,
        typer.Option(help="服务端已确认 authority 的 SHA-256"),
    ],
    idempotency_key: Annotated[
        str,
        typer.Option(help="本次 session/run 的稳定幂等键"),
    ],
    max_model_tokens: Annotated[
        int,
        typer.Option(min=1, help="模型 token 硬预算"),
    ] = 4096,
    max_model_spend_usd: Annotated[
        str,
        typer.Option(help="模型费用美元硬预算 (exact decimal)"),
    ] = "0.25",
    model_profile: Annotated[
        ModelProfile,
        typer.Option(help="受版本清单约束的模型 profile"),
    ] = ModelProfile.BALANCED,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="输出稳定 JSON"),
    ] = False,
) -> None:
    """创建一个本地 session，并在同一 runtime 中提交只读 Agent run。"""
    with _agent_runtime(json_output=json_output) as runtime:
        spend_budget = _parse_spend_budget(max_model_spend_usd)
        session = runtime.create_session(
            AgentSessionCreateCommand(
                retention_class=RetentionClass.STANDARD,
                idempotency_key=f"{idempotency_key}:session",
            )
        )
        run = runtime.create_run(
            AgentRunCreateCommand(
                session_id=session.session_id,
                objective=objective,
                authority_hash=authority_hash,
                max_model_tokens=max_model_tokens,
                max_model_spend_usd=spend_budget,
                model_profile=model_profile,
                idempotency_key=f"{idempotency_key}:run",
            )
        )
    if json_output:
        _emit_json({"run": _run_payload(run), "session": _session_payload(session)})
        return
    typer.echo(
        " ".join(
            (
                f"session_id={session.session_id}",
                f"run_id={run.run_id}",
                f"status={run.status.value}",
                f"revision={run.revision}",
            )
        )
    )


@app.command("show")
def show_agent_run(
    run_id: Annotated[str, typer.Argument(help="Agent run ID")],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="输出稳定 JSON"),
    ] = False,
) -> None:
    """读取一个不含原始目标或 provider state 的 run projection。"""
    with _agent_runtime(json_output=json_output) as runtime:
        run = runtime.get_run(run_id)
    _emit_run(run, json_output=json_output)


@app.command("events")
def show_agent_events(
    run_id: Annotated[str, typer.Argument(help="Agent run ID")],
    after_event_id: Annotated[
        int | None,
        typer.Option(min=0, help="仅读取此持久 event_id 之后的事件"),
    ] = None,
    follow: Annotated[
        bool,
        typer.Option("--follow", help="持续轮询持久事件直到 run terminal"),
    ] = False,
    poll_interval: Annotated[
        float,
        typer.Option(min=0.0, help="follow 模式轮询间隔 (秒)"),
    ] = 1.0,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="输出 JSON; follow 模式为 NDJSON"),
    ] = False,
) -> None:
    """重放持久事件；follow 不创建 session、run 或工具调用。"""
    cursor = after_event_id
    with _agent_runtime(json_output=json_output) as runtime:
        if not follow:
            events = runtime.list_run_events(run_id, after_event_id=cursor)
            if json_output:
                _emit_json(
                    {
                        "events": [_event_payload(event) for event in events],
                        "next_event_id": (
                            cursor if not events else events[-1].event_id
                        ),
                    }
                )
            else:
                for event in events:
                    _emit_event(event, json_output=False, streaming=False)
            return

        try:
            while True:
                events = runtime.list_run_events(run_id, after_event_id=cursor)
                for event in events:
                    _emit_event(event, json_output=json_output, streaming=True)
                    cursor = event.event_id
                run = runtime.get_run(run_id)
                if run.status in _TERMINAL_RUN_STATUSES:
                    return
                time.sleep(poll_interval)
        except KeyboardInterrupt as exc:
            raise typer.Exit(130) from exc


@app.command("cancel")
def cancel_agent_run(
    run_id: Annotated[str, typer.Argument(help="Agent run ID")],
    expected_revision: Annotated[
        int,
        typer.Option(min=0, help="当前 run projection revision"),
    ],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="输出稳定 JSON"),
    ] = False,
) -> None:
    """以 revision fence 取消 queued/running Agent run。"""
    with _agent_runtime(json_output=json_output) as runtime:
        run = runtime.cancel_run(
            AgentRunCancelCommand(
                run_id=run_id,
                expected_revision=expected_revision,
            )
        )
    _emit_run(run, json_output=json_output)


def _decide_approval(
    *,
    approval_id: str,
    expected_action_hash: str,
    operator_id: str,
    reason: str | None,
    decision: ApprovalDecisionKind,
    json_output: bool,
) -> None:
    with _agent_runtime(json_output=json_output) as runtime:
        receipt = runtime.decide_approval(
            AgentApprovalDecisionCommand(
                approval_id=approval_id,
                expected_action_hash=expected_action_hash,
                decision=decision,
                operator_id=operator_id,
                reason=reason,
            )
        )
    if json_output:
        _emit_json(_approval_payload(receipt))
        return
    typer.echo(
        " ".join(
            (
                f"approval_id={receipt.approval_id}",
                f"status={receipt.status.value}",
                f"run_id={receipt.run_id}",
            )
        )
    )


@app.command("approve")
def approve_agent_action(
    approval_id: Annotated[str, typer.Argument(help="Approval request ID")],
    expected_action_hash: Annotated[
        str,
        typer.Option(help="待批准 immutable action 的 SHA-256"),
    ],
    operator_id: Annotated[str, typer.Option(help="操作者审计 identity")],
    reason: Annotated[
        str | None,
        typer.Option(help="审批理由"),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="输出稳定 JSON"),
    ] = False,
) -> None:
    """批准一个与 exact action hash 绑定的 Agent action。"""
    _decide_approval(
        approval_id=approval_id,
        expected_action_hash=expected_action_hash,
        operator_id=operator_id,
        reason=reason,
        decision=ApprovalDecisionKind.APPROVE,
        json_output=json_output,
    )


@app.command("reject")
def reject_agent_action(
    approval_id: Annotated[str, typer.Argument(help="Approval request ID")],
    expected_action_hash: Annotated[
        str,
        typer.Option(help="待拒绝 immutable action 的 SHA-256"),
    ],
    operator_id: Annotated[str, typer.Option(help="操作者审计 identity")],
    reason: Annotated[
        str | None,
        typer.Option(help="拒绝理由"),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="输出稳定 JSON"),
    ] = False,
) -> None:
    """拒绝一个与 exact action hash 绑定的 Agent action。"""
    _decide_approval(
        approval_id=approval_id,
        expected_action_hash=expected_action_hash,
        operator_id=operator_id,
        reason=reason,
        decision=ApprovalDecisionKind.REJECT,
        json_output=json_output,
    )


__all__ = ["app"]
