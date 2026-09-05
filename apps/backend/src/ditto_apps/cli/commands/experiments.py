"""Experiment scheduler tick CLI (production composition root entrypoint)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

import typer

from ditto_apps.cli.utils.output import output_json_dict
from ditto_apps.jobs.flows.experiments import run_experiment_scheduler_tick

__all__ = ["app", "experiment_app_callback", "tick"]

app = typer.Typer(help="研究实验 scheduler tick 编排")


@app.callback()
def experiment_app_callback() -> None:
    """Experiment scheduler tick subcommand group (keeps ``tick`` a sub-command)."""


@app.command("tick")
def tick(
    occurred_at: Annotated[
        str,
        typer.Option(
            "--at",
            help=(
                "Tick occurrence time as an ISO 8601 UTC datetime "
                "(e.g. 2026-07-26T10:00:00+00:00). Defaults to now()."
            ),
        ),
    ] = "",
) -> None:
    """
    运行一次 experiment scheduler tick (claim fold -> run backtest -> record result).

    Reads all dispatchable experiments under the singleton scheduler lease and
    emits a structured progress-at-dispatch snapshot. Pass ``--at`` to pin the
    tick occurrence time; omit it to use the current UTC time.
    """
    ts = _parse_utc_datetime(occurred_at)
    result = run_experiment_scheduler_tick(occurred_at=ts)
    output_json_dict(result)


def _parse_utc_datetime(value: str) -> datetime:
    """
    Parse an ISO 8601 string into a timezone-aware UTC datetime.

    Defaults to ``datetime.now(UTC)`` when ``value`` is empty. Naive datetimes
    are rejected so the underlying flow's UTC invariant stays meaningful.
    """
    if not value:
        return datetime.now(UTC)
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise typer.BadParameter(
            f"--at must include UTC offset; got naive value '{value}'"
        )
    return parsed.astimezone(UTC)
