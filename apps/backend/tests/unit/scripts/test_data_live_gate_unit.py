"""#630 LIVE 门矩阵收集器单元测试：完成绑定与市场级范围规则."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import orjson
import pytest
from ditto_apps.scripts.data_live_gate import collect_live_gate_matrix
from ditto_data.catalog.contracts import DataAssetRef
from ditto_data.catalog.snapshot_completion import snapshot_completed
from ditto_data.catalog.source_snapshot import ProviderSnapshot
from ditto_data.ingestion.partition_state import (
    PartitionCheckpoint,
    PartitionLifecycleEvent,
    PartitionLifecycleStatus,
)

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

_DAYS = ("2026-10-30", "2026-11-02")


class _Seed:
    """一枚种子快照及其 checkpoint 绑定（五类完成形态）."""

    def __init__(
        self,
        snapshot_id: str,
        dataset: str,
        request_start: str,
        request_end: str,
        checksum: str,
        response_metadata: str,
        row_count: int,
        *,
        completed: bool,
        evidence_mismatch: bool = False,
    ) -> None:
        self.snapshot_id = snapshot_id
        self.dataset = dataset
        self.request_start = request_start
        self.request_end = request_end
        self.checksum = checksum
        self.response_metadata = response_metadata
        self.row_count = row_count
        self.completed = completed
        if not completed:
            self.payload_id: str | None = None
            self.evidence_id: str | None = None
        elif evidence_mismatch:
            self.payload_id = f"payload:{checksum}:x:snap-other"
            self.evidence_id = "snap-other"
        else:
            self.payload_id = f"payload:{checksum}:{dataset}/2026:{snapshot_id}"
            self.evidence_id = snapshot_id


_SEEDS: tuple[_Seed, ...] = (
    # ① 完成且市场级、有行 → attested。
    _Seed(
        "snap-ok",
        "stock_daily",
        "2026-10-30",
        "2026-10-30",
        "chk-ok",
        "{}",
        5000,
        completed=True,
    ),
    # ② 完成但零行（正常无事件）→ covered_empty。
    _Seed(
        "snap-empty",
        "fund_portfolio",
        "2026-10-30",
        "2026-10-30",
        "chk-empty",
        "{}",
        0,
        completed=True,
    ),
    # ③ 分区仍 PLANNED → 不算完成证据。
    _Seed(
        "snap-pending",
        "index_daily",
        "2026-11-02",
        "2026-11-02",
        "chk-pending",
        "{}",
        178,
        completed=False,
    ),
    # ④ 单标的范围请求不能证明全市场 → 排除。
    _Seed(
        "snap-ticker",
        "stock_daily",
        "2026-11-02",
        "2026-11-02",
        "chk-t",
        '{"source_ticker": "000001.SZ"}',
        1,
        completed=True,
    ),
    # ⑤ 完成证据绑定错位（evidence_id ≠ snapshot_id）→ 排除。
    _Seed(
        "snap-mismatch",
        "etf_daily",
        "2026-11-02",
        "2026-11-02",
        "chk-m",
        "{}",
        2000,
        completed=True,
        evidence_mismatch=True,
    ),
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
        # 双源数据集：fuyao 辅源同日也有日志行，矩阵须逐源全量透出。
        connection.execute(
            "INSERT INTO ingestion_log VALUES ("
            "'stock_daily', 'fuyao', '2026-10-30', 'SUCCESS', 'c2', 4998,"
            "NULL, NULL, 1, 't0', 't1')"
        )
        connection.execute(
            "INSERT INTO ingestion_log VALUES ("
            "'index_daily', 'tushare', '2026-11-02', 'FAIL', NULL, NULL,"
            "'FETCH_ERROR', 'partial day rejected', 4, 't0', 't1')"
        )
        for seed in _SEEDS:
            connection.execute(
                "INSERT INTO provider_snapshots VALUES ("
                "?, ?, 'tushare', ?, ?, 'v1', ?, ?, ?, 1, 't0', NULL, NULL,"
                "NULL, NULL)",
                (
                    seed.snapshot_id,
                    seed.dataset,
                    seed.request_start,
                    seed.request_end,
                    seed.checksum,
                    seed.response_metadata,
                    seed.row_count,
                ),
            )
            status = "PLANNED" if seed.payload_id is None else "COMPLETE"
            connection.execute(
                "INSERT INTO ingestion_partition_checkpoints VALUES ("
                "?, ?, 'tushare', ?, ?, ?, ?, ?, NULL, 't1')",
                (
                    f"chunk-{seed.snapshot_id}",
                    seed.dataset,
                    seed.request_start,
                    seed.request_end,
                    status,
                    seed.payload_id,
                    seed.evidence_id,
                ),
            )
    return database


def test_matrix_assessment_rules(tmp_path: Path) -> None:
    database = _seed(tmp_path)
    matrix = collect_live_gate_matrix(
        database=database, start="2026-10-30", end="2026-11-02"
    )
    # 非交易日不出现在窗口里。
    assert matrix["window"]["days"] == list(_DAYS)

    stock = matrix["datasets"]["stock_daily"]
    assert stock["days"]["2026-10-30"]["assessment"] == "attested"
    assert stock["days"]["2026-10-30"]["max_covering_rows"] == 5000
    # 双源日志逐源全量透出，不挑任意一条。
    logs = stock["days"]["2026-10-30"]["logs"]
    assert [entry["source"] for entry in logs] == ["fuyao", "tushare"]
    assert all(entry["status"] == "SUCCESS" for entry in logs)
    # 单标的请求不能证明全市场覆盖。
    assert stock["days"]["2026-11-02"]["assessment"] == "uncovered"
    assert stock["days"]["2026-11-02"]["covering_completed_snapshots"] == 0

    fund = matrix["datasets"]["fund_portfolio"]
    assert fund["days"]["2026-10-30"]["assessment"] == "covered_empty"
    assert fund["days"]["2026-10-30"]["max_covering_rows"] == 0
    # 完成时刻透出，补偿时点核对用。
    assert fund["days"]["2026-10-30"]["latest_completed_at"] == "t1"

    index = matrix["datasets"]["index_daily"]
    assert index["days"]["2026-11-02"]["assessment"] == "uncovered"
    tushare_log = next(
        entry
        for entry in index["days"]["2026-11-02"]["logs"]
        if entry["source"] == "tushare"
    )
    assert tushare_log["error_code"] == "FETCH_ERROR"

    etf = matrix["datasets"]["etf_daily"]
    assert etf["days"]["2026-11-02"]["assessment"] == "uncovered"


def test_dataset_scope_includes_snapshot_only_datasets(tmp_path: Path) -> None:
    database = _seed(tmp_path)
    matrix = collect_live_gate_matrix(
        database=database, start="2026-10-30", end="2026-11-02"
    )
    # fund_portfolio 只有快照证据、无日志行，也进入矩阵。
    assert "fund_portfolio" in matrix["datasets"]
    assert matrix["datasets"]["fund_portfolio"]["days"]["2026-10-30"]["logs"] == []


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


class _SeededLifecycle:
    """把种子 checkpoints 适配成完成规则的消费端口（Protocol 鸭子型）."""

    def __init__(self, seeds: tuple[_Seed, ...]) -> None:
        self._seeds = seeds

    def _checkpoint(self, seed: _Seed) -> PartitionCheckpoint:
        return PartitionCheckpoint(
            chunk_id=f"chunk-{seed.snapshot_id}",
            dataset_id=seed.dataset,
            source="tushare",
            request_start=seed.request_start,
            request_end=seed.request_end,
            status=(
                PartitionLifecycleStatus.COMPLETE
                if seed.payload_id is not None
                else PartitionLifecycleStatus.PLANNED
            ),
            payload_id=seed.payload_id,
            complete_evidence_id=seed.evidence_id,
            error_code=None,
            updated_at=datetime(2026, 11, 2, tzinfo=UTC),
        )

    def get_latest_checkpoint(self, chunk_id: str) -> PartitionCheckpoint | None:
        return self.get_checkpoint(chunk_id)

    def get_checkpoint(self, chunk_id: str) -> PartitionCheckpoint | None:
        return next(
            (
                self._checkpoint(seed)
                for seed in self._seeds
                if f"chunk-{seed.snapshot_id}" == chunk_id
            ),
            None,
        )

    def list_incomplete(
        self, *, dataset_id: str | None = None, source: str | None = None
    ) -> tuple[PartitionCheckpoint, ...]:
        return self._filtered(
            include_complete=False, dataset_id=dataset_id, source=source
        )

    def list_complete(
        self, *, dataset_id: str | None = None, source: str | None = None
    ) -> tuple[PartitionCheckpoint, ...]:
        return self._filtered(
            include_complete=True, dataset_id=dataset_id, source=source
        )

    def list_events(self, chunk_id: str) -> tuple[PartitionLifecycleEvent, ...]:
        return ()

    def _filtered(
        self, *, include_complete: bool, dataset_id: str | None, source: str | None
    ) -> tuple[PartitionCheckpoint, ...]:
        return tuple(
            self._checkpoint(seed)
            for seed in self._seeds
            if seed.dataset == (dataset_id or seed.dataset)
            and (source is None or source == "tushare")
            and (seed.payload_id is not None) == include_complete
        )


def _python_snapshot(seed: _Seed) -> ProviderSnapshot:
    metadata = tuple(sorted(orjson.loads(seed.response_metadata).items()))
    return ProviderSnapshot(
        snapshot_id=seed.snapshot_id,
        dataset_id=seed.dataset,
        source="tushare",
        request_start=seed.request_start,
        request_end=seed.request_end,
        schema_version="v1",
        checksum=seed.checksum,
        canonical_asset=DataAssetRef(dataset_id=seed.dataset, namespace="data"),
        request_parameters_hash="sha256:seed",
        response_metadata=metadata,
        row_count=seed.row_count,
        payload_uri="payload://seed",
        payload_retained=True,
        created_at=datetime(2026, 10, 30, tzinfo=UTC),
    )


def test_sql_completion_rule_matches_python_rule(tmp_path: Path) -> None:
    """脚本 SQL 完成判定与 snapshot_completed 真源逐格一致（防漂移守卫）.

    期望值＝Σ（snapshot_completed 真源判定完成 ∧ 市场级范围 ∧ 请求窗覆盖
    该日）。市场级过滤（response_metadata 无 source_ticker/exchange）与
    ``completed_snapshot_index`` 同式，此处两行复刻并留注释锚定。
    """
    database = _seed(tmp_path)
    matrix = collect_live_gate_matrix(
        database=database, start="2026-10-30", end="2026-11-02"
    )
    lifecycle = _SeededLifecycle(_SEEDS)
    for dataset in sorted({seed.dataset for seed in _SEEDS}):
        for day in _DAYS:
            expected = sum(
                1
                for seed in _SEEDS
                if seed.dataset == dataset
                and seed.request_start <= day <= seed.request_end
                and snapshot_completed(_python_snapshot(seed), lifecycle)
                # 市场级规则同 completed_snapshot_index._market_wide：
                # 单标的/单交易所请求不能证明全市场。
                and not dict(orjson.loads(seed.response_metadata)).keys()
                & {"source_ticker", "exchange"}
            )
            day_facts = matrix["datasets"][dataset]["days"][day]
            assert day_facts["covering_completed_snapshots"] == expected, (
                dataset,
                day,
            )
