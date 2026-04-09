"""T1 任务工厂别名."""

from __future__ import annotations

from ditto_interfaces.jobs.tasks.t0_meta import create_ingest_task

__all__ = [
    "create_ingest_task_t1_adj",
    "create_ingest_task_t1_bars",
]

create_ingest_task_t1_adj = create_ingest_task
create_ingest_task_t1_bars = create_ingest_task
