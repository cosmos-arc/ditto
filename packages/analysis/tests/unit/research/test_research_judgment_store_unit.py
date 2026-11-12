"""SQLite persistence and domain rules for immutable research judgments."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import orjson
import pytest
from ditto_analysis.errors import ResearchJudgmentIntegrityError
from ditto_analysis.research.judgments import ResearchJudgment
from ditto_analysis.storage.sqlite.research.judgment_store import (
    SQLiteResearchJudgmentStore,
)
from ditto_platform.foundation import SQLiteClient, SQLitePool

_CREATED = datetime(2026, 11, 10, 15, 5, tzinfo=UTC)


def _judgment(**overrides: object) -> ResearchJudgment:
    baseline = ResearchJudgment(
        run_ids=("sys-fx-nav-001", "sys-fx-nav-002"),
        judgment="两个 run 同口径可比; 001 回撤更浅但收益略低, 次日优先观察放量修复",
        created_at=_CREATED,
    )
    return replace(baseline, **overrides)


@pytest.fixture
def store(tmp_path: Path) -> Iterator[SQLiteResearchJudgmentStore]:
    pool = SQLitePool(str(tmp_path / "metadata.sqlite"))
    client = SQLiteClient(pool)
    value = SQLiteResearchJudgmentStore(client)
    value.init_schema()
    yield value
    pool.close_all()


def test_judgment_is_content_addressed_and_idempotent_on_replay(
    store: SQLiteResearchJudgmentStore,
) -> None:
    judgment = _judgment()

    store.save(judgment)
    store.save(judgment)

    restored = store.get(judgment.judgment_id)
    assert restored is not None
    assert restored == judgment
    assert restored.judgment_id.startswith("research-judgment:sha256:")
    assert len(store.list_recent(limit=10)) == 1


def test_edited_judgments_are_separate_immutable_entries(
    store: SQLiteResearchJudgmentStore,
) -> None:
    first = _judgment()
    revised = _judgment(
        judgment="修订: 002 的费用轴与 001 不一致, 先核对费用口径再比较",
        created_at=datetime(2026, 11, 10, 15, 40, tzinfo=UTC),
    )

    store.save(first)
    store.save(revised)

    assert first.judgment_id != revised.judgment_id
    listed = store.list_recent(limit=10)
    assert [item.judgment_id for item in listed] == [
        revised.judgment_id,
        first.judgment_id,
    ]
    assert store.get(first.judgment_id) == first


def test_a_retry_keeps_one_identity_regardless_of_recording_time(
    store: SQLiteResearchJudgmentStore,
) -> None:
    """同一用户内容重试只产生一条记录；created_at 不参与内容身份。"""
    first = _judgment()
    retried = _judgment(created_at=datetime(2026, 11, 10, 15, 41, tzinfo=UTC))

    assert retried.judgment_id == first.judgment_id
    store.save(first)

    listed = store.list_recent(limit=10)
    assert len(listed) == 1
    assert listed[0].created_at == first.created_at


def test_a_sequential_retry_returns_the_first_recorded_entry(
    store: SQLiteResearchJudgmentStore,
) -> None:
    """顺序重试：save(较晚 created_at 的同内容) 返回首存条目而非报错。"""
    first = _judgment()
    retried = _judgment(created_at=datetime(2026, 11, 10, 15, 41, tzinfo=UTC))

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
    store_a = SQLiteResearchJudgmentStore(client_a)
    store_a.init_schema()
    pool_b = SQLitePool(str(tmp_path / "metadata.sqlite"))
    client_b = SQLiteClient(pool_b)
    store_b = SQLiteResearchJudgmentStore(client_b)
    try:
        first = _judgment()
        store_a.save(first)
        retried = _judgment(created_at=datetime(2026, 11, 10, 15, 41, tzinfo=UTC))
        with patch.object(store_b, "get", return_value=None):
            returned = store_b.save(retried)
        assert returned == first
        assert returned.created_at == first.created_at
        assert len(store_a.list_recent(limit=10)) == 1
    finally:
        pool_b.close_all()
        pool_a.close_all()


def test_get_returns_none_for_an_unknown_judgment(
    store: SQLiteResearchJudgmentStore,
) -> None:
    assert store.get("research-judgment:sha256:" + "0" * 64) is None


def test_save_rejects_a_row_that_breaks_content_addressing(
    store: SQLiteResearchJudgmentStore,
) -> None:
    judgment = _judgment()
    store.save(judgment)
    # 直接篡改持久化载荷（模拟存储层缺陷/外部写入）：同 judgment_id 已属
    # 不同内容，重放必须 fail closed 而不是静默覆盖。
    other = _judgment(judgment="被篡改的判断正文")
    store._sqlite_client.execute(
        "UPDATE research_judgment SET payload_json = ? WHERE judgment_id = ?",
        (
            orjson.dumps(other.canonical_payload).decode(),
            judgment.judgment_id,
        ),
    )
    store._sqlite_client.commit()

    with pytest.raises(ResearchJudgmentIntegrityError):
        store.save(judgment)
    with pytest.raises(ResearchJudgmentIntegrityError):
        store.get(judgment.judgment_id)


def test_strategy_reference_rides_in_the_content_addressed_payload() -> None:
    without = _judgment()
    with_strategy = _judgment(strategy_id="sys-fx-etf-rotation", strategy_version=2)

    assert with_strategy.judgment_id != without.judgment_id
    payload = with_strategy.canonical_payload
    assert payload["strategy_id"] == "sys-fx-etf-rotation"
    assert payload["strategy_version"] == 2
    assert "strategy_id" not in without.canonical_payload
    assert "strategy_version" not in without.canonical_payload


@pytest.mark.parametrize(
    "overrides_factory",
    [
        lambda: {"run_ids": ()},
        lambda: {"run_ids": ("sys-fx-nav-001", "sys-fx-nav-001")},
        lambda: {"run_ids": (" ",)},
        lambda: {"run_ids": (" padded ",)},
        lambda: {"judgment": " "},
        lambda: {"judgment": " padded "},
        lambda: {"created_at": datetime(2026, 11, 10, 15, 5)},
        lambda: {"strategy_id": "sys-fx-etf-rotation", "strategy_version": None},
        lambda: {"strategy_id": None, "strategy_version": 2},
        lambda: {"strategy_id": "sys-fx-etf-rotation", "strategy_version": 0},
    ],
)
def test_judgment_rejects_invalid_payloads(
    overrides_factory: Callable[[], dict[str, object]],
) -> None:
    with pytest.raises(ValueError):
        _judgment(**overrides_factory())


def test_run_order_is_preserved_for_the_reader() -> None:
    judgment = _judgment(run_ids=("sys-fx-nav-002", "sys-fx-nav-001"))

    assert judgment.run_ids == ("sys-fx-nav-002", "sys-fx-nav-001")
    assert judgment.canonical_payload["run_ids"] == [
        "sys-fx-nav-002",
        "sys-fx-nav-001",
    ]
