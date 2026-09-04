"""Formal paper end-of-day recovery and reconciliation job."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from ditto_application.commands.paper_session import (
    PaperSessionCommandHandler,
    ReconcilePaperSessionCommand,
)
from ditto_application.processes.execution.operate_paper_session import (
    OperatePaperSession,
)
from ditto_platform.foundation import Metrics, SafeCounter

__all__ = ["PaperEodJob", "PaperEodResult"]


@dataclass(frozen=True, kw_only=True)
class PaperEodResult:
    """EOD recovery count and balanced checksum."""

    recovered_execution_count: int
    reconciliation_checksum: str


class PaperEodJob:
    """Recover ledger gaps before producing fail-closed EOD evidence."""

    def __init__(
        self,
        *,
        operator: OperatePaperSession,
        command_handler: PaperSessionCommandHandler,
    ) -> None:
        self._operator = operator
        self._command_handler = command_handler

    def run(self, *, session_id: str, idempotency_key: str) -> PaperEodResult:
        """Recover, reconcile, and reject unbalanced end-of-day state."""
        try:
            recovered = self._operator.recover(session_id)
            reconciliation = self._command_handler.reconcile(
                ReconcilePaperSessionCommand(
                    session_id=session_id,
                    idempotency_key=idempotency_key,
                )
            )
        except Exception:
            _paper_eod_counter().add(1, attributes={"status": "failed"})
            raise
        if not reconciliation.balanced:
            _paper_eod_counter().add(1, attributes={"status": "unbalanced"})
            raise RuntimeError(
                f"paper EOD reconciliation is unbalanced: {reconciliation.checksum}"
            )
        _paper_eod_counter().add(1, attributes={"status": "completed"})
        return PaperEodResult(
            recovered_execution_count=len(recovered),
            reconciliation_checksum=reconciliation.checksum,
        )


def _paper_eod_counter() -> SafeCounter:
    return cast(
        SafeCounter,
        getattr(Metrics, "workstation_paper_eod", SafeCounter()),
    )
