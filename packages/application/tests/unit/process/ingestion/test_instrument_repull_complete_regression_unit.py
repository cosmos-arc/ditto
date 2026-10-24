"""#602 instrument 范围重拉跨 COMPLETE 分区回归测试.

复刻 instrument_ingestion 的完整证据序列（prepare_payload_write intent →
committer.commit），锁定重拉跨 COMPLETE 分区时必走幂等快径或独立
revision 落证，不得 PARTITION_LIFECYCLE_FAILED。快照身份按 R2 契约为
确定性派生（created_at/元数据不进 id），intent 与 commit 阶段对同一
(checksum, 区间) 解析到同一 revision。
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from ditto_application.processes.ingestion.evidence_commit import (
    EvidenceCommitPorts,
    EvidenceCommitRequest,
    IngestionEvidenceCommitter,
    PartitionWriteIntent,
)
from ditto_data.catalog import DataAssetRef, DataCatalogEntry, DataSchemaFingerprint
from ditto_data.catalog.provider_payload import ProviderPayloadArtifact
from ditto_data.catalog.source_snapshot import (
    ProviderSnapshot,
    ProviderSnapshotDraft,
    snapshot_identity,
)
from ditto_data.catalog.source_snapshot_store import SQLiteProviderSnapshotStore
from ditto_data.ingestion.partition_state import PartitionLifecycleStatus
from ditto_data.ingestion.partition_state_store import SQLitePartitionLifecycleStore
from ditto_data.models.ingestion import IngestionLog, IngestionStatus
from ditto_platform.foundation import SQLiteClient, SQLitePool

_CHUNK_ID = "chunk:tushare:index_weight:2022:2022-01-04:2022-12-30:instrument:3009282"
_START = "2022-01-04"
_END = "2022-12-30"
_SCHEMA_VERSION = "market.index_weight.v1"


class _Recorder:
    """In-memory durable ports recorder."""

    def __init__(self) -> None:
        self.values: list[Any] = []

    def append_snapshot(self, value: object) -> None:
        self.values.append(value)

    def upsert_asset(self, value: object) -> None:
        self.values.append(value)

    def save_log(self, value: object) -> object:
        self.values.append(value)
        return value

    def get_log(
        self, dataset: str, source: str, trade_date: str
    ) -> IngestionLog | None:
        return next(
            (
                v
                for v in self.values
                if isinstance(v, IngestionLog)
                and (v.dataset, v.source, v.trade_date) == (dataset, source, trade_date)
            ),
            None,
        )

    def get_snapshot(self, snapshot_id: str) -> ProviderSnapshot | None:
        return next(
            (
                v
                for v in self.values
                if isinstance(v, ProviderSnapshot) and v.snapshot_id == snapshot_id
            ),
            None,
        )

    def list_snapshots(self, **_: Any) -> tuple[ProviderSnapshot, ...]:
        return tuple(v for v in self.values if isinstance(v, ProviderSnapshot))


def _request(
    payload_checksum: str, canonical_checksum: str = "sha256:canonical-v1"
) -> EvidenceCommitRequest:
    """同 chunk 同区间的重拉载荷请求（载荷 checksum 与 canonical 输出独立给定）."""
    now = datetime(2026, 10, 25, 1, 0, tzinfo=UTC)
    canonical_asset = DataAssetRef(dataset_id="index_weight", namespace="capital")
    snapshot = ProviderSnapshot.create(
        ProviderSnapshotDraft(
            dataset_id="index_weight",
            source="tushare",
            request_start=_START,
            request_end=_END,
            schema_version=_SCHEMA_VERSION,
            checksum=payload_checksum,
            canonical_asset=canonical_asset,
            request_parameters_hash="sha256:request",
            response_metadata=(
                ("snapshot_layer", "normalized_provider_payload"),
                ("source_ticker", "000300.SH"),
            ),
            row_count=12,
            payload_uri=(
                f"provider_payloads/tushare/index_weight/{payload_checksum}.parquet"
            ),
            payload_retained=True,
            created_at=now,
        )
    )
    catalog_entry = DataCatalogEntry(
        asset=canonical_asset,
        storage_uri="capital/index_weight/2022.parquet",
        schema=DataSchemaFingerprint(
            schema_hash="schema:sha256:index-weight",
            row_count=12,
            created_at=now,
            schema_version=_SCHEMA_VERSION,
            columns=("instrument_id", "index_id", "trade_date"),
        ),
        source="tushare",
        freshness_at=now,
        source_snapshot_id=snapshot.snapshot_id,
    )
    return EvidenceCommitRequest(
        chunk_id=_CHUNK_ID,
        dataset_id="index_weight",
        source="tushare",
        request_start=_START,
        request_end=_END,
        ingestion_date=_START,
        provider_snapshot=snapshot,
        catalog_entry=catalog_entry,
        success_log=IngestionLog(
            dataset="index_weight",
            source="tushare",
            trade_date=_START,
            status=IngestionStatus.SUCCESS,
            checksum=canonical_checksum,
            rows=12,
        ),
    )


def _artifact(checksum: str) -> ProviderPayloadArtifact:
    return ProviderPayloadArtifact(
        dataset_id="index_weight",
        source="tushare",
        checksum=checksum,
        row_count=12,
        uri=f"provider_payloads/tushare/index_weight/{checksum}.parquet",
    )


def _prepare_repull_intent(
    committer: IngestionEvidenceCommitter, payload_checksum: str
) -> None:
    """复刻 post_ingest.prepare_payload_write 的 intent 阶段（含确定性快照身份）."""
    committer.prepare_payload_write(
        PartitionWriteIntent(
            chunk_id=_CHUNK_ID,
            request_start=_START,
            request_end=_END,
            payload=_artifact(payload_checksum),
            snapshot_id=snapshot_identity(
                "index_weight",
                "tushare",
                _START,
                _END,
                _SCHEMA_VERSION,
                payload_checksum,
            ),
        )
    )


def _committer(
    tmp_path: Path,
) -> tuple[IngestionEvidenceCommitter, SQLitePartitionLifecycleStore, SQLitePool]:
    pool = SQLitePool(str(tmp_path / "runtime.sqlite"))
    lifecycle = SQLitePartitionLifecycleStore(SQLiteClient(pool))
    recorder = _Recorder()
    committer = IngestionEvidenceCommitter(
        ports=EvidenceCommitPorts(
            lifecycle_reader=lifecycle,
            lifecycle_writer=lifecycle,
            snapshot_writer=recorder,
            snapshot_reader=recorder,
            catalog_writer=recorder,
            ingestion_log_store=recorder,
        ),
        now=lambda: datetime(2026, 10, 25, 1, 0, tzinfo=UTC),
    )
    return committer, lifecycle, pool


@pytest.mark.unit
def test_repull_same_payload_over_complete_attests_idempotently(
    tmp_path: Path,
) -> None:
    """同载荷重拉跨 COMPLETE：幂等快径落证，不产生失败态."""
    committer, lifecycle, pool = _committer(tmp_path)
    try:
        base = _request("a" * 32)
        assert committer.commit(base).completed

        _prepare_repull_intent(committer, "a" * 32)
        outcome = committer.commit(base)

        assert outcome.completed is True
        assert outcome.error_code is None
        checkpoint = lifecycle.get_checkpoint(_CHUNK_ID)
        assert checkpoint is not None
        assert checkpoint.status is PartitionLifecycleStatus.COMPLETE
        assert checkpoint.error_code is None
        assert checkpoint.complete_evidence_id == base.provider_snapshot.snapshot_id
        assert not lifecycle.list_incomplete()
    finally:
        pool.close()


@pytest.mark.unit
def test_repull_revised_payload_over_complete_forks_revision(
    tmp_path: Path,
) -> None:
    """异载荷重拉跨 COMPLETE：独立 revision 完整落证，基线分区不动摇."""
    committer, lifecycle, pool = _committer(tmp_path)
    try:
        assert committer.commit(_request("a" * 32)).completed

        revised = _request("b" * 32)
        _prepare_repull_intent(committer, "b" * 32)
        outcome = committer.commit(revised)

        assert outcome.completed is True
        assert outcome.error_code is None
        assert outcome.chunk_id.startswith(f"{_CHUNK_ID}:revision:")
        base = lifecycle.get_checkpoint(_CHUNK_ID)
        assert base is not None
        assert base.status is PartitionLifecycleStatus.COMPLETE
        assert base.complete_evidence_id is not None
        assert not lifecycle.list_incomplete()
        for row in lifecycle.list_complete(dataset_id="index_weight"):
            assert row.error_code is None
    finally:
        pool.close()


@pytest.mark.unit
def test_repull_sequence_never_emits_partition_lifecycle_failed(
    tmp_path: Path,
) -> None:
    """intent→commit 全序列重放（含失败残留重试形）不得出现失败态收尾.

    #602 现象是 R2 证据提交以 PARTITION_LIFECYCLE_FAILED 收尾——此处把
    重拉序列在 COMPLETE 基线上重放两轮，任何一轮出现该错误码即为回归。
    """
    committer, lifecycle, pool = _committer(tmp_path)
    try:
        assert committer.commit(_request("a" * 32)).completed
        for checksum in ("a" * 32, "b" * 32, "b" * 32):
            _prepare_repull_intent(committer, checksum)
            outcome = committer.commit(_request(checksum))
            assert outcome.completed is True
            assert outcome.error_code != "PARTITION_LIFECYCLE_FAILED"
        assert not lifecycle.list_incomplete()
    finally:
        pool.close()


@pytest.mark.unit
def test_repull_same_payload_with_canonical_drift_reattests_over_real_store(
    tmp_path: Path,
) -> None:
    """#602 根因形：同载荷重拉但 canonical 富化漂移（别名注册/settle 改变
    富化输出）→ commit 注入的 canonical_checksum 异于存量快照 → 真快照
    端口同 id 异内容冲突。期望幂等落证（快照不可变、漂移由 success log
    承载），不得 PARTITION_LIFECYCLE_FAILED。
    """
    pool = SQLitePool(str(tmp_path / "runtime.sqlite"))
    client = SQLiteClient(pool)
    lifecycle = SQLitePartitionLifecycleStore(client)
    snapshot_store = SQLiteProviderSnapshotStore(client)
    recorder = _Recorder()
    committer = IngestionEvidenceCommitter(
        ports=EvidenceCommitPorts(
            lifecycle_reader=lifecycle,
            lifecycle_writer=lifecycle,
            snapshot_writer=snapshot_store,
            snapshot_reader=snapshot_store,
            catalog_writer=recorder,
            ingestion_log_store=recorder,
        ),
        now=lambda: datetime(2026, 10, 25, 1, 0, tzinfo=UTC),
    )
    try:
        assert committer.commit(_request("a" * 32)).completed

        drifted = _request("a" * 32, canonical_checksum="sha256:canonical-v2")
        _prepare_repull_intent(committer, "a" * 32)
        outcome = committer.commit(drifted)

        assert outcome.completed is True
        assert outcome.error_code is None
        checkpoint = lifecycle.get_checkpoint(_CHUNK_ID)
        assert checkpoint is not None
        assert checkpoint.status is PartitionLifecycleStatus.COMPLETE
        assert checkpoint.error_code is None
    finally:
        pool.close()
