"""SQLite persistence for immutable Research Case handoffs."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import orjson
import pytest
from ditto_analysis.errors import ResearchCaseIntegrityError
from ditto_analysis.research.cases import ResearchCase
from ditto_analysis.storage.sqlite.research.case_store import (
    SQLiteResearchCaseStore,
)
from ditto_kernel.identity import InstrumentId
from ditto_platform.foundation import SQLiteClient, SQLitePool

_AS_OF = datetime(2026, 11, 10, 7, 0, tzinfo=UTC)
_HASH_A = "a" * 64
_HASH_B = "b" * 64
_HASH_C = "c" * 64


def _case(**overrides: object) -> ResearchCase:
    baseline = ResearchCase(
        selection_run_id=f"selection-run:sha256:{_HASH_A}",
        selection_run_hash=_HASH_A,
        selection_input_hash=_HASH_B,
        selection_spec_hash=_HASH_C,
        objective="验证筛选动量候选的持续性",
        asset_kind="stock",
        as_of=_AS_OF,
        knowledge_cutoff=_AS_OF,
        publication_cutoff=_AS_OF,
        universe_snapshot_id="universe:sha256:abc",
        industry_rotation_snapshot_id="industry-rotation:sha256:def",
        source_snapshot_ids=("source-b", "source-a"),
        candidate_instrument_ids=(InstrumentId(600001), InstrumentId(600002)),
        selection_status="ready",
        missing_inputs=(),
    )
    return replace(baseline, **overrides)


@pytest.fixture
def store(tmp_path: Path) -> SQLiteResearchCaseStore:
    pool = SQLitePool(tmp_path / "metadata.sqlite")
    client = SQLiteClient(pool)
    value = SQLiteResearchCaseStore(client)
    value.init_schema()
    yield value
    pool.close_all()


def test_saved_case_round_trips_through_exact_content_identity(
    store: SQLiteResearchCaseStore,
) -> None:
    case = _case()

    store.save(case)

    restored = store.get(case.case_id)
    assert restored is not None
    assert restored == case


def test_replay_of_the_same_case_is_an_idempotent_no_op(
    store: SQLiteResearchCaseStore,
) -> None:
    case = _case()

    store.save(case)
    store.save(case)

    assert len(store.list_recent(limit=10)) == 1


def test_save_rejects_an_identity_that_owns_different_evidence(
    store: SQLiteResearchCaseStore,
) -> None:
    case = _case()
    store.save(case)
    # 直接篡改持久化载荷（模拟存储层缺陷/外部写入）：同 case_id 已属
    # 不同证据，重放必须 fail closed 而不是静默覆盖。
    other = _case(objective="被篡改的另一个研究目标")
    store._sqlite_client.execute(
        "UPDATE research_case SET payload_json = ? WHERE case_id = ?",
        (
            orjson.dumps(other.canonical_payload).decode(),
            case.case_id,
        ),
    )
    store._sqlite_client.commit()

    with pytest.raises(ResearchCaseIntegrityError):
        store.save(case)


def test_get_rejects_a_payload_that_does_not_rebuild_the_identity(
    store: SQLiteResearchCaseStore,
) -> None:
    case = _case()
    store.save(case)
    other = _case(objective="载荷被替换后的目标")
    store._sqlite_client.execute(
        "UPDATE research_case SET payload_json = ? WHERE case_id = ?",
        (
            orjson.dumps(other.canonical_payload).decode(),
            case.case_id,
        ),
    )
    store._sqlite_client.commit()

    with pytest.raises(ResearchCaseIntegrityError):
        store.get(case.case_id)


def test_get_of_an_unknown_case_returns_none(store: SQLiteResearchCaseStore) -> None:
    assert store.get("research-case:sha256:" + "f" * 64) is None


def test_list_recent_orders_by_decision_time_desc(
    store: SQLiteResearchCaseStore,
) -> None:
    older = _case(as_of=datetime(2026, 11, 9, 7, 0, tzinfo=UTC))
    newer = _case(
        as_of=datetime(2026, 11, 10, 7, 0, tzinfo=UTC),
        selection_run_id=f"selection-run:sha256:{_HASH_B}",
        selection_run_hash=_HASH_B,
    )

    store.save(older)
    store.save(newer)

    listed = store.list_recent(limit=10)
    assert [item.case_id for item in listed] == [newer.case_id, older.case_id]


def test_list_recent_applies_the_requested_limit(
    store: SQLiteResearchCaseStore,
) -> None:
    for index in range(3):
        store.save(
            _case(
                as_of=datetime(2026, 11, 9 + index, 7, 0, tzinfo=UTC),
                selection_run_id=f"selection-run:sha256:{_HASH_A}",
            )
        )

    assert len(store.list_recent(limit=2)) == 2


def test_list_by_run_filters_to_one_selection_run(
    store: SQLiteResearchCaseStore,
) -> None:
    run_a_case = _case()
    run_b_case = _case(
        selection_run_id=f"selection-run:sha256:{_HASH_B}",
        selection_run_hash=_HASH_B,
        objective="另一个运行的用例",
    )
    store.save(run_a_case)
    store.save(run_b_case)

    listed = store.list_by_run(run_a_case.selection_run_id, limit=10)

    assert [item.case_id for item in listed] == [run_a_case.case_id]
