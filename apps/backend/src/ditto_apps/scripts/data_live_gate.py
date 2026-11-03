"""
#630 LIVE 建议门：从 catalog 账本提取交易日窗口的逐数据集证据矩阵.

只读工具。对给定交易日窗口，从 catalog（``ingestion_log`` 三阶段日志与
分区完成证据）逐数据集逐日提取两类事实：

1. 当日摄取日志行（逐源全量：status/rows/error/attempts）；
2. 覆盖该日的已完成市场级供应商快照（数量、行数与最晚完成时刻——
   补偿时点核对用，SLA 时限裁量归验收记录）。

完成判定 SQL 精确镜像
``ditto_data.catalog.snapshot_completion.snapshot_completed``
（COMPLETE 状态 + ``payload:{checksum}:…:{snapshot_id}`` 绑定 +
``complete_evidence_id`` 一致）与 ``completed_snapshot_index`` 的市场级
范围规则（response_metadata 不含 source_ticker/exchange）；若上游规则
演进，须同步本 SQL。输出仅含事实与机械分类
（attested/covered_empty/uncovered），窗口裁量与受限项归类归
docs/data 验收记录，不在本脚本内宣称通过。

用法::

    python -m ditto_apps.scripts.data_live_gate \
        --database <state_root>/metadata/metadata.sqlite \
        --start 2026-10-26 --end 2026-10-30 [--output matrix.json]
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import orjson
from ditto_data.catalog import default_dataset_metadata

__all__ = ["collect_live_gate_matrix", "main"]

_SCHEMA = "ditto.live-gate-matrix.v1"

_DAYS_QUERY = (
    "SELECT trade_date FROM trading_calendar "
    "WHERE exchange = 'SSE' AND is_open = 1 AND trade_date BETWEEN ? AND ? "
    "ORDER BY trade_date"
)

_LOG_QUERY = (
    "SELECT source, status, rows, error_code, error_message, attempts, "
    "last_attempt_at FROM ingestion_log "
    "WHERE dataset = ? AND trade_date = ? ORDER BY source"
)

# 覆盖该日的已完成市场级快照（完成绑定规则同 snapshot_completion.py）。
_COVERING_QUERY = """
SELECT s.row_count, s.snapshot_id, c.updated_at
FROM provider_snapshots s
JOIN ingestion_partition_checkpoints c
  ON c.dataset_id = s.dataset_id AND c.source = s.source
 AND c.request_start = s.request_start AND c.request_end = s.request_end
 AND c.status = 'COMPLETE'
 AND c.complete_evidence_id = s.snapshot_id
 AND c.payload_id LIKE 'payload:' || s.checksum || ':%'
 AND c.payload_id LIKE '%:' || s.snapshot_id
WHERE s.dataset_id = :dataset AND :day BETWEEN s.request_start AND s.request_end
  AND json_extract(s.response_metadata, '$.source_ticker') IS NULL
  AND json_extract(s.response_metadata, '$.exchange') IS NULL
ORDER BY c.updated_at
"""

_DATASET_QUERY = (
    "SELECT DISTINCT dataset FROM ingestion_log WHERE trade_date BETWEEN ? AND ? "
    "UNION "
    "SELECT DISTINCT dataset_id FROM provider_snapshots "
    "WHERE request_end >= ? AND request_start <= ? "
    "ORDER BY 1"
)


def collect_live_gate_matrix(
    *,
    database: Path,
    start: str,
    end: str,
) -> dict[str, Any]:
    """读取账本并返回窗口内逐数据集×逐日证据矩阵（纯只读）."""
    if not database.is_file():
        raise FileNotFoundError(f"catalog database not found: {database}")
    database = database.absolute()
    connection = sqlite3.connect(f"{database.as_uri()}?mode=ro", uri=True)
    try:
        days = [row[0] for row in connection.execute(_DAYS_QUERY, (start, end))]
        if not days:
            raise ValueError(f"no open trading days between {start} and {end}")
        datasets = [
            row[0]
            for row in connection.execute(_DATASET_QUERY, (start, end, start, end))
        ]
        registry = default_dataset_metadata()
        matrix: dict[str, Any] = {}
        for dataset in datasets:
            metadata = registry.get(dataset)
            day_facts: dict[str, Any] = {}
            for day in days:
                log_rows = connection.execute(_LOG_QUERY, (dataset, day)).fetchall()
                covering = connection.execute(
                    _COVERING_QUERY, {"dataset": dataset, "day": day}
                ).fetchall()
                max_rows = max((row[0] for row in covering), default=None)
                if covering and max_rows:
                    assessment = "attested"
                elif covering:
                    assessment = "covered_empty"
                else:
                    assessment = "uncovered"
                day_facts[day] = {
                    # ingestion_log 主键含 source（如 stock_daily 双源）；逐源
                    # 全量列出，不挑任意一条冒充该日日志事实。
                    "logs": [
                        {
                            "source": row[0],
                            "status": row[1],
                            "rows": row[2],
                            "error_code": row[3],
                            "error_message": row[4],
                            "attempts": row[5],
                            "last_attempt_at": row[6],
                        }
                        for row in log_rows
                    ],
                    "covering_completed_snapshots": len(covering),
                    "max_covering_rows": max_rows,
                    "latest_snapshot_id": covering[-1][1] if covering else None,
                    "latest_completed_at": covering[-1][2] if covering else None,
                    "assessment": assessment,
                }
            matrix[dataset] = {
                "domain": metadata.domain if metadata else None,
                "schedule": metadata.schedule if metadata else None,
                "sla_hours": (metadata.freshness_sla_hours if metadata else None),
                "days": day_facts,
            }
        return {
            "schema": _SCHEMA,
            "generated_at": datetime.now(UTC).isoformat(),
            "database": str(database),
            "window": {"start": start, "end": end, "days": days},
            "datasets": matrix,
        }
    finally:
        connection.close()


def main(argv: list[str] | None = None) -> int:
    """输出窗口证据矩阵 JSON；窗口与合格裁量归验收记录."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database",
        type=Path,
        required=True,
        help="catalog 库路径 <state_root>/metadata/metadata.sqlite",
    )
    parser.add_argument("--start", required=True, help="窗口起始日 YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="窗口结束日 YYYY-MM-DD")
    parser.add_argument("--output", type=Path, help="可选 JSON 落档路径")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    try:
        matrix = collect_live_gate_matrix(
            database=args.database, start=args.start, end=args.end
        )
    except (FileNotFoundError, ValueError, sqlite3.Error) as exc:
        sys.stderr.write(f"FAIL: {exc}\n")
        return 2
    payload = orjson.dumps(matrix, option=orjson.OPT_INDENT_2)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(payload)
    sys.stdout.write(payload.decode() + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
