"""#630 LIVE 门矩阵收集器单元测试：完成绑定与市场级范围规则."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from ditto_apps.scripts.data_live_gate import collect_live_gate_matrix

pytestmark = pytest.mark.unit

_DDL = (
    "CREATE TABLE trading_calendar ("
    "trade_date TEXT PRIMARY KEY, is_open INTEGER, exchange TEXT)",
    "CREATE TABLE ingestion_log ("
    "dataset TEXT, source TEXT, trade_date TEXT, status TEXT, checksum TEXT,"
    "rows INTEGER, error_code TEXT, error_message TEXT, attempts INTEGER,"
    "first_attempt_at TEXT, last_attempt_at TEXT)",
    "CREATE TABLE provider_snapshots ("
    "snapshot_id TEXT PRIMARY KEY, dataset_id TEXT, source TEXT,"
    "request_start TEXT, request_end TEXT, schema_version TEXT, checksum TEXT,"
    "response_metadata TEXT, row_count INTEGER, payload_retained INTEGER,"
    "created_at TEXT, canonical_namespace TEXT, canonical_dataset_id TEXT,"
    "canonical_partition_keys TEXT, request_parameters_hash TEXT)",
    "CREATE TABLE ingestion_partition_checkpoints ("
    "chunk_id TEXT, dataset_id TEXT, source TEXT, request_start TEXT,"
    "request_end TEXT, status TEXT, payload_id TEXT, complete_evidence_id TEXT,"
    "error_code TEXT, updated_at TEXT)",
)


def _seed(tmp_path: Path) -> Path:
    database = tmp_path / "metadata" / "metadata.sqlite"
    database.parent.mkdir()
    with sqlite3.connect(database) as connection:
        for statement in _DDL:
            connection.execute(statement)
        for day, is_open in (
            ("2026-10-30", 1),
            ("2026-10-31", 0),
            ("2026-11-02", 1),
        ):
            connection.execute(
                "INSERT INTO trading_calendar VALUES (?, ?, 'SSE')", (day, is_open)
            )
        connection.execute(
            "INSERT INTO ingestion_log VALUES ("
            "'stock_daily', 'tushare', '2026-10-30', 'SUCCESS', 'c1', 5000,"
            "NULL, NULL, 1, 't0', 't1')"
        )
        connection.execute(
            "INSERT INTO ingestion_log VALUES ("
            "'index_daily', 'tushare', '2026-11-02', 'FAIL', NULL, NULL,"
            "'FETCH_ERROR', 'partial day rejected', 4, 't0', 't1')"
        )
        # ① 完成且市场级、有行 → attested。
        connection.execute(
            "INSERT INTO provider_snapshots VALUES ("
            "'snap-ok', 'stock_daily', 'tushare', '2026-10-30', '2026-10-30',"
            "'v1', 'chk-ok', '{}', 5000, 1, 't0', NULL, NULL, NULL, NULL)"
        )
        connection.execute(
            "INSERT INTO ingestion_partition_checkpoints VALUES ("
            "'chunk-ok', 'stock_daily', 'tushare', '2026-10-30', '2026-10-30',"
            "'COMPLETE', 'payload:chk-ok:stock_daily/2026:snap-ok', 'snap-ok',"
            "NULL, 't1')"
        )
        # ② 完成但零行（正常无事件）→ covered_empty。
        connection.execute(
            "INSERT INTO provider_snapshots VALUES ("
            "'snap-empty', 'fund_portfolio', 'tushare', '2026-10-30',"
            "'2026-10-30', 'v1', 'chk-empty', '{}', 0, 1, 't0', NULL, NULL,"
            "NULL, NULL)"
        )
        connection.execute(
            "INSERT INTO ingestion_partition_checkpoints VALUES ("
            "'chunk-empty', 'fund_portfolio', 'tushare', '2026-10-30',"
            "'2026-10-30', 'COMPLETE',"
            "'payload:chk-empty:fund_portfolio/2026:snap-empty', 'snap-empty',"
            "NULL, 't1')"
        )
        # ③ 分区仍 PLANNED → 不算完成证据。
        connection.execute(
            "INSERT INTO provider_snapshots VALUES ("
            "'snap-pending', 'index_daily', 'tushare', '2026-11-02',"
            "'2026-11-02', 'v1', 'chk-pending', '{}', 178, 1, 't0', NULL, NULL,"
            "NULL, NULL)"
        )
        connection.execute(
            "INSERT INTO ingestion_partition_checkpoints VALUES ("
            "'chunk-pending', 'index_daily', 'tushare', '2026-11-02',"
            "'2026-11-02', 'PLANNED', NULL, NULL, NULL, 't1')"
        )
        # ④ 单标的范围请求不能证明全市场 → 排除。
        connection.execute(
            "INSERT INTO provider_snapshots VALUES ("
            "'snap-ticker', 'stock_daily', 'tushare', '2026-11-02',"
            "'2026-11-02', 'v1', 'chk-t',"
            "'{\"source_ticker\": \"000001.SZ\"}', 1, 1, 't0', NULL, NULL,"
            "NULL, NULL)"
        )
        connection.execute(
            "INSERT INTO ingestion_partition_checkpoints VALUES ("
            "'chunk-ticker', 'stock_daily', 'tushare', '2026-11-02',"
            "'2026-11-02', 'COMPLETE', 'payload:chk-t:x:snap-ticker',"
            "'snap-ticker', NULL, 't1')"
        )
        # ⑤ 完成证据绑定错位（evidence_id ≠ snapshot_id）→ 排除。
        connection.execute(
            "INSERT INTO provider_snapshots VALUES ("
            "'snap-mismatch', 'etf_daily', 'tushare', '2026-11-02',"
            "'2026-11-02', 'v1', 'chk-m', '{}', 2000, 1, 't0', NULL, NULL,"
            "NULL, NULL)"
        )
        connection.execute(
            "INSERT INTO ingestion_partition_checkpoints VALUES ("
            "'chunk-mismatch', 'etf_daily', 'tushare', '2026-11-02',"
            "'2026-11-02', 'COMPLETE', 'payload:chk-m:x:snap-other',"
            "'snap-other', NULL, 't1')"
        )
    return database


def test_matrix_assessment_rules(tmp_path: Path) -> None:
    database = _seed(tmp_path)
    matrix = collect_live_gate_matrix(
        database=database, start="2026-10-30", end="2026-11-02"
    )
    # 非交易日不出现在窗口里。
    assert matrix["window"]["days"] == ["2026-10-30", "2026-11-02"]

    stock = matrix["datasets"]["stock_daily"]
    assert stock["days"]["2026-10-30"]["assessment"] == "attested"
    assert stock["days"]["2026-10-30"]["max_covering_rows"] == 5000
    assert stock["days"]["2026-10-30"]["log"]["status"] == "SUCCESS"
    # 单标的请求不能证明全市场覆盖。
    assert stock["days"]["2026-11-02"]["assessment"] == "uncovered"
    assert stock["days"]["2026-11-02"]["covering_completed_snapshots"] == 0

    fund = matrix["datasets"]["fund_portfolio"]
    assert fund["days"]["2026-10-30"]["assessment"] == "covered_empty"
    assert fund["days"]["2026-10-30"]["max_covering_rows"] == 0

    index = matrix["datasets"]["index_daily"]
    assert index["days"]["2026-11-02"]["assessment"] == "uncovered"
    assert index["days"]["2026-11-02"]["log"]["error_code"] == "FETCH_ERROR"

    etf = matrix["datasets"]["etf_daily"]
    assert etf["days"]["2026-11-02"]["assessment"] == "uncovered"


def test_dataset_scope_includes_snapshot_only_datasets(tmp_path: Path) -> None:
    database = _seed(tmp_path)
    matrix = collect_live_gate_matrix(
        database=database, start="2026-10-30", end="2026-11-02"
    )
    # fund_portfolio 只有快照证据、无日志行，也进入矩阵。
    assert "fund_portfolio" in matrix["datasets"]
    assert matrix["datasets"]["fund_portfolio"]["days"]["2026-10-30"]["log"] is None


def test_registry_metadata_attached(tmp_path: Path) -> None:
    database = _seed(tmp_path)
    matrix = collect_live_gate_matrix(
        database=database, start="2026-10-30", end="2026-11-02"
    )
    stock = matrix["datasets"]["stock_daily"]
    assert stock["domain"] == "market"
    assert stock["schedule"] == "trading_days"


def test_window_without_open_days_rejected(tmp_path: Path) -> None:
    database = _seed(tmp_path)
    with pytest.raises(ValueError, match="no open trading days"):
        collect_live_gate_matrix(
            database=database, start="2026-11-08", end="2026-11-09"
        )
