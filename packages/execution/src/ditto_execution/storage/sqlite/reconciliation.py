"""SQLite storage for reconciliation repair workflow state."""

from __future__ import annotations

from typing import Any, Literal

from ditto_platform.foundation import SQLiteClient

from ditto_execution.reconciliation.types import (
    MismatchType,
    RepairActionRecord,
    RepairActionStatus,
    RepairActionType,
    RepairPlan,
)

__all__ = ["REPAIR_WORKFLOW_DDL", "SQLiteRepairWorkflowStore"]

_PRIORITIES: tuple[Literal["low", "medium", "high"], ...] = (
    "low",
    "medium",
    "high",
)

_CREATE_REPAIR_ACTIONS_TABLE = """
CREATE TABLE IF NOT EXISTS reconciliation_repair_actions (
    action_id              TEXT PRIMARY KEY,
    report_id              TEXT    NOT NULL,
    account_id             TEXT    NOT NULL,
    trade_date             TEXT    NOT NULL,
    action_index           INTEGER NOT NULL,
    action_type            TEXT    NOT NULL,
    mismatch_type          TEXT    NOT NULL,
    status                 TEXT    NOT NULL,
    order_id               TEXT    NOT NULL,
    fill_id                TEXT,
    client_order_id        TEXT,
    broker_order_id        TEXT,
    priority               TEXT    NOT NULL,
    requires_manual_review INTEGER NOT NULL,
    reason                 TEXT    NOT NULL,
    reviewer               TEXT,
    review_reason          TEXT,
    reviewed_at            TEXT,
    executor               TEXT,
    claimed_at             TEXT,
    execution_result       TEXT,
    executed_at            TEXT,
    created_at             TEXT    NOT NULL,
    UNIQUE(report_id, action_index)
);
"""

_CREATE_IDX_REPAIR_ACTIONS_REPORT = (
    "CREATE INDEX IF NOT EXISTS idx_reconciliation_repair_actions_report "
    "ON reconciliation_repair_actions(report_id, action_index);"
)

_CREATE_IDX_REPAIR_ACTIONS_STATUS = (
    "CREATE INDEX IF NOT EXISTS idx_reconciliation_repair_actions_status "
    "ON reconciliation_repair_actions(status, trade_date);"
)

_CREATE_IDX_REPAIR_ACTIONS_FILL_MUTATION_CLAIM = (
    "CREATE INDEX IF NOT EXISTS idx_reconciliation_repair_actions_fill_mutation_claim "
    "ON reconciliation_repair_actions("
    "action_type, status, account_id, trade_date, fill_id"
    ");"
)

REPAIR_WORKFLOW_DDL = (
    _CREATE_REPAIR_ACTIONS_TABLE
    + _CREATE_IDX_REPAIR_ACTIONS_REPORT
    + _CREATE_IDX_REPAIR_ACTIONS_STATUS
    + _CREATE_IDX_REPAIR_ACTIONS_FILL_MUTATION_CLAIM
)

_INSERT_REPAIR_ACTION = """
INSERT OR IGNORE INTO reconciliation_repair_actions
    (action_id, report_id, account_id, trade_date, action_index,
     action_type, mismatch_type, status, order_id, fill_id, client_order_id,
     broker_order_id, priority, requires_manual_review, reason, created_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_SELECT_ACTION_BY_ID = """
SELECT * FROM reconciliation_repair_actions WHERE action_id = ?
"""

_LIST_ACTIONS_BY_REPORT = """
SELECT * FROM reconciliation_repair_actions
WHERE report_id = ?
ORDER BY action_index ASC
"""

_APPROVE_ACTION = """
UPDATE reconciliation_repair_actions
SET status = ?, reviewer = ?, review_reason = ?, reviewed_at = ?
WHERE action_id = ? AND status = ?
"""

_REJECT_ACTION = """
UPDATE reconciliation_repair_actions
SET status = ?, reviewer = ?, review_reason = ?, reviewed_at = ?
WHERE action_id = ? AND status = ?
"""

_CLAIM_FOR_EXECUTION = """
UPDATE reconciliation_repair_actions
SET status = ?, executor = ?, claimed_at = ?, execution_result = NULL,
    executed_at = NULL
WHERE action_id = ? AND status IN (?, ?)
  AND (
    action_type NOT IN (?, ?)
    OR fill_id IS NULL
    OR NOT EXISTS (
      SELECT 1
      FROM reconciliation_repair_actions AS competing
      WHERE competing.action_id <> ?
        AND competing.status = ?
        AND competing.action_type IN (?, ?)
        AND competing.account_id = (
          SELECT target.account_id
          FROM reconciliation_repair_actions AS target
          WHERE target.action_id = ?
        )
        AND competing.trade_date = (
          SELECT target.trade_date
          FROM reconciliation_repair_actions AS target
          WHERE target.action_id = ?
        )
        AND competing.fill_id = (
          SELECT target.fill_id
          FROM reconciliation_repair_actions AS target
          WHERE target.action_id = ?
        )
    )
  )
"""

_CLAIM_FOR_EXECUTION_OR_RECLAIM_STALE = """
UPDATE reconciliation_repair_actions
SET status = ?, executor = ?, claimed_at = ?, execution_result = NULL,
    executed_at = NULL
WHERE action_id = ?
  AND (
    status IN (?, ?)
    OR (
      status = ?
      AND (claimed_at IS NULL OR claimed_at = '' OR claimed_at < ?)
    )
  )
  AND (
    action_type NOT IN (?, ?)
    OR fill_id IS NULL
    OR NOT EXISTS (
      SELECT 1
      FROM reconciliation_repair_actions AS competing
      WHERE competing.action_id <> ?
        AND competing.status = ?
        AND competing.action_type IN (?, ?)
        AND competing.account_id = (
          SELECT target.account_id
          FROM reconciliation_repair_actions AS target
          WHERE target.action_id = ?
        )
        AND competing.trade_date = (
          SELECT target.trade_date
          FROM reconciliation_repair_actions AS target
          WHERE target.action_id = ?
        )
        AND competing.fill_id = (
          SELECT target.fill_id
          FROM reconciliation_repair_actions AS target
          WHERE target.action_id = ?
        )
    )
  )
"""

_RELEASE_STALE_COMPETING_FILL_MUTATION_CLAIMS = """
UPDATE reconciliation_repair_actions
SET status = CASE WHEN requires_manual_review = 1 THEN ? ELSE ? END,
    executor = NULL,
    claimed_at = NULL
WHERE action_id <> ?
  AND status = ?
  AND action_type IN (?, ?)
  AND (claimed_at IS NULL OR claimed_at = '' OR claimed_at < ?)
  AND EXISTS (
    SELECT 1
    FROM reconciliation_repair_actions AS target
    WHERE target.action_id = ?
      AND target.action_type IN (?, ?)
      AND target.fill_id IS NOT NULL
      AND target.account_id = reconciliation_repair_actions.account_id
      AND target.trade_date = reconciliation_repair_actions.trade_date
      AND target.fill_id = reconciliation_repair_actions.fill_id
      AND (
        target.status IN (?, ?)
        OR (
          target.status = ?
          AND (
            target.claimed_at IS NULL
            OR target.claimed_at = ''
            OR target.claimed_at < ?
          )
        )
      )
  )
"""

_RELEASE_EXECUTION_CLAIM = """
UPDATE reconciliation_repair_actions
SET status = CASE WHEN requires_manual_review = 1 THEN ? ELSE ? END,
    executor = NULL,
    claimed_at = NULL
WHERE action_id = ? AND status = ? AND executor = ?
"""

_MARK_EXECUTED = """
UPDATE reconciliation_repair_actions
SET status = ?, executor = ?, execution_result = ?, executed_at = ?
WHERE action_id = ?
  AND status = ?
  AND executor = ?
"""


class SQLiteRepairWorkflowStore:
    """Persist repair action review and execution state."""

    def __init__(self, client: SQLiteClient) -> None:
        self._client = client

    def init_schema(self) -> None:
        """Initialize reconciliation repair workflow tables."""
        self._client.executescript(REPAIR_WORKFLOW_DDL)
        self._ensure_claimed_at_column()
        self._client.commit()

    def save_plan(
        self, plan: RepairPlan, *, created_at: str = ""
    ) -> tuple[RepairActionRecord, ...]:
        """Persist one row per planned action without overwriting review state."""
        for index, action in enumerate(plan.actions):
            status = (
                RepairActionStatus.PENDING_REVIEW
                if action.requires_manual_review
                else RepairActionStatus.READY
            )
            self._client.execute(
                _INSERT_REPAIR_ACTION,
                (
                    _action_id(plan.report_id, index),
                    plan.report_id,
                    plan.account_id,
                    plan.trade_date,
                    index,
                    action.action_type.value,
                    action.mismatch_type.value,
                    status.value,
                    action.order_id,
                    action.fill_id,
                    action.client_order_id,
                    action.broker_order_id,
                    action.priority,
                    int(action.requires_manual_review),
                    action.reason,
                    created_at,
                ),
            )
        self._client.commit()
        return self.list_actions(plan.report_id)

    def get_action(self, action_id: str) -> RepairActionRecord | None:
        """Return one persisted repair action."""
        row = self._client.fetchone(_SELECT_ACTION_BY_ID, (action_id,))
        return _row_to_record(row) if row else None

    def list_actions(self, report_id: str) -> tuple[RepairActionRecord, ...]:
        """Return persisted repair actions for a report in plan order."""
        rows = self._client.fetchall(_LIST_ACTIONS_BY_REPORT, (report_id,))
        return tuple(_row_to_record(row) for row in rows)

    def approve_action(
        self,
        action_id: str,
        *,
        reviewer: str,
        reason: str,
        reviewed_at: str = "",
    ) -> bool:
        """Move a manual action from pending review to approved."""
        cursor = self._client.execute(
            _APPROVE_ACTION,
            (
                RepairActionStatus.APPROVED.value,
                reviewer,
                reason,
                reviewed_at,
                action_id,
                RepairActionStatus.PENDING_REVIEW.value,
            ),
        )
        self._client.commit()
        return cursor.rowcount > 0

    def reject_action(
        self,
        action_id: str,
        *,
        reviewer: str,
        reason: str,
        reviewed_at: str = "",
    ) -> bool:
        """Reject a pending manual action."""
        cursor = self._client.execute(
            _REJECT_ACTION,
            (
                RepairActionStatus.REJECTED.value,
                reviewer,
                reason,
                reviewed_at,
                action_id,
                RepairActionStatus.PENDING_REVIEW.value,
            ),
        )
        self._client.commit()
        return cursor.rowcount > 0

    def claim_for_execution(
        self,
        action_id: str,
        *,
        executor: str,
        claimed_at: str = "",
        reclaim_before: str | None = None,
    ) -> RepairActionRecord | None:
        """Atomically move a claimable action into execution."""
        if reclaim_before is None:
            cursor = self._client.execute(
                _CLAIM_FOR_EXECUTION,
                (
                    RepairActionStatus.EXECUTING.value,
                    executor,
                    claimed_at,
                    action_id,
                    RepairActionStatus.READY.value,
                    RepairActionStatus.APPROVED.value,
                    RepairActionType.IMPORT_BROKER_FILL.value,
                    RepairActionType.AMEND_LOCAL_FILL.value,
                    action_id,
                    RepairActionStatus.EXECUTING.value,
                    RepairActionType.IMPORT_BROKER_FILL.value,
                    RepairActionType.AMEND_LOCAL_FILL.value,
                    action_id,
                    action_id,
                    action_id,
                ),
            )
        else:
            self._release_stale_competing_fill_mutation_claims(
                action_id,
                reclaim_before=reclaim_before,
            )
            cursor = self._client.execute(
                _CLAIM_FOR_EXECUTION_OR_RECLAIM_STALE,
                (
                    RepairActionStatus.EXECUTING.value,
                    executor,
                    claimed_at,
                    action_id,
                    RepairActionStatus.READY.value,
                    RepairActionStatus.APPROVED.value,
                    RepairActionStatus.EXECUTING.value,
                    reclaim_before,
                    RepairActionType.IMPORT_BROKER_FILL.value,
                    RepairActionType.AMEND_LOCAL_FILL.value,
                    action_id,
                    RepairActionStatus.EXECUTING.value,
                    RepairActionType.IMPORT_BROKER_FILL.value,
                    RepairActionType.AMEND_LOCAL_FILL.value,
                    action_id,
                    action_id,
                    action_id,
                ),
            )
        self._client.commit()
        if cursor.rowcount == 0:
            return None
        return self.get_action(action_id)

    def _release_stale_competing_fill_mutation_claims(
        self,
        action_id: str,
        *,
        reclaim_before: str,
    ) -> None:
        self._client.execute(
            _RELEASE_STALE_COMPETING_FILL_MUTATION_CLAIMS,
            (
                RepairActionStatus.APPROVED.value,
                RepairActionStatus.READY.value,
                action_id,
                RepairActionStatus.EXECUTING.value,
                RepairActionType.IMPORT_BROKER_FILL.value,
                RepairActionType.AMEND_LOCAL_FILL.value,
                reclaim_before,
                action_id,
                RepairActionType.IMPORT_BROKER_FILL.value,
                RepairActionType.AMEND_LOCAL_FILL.value,
                RepairActionStatus.READY.value,
                RepairActionStatus.APPROVED.value,
                RepairActionStatus.EXECUTING.value,
                reclaim_before,
            ),
        )

    def release_execution_claim(
        self,
        action_id: str,
        *,
        executor: str,
    ) -> bool:
        """Release an in-flight execution claim back to its retriable state."""
        cursor = self._client.execute(
            _RELEASE_EXECUTION_CLAIM,
            (
                RepairActionStatus.APPROVED.value,
                RepairActionStatus.READY.value,
                action_id,
                RepairActionStatus.EXECUTING.value,
                executor,
            ),
        )
        self._client.commit()
        return cursor.rowcount > 0

    def _ensure_claimed_at_column(self) -> None:
        columns = {
            str(row["name"])
            for row in self._client.fetchall(
                "PRAGMA table_info(reconciliation_repair_actions)"
            )
        }
        if "claimed_at" not in columns:
            self._client.execute(
                "ALTER TABLE reconciliation_repair_actions ADD COLUMN claimed_at TEXT"
            )

    def mark_executed(
        self,
        action_id: str,
        *,
        executor: str,
        result: str,
        executed_at: str = "",
    ) -> bool:
        """Record execution result for an executor-owned in-flight action."""
        cursor = self._client.execute(
            _MARK_EXECUTED,
            (
                RepairActionStatus.EXECUTED.value,
                executor,
                result,
                executed_at,
                action_id,
                RepairActionStatus.EXECUTING.value,
                executor,
            ),
        )
        self._client.commit()
        return cursor.rowcount > 0


def _action_id(report_id: str, action_index: int) -> str:
    return f"{report_id}:{action_index:04d}"


def _row_to_record(row: dict[str, Any]) -> RepairActionRecord:
    return RepairActionRecord(
        action_id=str(row["action_id"]),
        report_id=str(row["report_id"]),
        account_id=str(row["account_id"]),
        trade_date=str(row["trade_date"]),
        action_index=int(row["action_index"]),
        action_type=RepairActionType(str(row["action_type"])),
        mismatch_type=MismatchType(str(row["mismatch_type"])),
        status=RepairActionStatus(str(row["status"])),
        order_id=str(row["order_id"]),
        fill_id=_optional_text(row["fill_id"]),
        client_order_id=_optional_text(row["client_order_id"]),
        broker_order_id=_optional_text(row["broker_order_id"]),
        priority=_priority(row["priority"]),
        requires_manual_review=bool(row["requires_manual_review"]),
        reason=str(row["reason"]),
        reviewer=_optional_text(row["reviewer"]),
        review_reason=_optional_text(row["review_reason"]),
        reviewed_at=_optional_text(row["reviewed_at"]),
        executor=_optional_text(row["executor"]),
        claimed_at=_optional_text(row.get("claimed_at")),
        execution_result=_optional_text(row["execution_result"]),
        executed_at=_optional_text(row["executed_at"]),
        created_at=str(row["created_at"]),
    )


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _priority(value: object) -> Literal["low", "medium", "high"]:
    text = str(value)
    if text not in _PRIORITIES:
        raise ValueError(f"unknown repair action priority: {text!r}")
    return text
