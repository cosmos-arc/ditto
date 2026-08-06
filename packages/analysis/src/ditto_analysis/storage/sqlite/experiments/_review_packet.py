"""
Review-packet read helpers composed by :class:`SQLiteExperimentReader`.

Kept in a leaf submodule so the reader stays under the file-size budget; the
reader delegates to these pure read functions, passing its bounded ``_one``
fetch helper so SQLite error wrapping stays in one place.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable

from ditto_analysis.experiments.models import ExperimentId

__all__ = ["fetch_experiment_id_by_spec_hash"]


def fetch_experiment_id_by_spec_hash(
    fetchone: Callable[[str, tuple[object, ...]], sqlite3.Row | None],
    spec_hash: str,
) -> ExperimentId | None:
    """
    Resolve the latest experiment owning a review packet for one spec hash.

    The spec hash is the content-addressed bridge from a governance review
    queue item to its experiment review packet. Multiple experiments may share
    a spec hash (re-runs); the ``EXISTS`` filter keeps only experiments that
    have a persisted review packet, and the recency ordering picks the latest.
    Returns ``None`` when no such experiment exists (no experiment, or the
    experiment has no review packet yet).
    """
    row = fetchone(
        """
        SELECT e.experiment_id
        FROM experiment e
        WHERE e.strategy_spec_hash = ?
          AND EXISTS (
            SELECT 1 FROM research_artifact a
            WHERE a.experiment_id = e.experiment_id
              AND a.artifact_kind = 'review_packet'
          )
        ORDER BY e.created_at_epoch_us DESC
        LIMIT 1
        """,
        (spec_hash,),
    )
    if row is None:
        return None
    return ExperimentId(str(row["experiment_id"]))
