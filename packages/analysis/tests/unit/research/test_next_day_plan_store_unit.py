"""SQLite persistence and contracts for immutable next-day plans."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import replace
from datetime import UTC, date, datetime
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

import orjson
import pytest
from ditto_analysis.errors import NextDayPlanIntegrityError
from ditto_analysis.research.plans import NextDayPlan, PlanCandidateNote
from ditto_analysis.storage.sqlite.research.plan_store import SQLiteNextDayPlanStore
from ditto_kernel.identity import InstrumentId
from ditto_platform.foundation import SQLiteClient, SQLitePool

_CREATED = datetime(2026, 11, 10, 15, 5, tzinfo=UTC)


def _plan(**overrides: object) -> NextDayPlan:
    baseline = NextDayPlan(
        observation_date=date(2026, 11, 10),
        candidate_notes=(
            PlanCandidateNote(
                instrument_id=InstrumentId(600779), reason="白酒板块缩量回踩半年线"
            ),
            PlanCandidateNote(
                instrument_id=InstrumentId(510888), reason="宽基 ETF 跟随大盘缩量"
            ),
        ),
        next_day_plan="次日开盘观察 600779 是否放量收复 5 日线; 否则移出候选",
        created_at=_CREATED,
    )
    return replace(baseline, **overrides)


@pytest.fixture
def store(tmp_path: Path) -> Iterator[SQLiteNextDayPlanStore]:
    pool = SQLitePool(str(tmp_path / "metadata.sqlite"))
    client = SQLiteClient(pool)
    value = SQLiteNextDayPlanStore(client)
    value.init_schema()
    yield value
    pool.close_all()


def test_plan_is_content_addressed_and_idempotent_on_replay(
    store: SQLiteNextDayPlanStore,
) -> None:
    plan = _plan()

    store.save(plan)
    store.save(plan)

    restored = store.get(plan.plan_id)
    assert restored is not None
    assert restored == plan
    assert restored.plan_id.startswith("next-day-plan:sha256:")
    assert len(store.list_recent(limit=10)) == 1


def test_revisions_are_separate_immutable_entries(
    store: SQLiteNextDayPlanStore,
) -> None:
    first = _plan()
    revised = _plan(
        next_day_plan="改为观察 510888 的净值折溢价再决定",
        created_at=datetime(2026, 11, 10, 15, 40, tzinfo=UTC),
    )

    store.save(first)
    store.save(revised)

    assert first.plan_id != revised.plan_id
    listed = store.list_recent(limit=10)
    assert [item.plan_id for item in listed] == [revised.plan_id, first.plan_id]
    assert store.get(first.plan_id) == first


def test_a_retry_keeps_one_identity_regardless_of_recording_time(
    store: SQLiteNextDayPlanStore,
) -> None:
    """同一用户内容重试只产生一条记录；created_at 不参与内容身份。"""
    first = _plan()
    retried = _plan(created_at=datetime(2026, 11, 10, 15, 41, tzinfo=UTC))

    assert retried.plan_id == first.plan_id
    store.save(first)

    listed = store.list_recent(limit=10)
    assert len(listed) == 1
    assert listed[0].created_at == first.created_at


def test_a_sequential_retry_returns_the_first_recorded_entry(
    store: SQLiteNextDayPlanStore,
) -> None:
    """顺序重试：save(较晚 created_at 的同内容) 返回首存条目而非报错。"""
    first = _plan()
    retried = _plan(created_at=datetime(2026, 11, 10, 15, 41, tzinfo=UTC))

    store.save(first)
    returned = store.save(retried)

    assert returned == first
    assert returned.created_at == first.created_at
    assert len(store.list_recent(limit=10)) == 1


def test_a_concurrent_same_content_writer_converges_on_the_stored_entry(
    tmp_path: Path,
) -> None:
    """并发交错：get 与 INSERT 之间对手已提交同内容写入，重放收敛首存。"""
    pool_a = SQLitePool(str(tmp_path / "metadata.sqlite"))
    client_a = SQLiteClient(pool_a)
    store_a = SQLiteNextDayPlanStore(client_a)
    store_a.init_schema()
    pool_b = SQLitePool(str(tmp_path / "metadata.sqlite"))
    client_b = SQLiteClient(pool_b)
    store_b = SQLiteNextDayPlanStore(client_b)
    try:
        first = _plan()
        store_a.save(first)
        # 竞态窗口：B 的 get 已见过 None（此刻才注入对手提交已可见），
        # B 走 INSERT 路径撞上 A 已提交的同内容行（ON CONFLICT DO NOTHING）。
        retried = _plan(created_at=datetime(2026, 11, 10, 15, 41, tzinfo=UTC))
        with patch.object(store_b, "get", return_value=None):
            returned = store_b.save(retried)
        assert returned == first
        assert returned.created_at == first.created_at
        assert len(store_a.list_recent(limit=10)) == 1
    finally:
        pool_b.close_all()
        pool_a.close_all()


def test_get_returns_none_for_an_unknown_plan(store: SQLiteNextDayPlanStore) -> None:
    assert store.get("next-day-plan:sha256:" + "0" * 64) is None


def test_save_rejects_a_row_that_breaks_content_addressing(
    store: SQLiteNextDayPlanStore,
) -> None:
    plan = _plan()
    store.save(plan)
    # 直接篡改持久化载荷（模拟存储层缺陷/外部写入）：同 plan_id 已属
    # 不同内容，重放必须 fail closed 而不是静默覆盖。
    other = _plan(next_day_plan="被篡改的计划正文")
    store._sqlite_client.execute(
        "UPDATE next_day_plan SET payload_json = ? WHERE plan_id = ?",
        (
            orjson.dumps(other.canonical_payload).decode(),
            plan.plan_id,
        ),
    )
    store._sqlite_client.commit()

    with pytest.raises(NextDayPlanIntegrityError):
        store.save(plan)
    with pytest.raises(NextDayPlanIntegrityError):
        store.get(plan.plan_id)


@pytest.mark.parametrize(
    "overrides_factory",
    [
        lambda: {"candidate_notes": ()},
        lambda: {
            "candidate_notes": (
                PlanCandidateNote(instrument_id=InstrumentId(600779), reason="a"),
                PlanCandidateNote(instrument_id=InstrumentId(600779), reason="b"),
            )
        },
        lambda: {
            "candidate_notes": (
                PlanCandidateNote(instrument_id=InstrumentId(1), reason=" "),
            )
        },
        lambda: {"next_day_plan": " "},
        lambda: {"next_day_plan": " padded "},
        lambda: {"created_at": datetime(2026, 11, 10, 15, 5)},
    ],
)
def test_plan_rejects_invalid_payloads(
    overrides_factory: Callable[[], dict[str, object]],
) -> None:
    with pytest.raises(ValueError):
        _plan(**overrides_factory())


def test_plan_rejects_a_non_positive_candidate_identity() -> None:
    with pytest.raises(ValueError, match="positive integer"):
        PlanCandidateNote(instrument_id=InstrumentId(0), reason="非法身份")


def test_candidate_order_is_preserved_for_the_reader() -> None:
    plan = _plan(
        candidate_notes=(
            PlanCandidateNote(instrument_id=InstrumentId(510888), reason="先看 ETF"),
            PlanCandidateNote(instrument_id=InstrumentId(600779), reason="再看个股"),
        ),
    )

    assert [note.instrument_id for note in plan.candidate_notes] == [510888, 600779]
    assert plan.canonical_payload["candidate_notes"] == [
        {"instrument_id": 510888, "reason": "先看 ETF"},
        {"instrument_id": 600779, "reason": "再看个股"},
    ]


def test_source_judgment_reference_changes_identity_and_only_rides_when_set() -> None:
    plain = _plan()
    sourced = _plan(source_judgment_id="research-judgment:sha256:" + "1" * 64)

    # 默认不带来源：canonical_payload 不含该键，旧对象身份逐字节不变。
    assert "source_judgment_id" not in plain.canonical_payload
    assert plain.source_judgment_id is None
    # 带来源是新的内容 → 新身份；来源键进入 preimage。
    assert sourced.plan_id != plain.plan_id
    assert (
        sourced.canonical_payload["source_judgment_id"]
        == "research-judgment:sha256:" + "1" * 64
    )
    assert sourced.source_judgment_id == "research-judgment:sha256:" + "1" * 64


def test_source_judgment_reference_must_use_the_judgment_identity_format() -> None:
    for invalid in ("", " ", "padded ", "next-day-plan:sha256:" + "1" * 64):
        with pytest.raises(ValueError, match="research-judgment:sha256:"):
            _plan(source_judgment_id=invalid)


def test_source_judgment_round_trips_through_the_store(
    store: SQLiteNextDayPlanStore,
) -> None:
    sourced = _plan(source_judgment_id="research-judgment:sha256:" + "2" * 64)

    store.save(sourced)

    restored = store.get(sourced.plan_id)
    assert restored is not None
    assert restored.source_judgment_id == "research-judgment:sha256:" + "2" * 64
    assert restored == sourced


def test_a_legacy_row_without_the_source_key_keeps_its_exact_identity(
    store: SQLiteNextDayPlanStore,
) -> None:
    """兼容：#743 旧行不含 source_judgment_id 键，解码后 canonical 字节不变。"""
    plan = _plan()
    legacy_payload = plan.canonical_payload
    legacy_bytes = orjson.dumps(legacy_payload, option=orjson.OPT_SORT_KEYS)
    legacy_id = f"next-day-plan:sha256:{sha256(legacy_bytes).hexdigest()}"
    # 旧行确实等于当前无来源对象的身份（回归防护：preimage 未漂移）。
    assert plan.plan_id == legacy_id
    encoded_row = orjson.dumps(
        {**legacy_payload, "created_at": _CREATED.isoformat()}
    ).decode()
    store._sqlite_client.execute(
        "INSERT INTO next_day_plan "
        "(plan_id, observation_date, created_at, payload_json) "
        "VALUES (?, ?, ?, ?)",
        (legacy_id, "2026-11-10", _CREATED.isoformat(), encoded_row),
    )
    store._sqlite_client.commit()

    restored = store.get(legacy_id)
    assert restored is not None
    assert restored.source_judgment_id is None
    assert (
        orjson.dumps(restored.canonical_payload, option=orjson.OPT_SORT_KEYS)
        == legacy_bytes
    )
    assert restored.plan_id == legacy_id
