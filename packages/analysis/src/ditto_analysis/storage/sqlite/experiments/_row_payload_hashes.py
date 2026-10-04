"""
Row → canonical payload-hash builders for experiment child sets.

#448 起 enqueue fence 机器删除；这两个纯函数是 holdout preflight 权威
绑定的承重件（行内容 ↔ 冻结权威事件的反泄漏比对），保留于此。
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import date
from typing import cast

from ditto_analysis.errors import (
    AnalysisError,
    ExperimentIntegrityError,
)
from ditto_analysis.experiments.enqueue_fence import (
    FoldPersistenceFence,
    GateEvaluationFence,
)
from ditto_analysis.experiments.models import (
    CandidateId,
    ContentHash,
    ExperimentId,
    FoldId,
)
from ditto_analysis.experiments.persistence import (
    DateWindow,
    FoldKey,
    FoldPersistenceSpec,
    FoldRole,
    canonical_payload,
)

__all__ = [
    "fold_fence_from_row",
    "gate_fence_from_row",
]


def _integrity(
    message: str, reason_code: str, **details: object
) -> ExperimentIntegrityError:
    return ExperimentIntegrityError(
        message,
        details={"reason_code": reason_code, **details},
    )


def _json_object(value: object, field_name: str) -> dict[str, object]:
    if type(value) is not str:
        raise _integrity(
            "gate fence source JSON is not text",
            "gate_payload_invalid",
            field=field_name,
        )
    try:
        decoded = cast("object", json.loads(value))
    except json.JSONDecodeError as exc:
        raise _integrity(
            "gate fence source JSON is invalid",
            "gate_payload_invalid",
            field=field_name,
        ) from exc
    if type(decoded) is not dict:
        raise _integrity(
            "gate fence source JSON is not an object",
            "gate_payload_invalid",
            field=field_name,
        )
    return cast("dict[str, object]", decoded)


def gate_fence_from_row(row: sqlite3.Row) -> GateEvaluationFence:
    try:
        payload_hash = canonical_payload(
            {
                "evaluation_id": row["evaluation_id"],
                "experiment_id": row["experiment_id"],
                "candidate_id": row["candidate_id"],
                "fold_id": row["fold_id"],
                "attempt_id": row["attempt_id"],
                "rule_id": row["rule_id"],
                "policy_version": row["policy_version"],
                "layer": row["layer"],
                "outcome": row["outcome"],
                "observed": _json_object(row["observed_json"], "observed_json"),
                "policy": _json_object(row["policy_json"], "policy_json"),
                "artifact_id": row["artifact_id"],
                "evaluated_at_epoch_us": row["evaluated_at_epoch_us"],
            }
        ).content_hash
        fence = GateEvaluationFence(row["evaluation_id"], payload_hash)
    except ExperimentIntegrityError:
        raise
    except (AnalysisError, OverflowError, TypeError, UnicodeError, ValueError) as exc:
        raise _integrity(
            "gate row cannot be reconstructed",
            "gate_payload_invalid",
            evaluation_id=row["evaluation_id"],
        ) from exc
    if str(payload_hash) != row["payload_hash"]:
        raise _integrity(
            "gate evaluation payload hash mismatch",
            "gate_payload_hash_mismatch",
            evaluation_id=row["evaluation_id"],
        )
    return fence


def fold_fence_from_row(row: sqlite3.Row) -> FoldPersistenceFence:
    raw_payload = row["fold_spec_json"]
    if type(raw_payload) is not str:
        raise _integrity(
            "fold canonical payload is not text",
            "fold_payload_invalid",
            fold_id=row["fold_id"],
        )
    try:
        payload = raw_payload.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise _integrity(
            "fold canonical payload is not UTF-8 encodable",
            "fold_payload_invalid",
            fold_id=row["fold_id"],
        ) from exc
    actual_hash = hashlib.sha256(payload).hexdigest()
    if actual_hash != row["fold_spec_hash"]:
        raise _integrity(
            "fold canonical payload hash mismatch",
            "fold_payload_hash_mismatch",
            fold_id=row["fold_id"],
        )
    try:
        key = FoldKey(
            ExperimentId(row["experiment_id"]),
            CandidateId(row["candidate_id"]),
            FoldId(row["fold_id"]),
        )
        train_window = (
            None
            if row["train_start"] is None
            else DateWindow(
                date.fromisoformat(row["train_start"]),
                date.fromisoformat(row["train_end"]),
            )
        )
        expected = FoldPersistenceSpec.create(
            key=key,
            ordinal=row["ordinal"],
            fold_role=FoldRole(row["fold_role"]),
            train_window=train_window,
            test_window=DateWindow(
                date.fromisoformat(row["test_start"]),
                date.fromisoformat(row["test_end"]),
            ),
            purge_sessions=row["purge_sessions"],
            embargo_sessions=row["embargo_sessions"],
        )
        fence = FoldPersistenceFence(key, ContentHash(actual_hash))
    except (AnalysisError, TypeError, ValueError) as exc:
        raise _integrity(
            "fold row cannot be reconstructed",
            "fold_payload_invalid",
            fold_id=row["fold_id"],
        ) from exc
    if expected.canonical_payload != payload:
        raise _integrity(
            "fold payload disagrees with its relational fields",
            "fold_relation_payload_mismatch",
            fold_id=row["fold_id"],
        )
    return fence
