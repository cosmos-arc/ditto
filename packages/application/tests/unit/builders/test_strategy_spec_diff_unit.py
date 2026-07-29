"""Strategy spec canonical payload diff 与 payload 提取的单元测试."""

from __future__ import annotations

import hashlib
from dataclasses import asdict

import orjson
from ditto_application.contracts import SpecChange
from ditto_application.strategy_spec_deserialization import (
    canonical_spec_hash_for_record,
    canonical_spec_payload_for_record,
    diff_canonical_payloads,
)
from ditto_strategy.alpha.seeds import SEED_STRATEGY_SPECS
from ditto_strategy.models import StrategySpecRecord


def _seed_record(key: str = "seed_stock_selection_rotation") -> StrategySpecRecord:
    """构造一个可成功 legacy deserialize 的 record（用于 payload/hash 同源验证）."""
    seed = SEED_STRATEGY_SPECS[key]
    return StrategySpecRecord(
        strategy_id=seed.strategy_id,
        name=seed.name,
        spec_json=asdict(seed),
        version=1,
        tags=seed.tags,
    )


class TestDiffCanonicalPayloads:
    """diff_canonical_payloads 递归比较两个 canonical payload dict，输出字段级变更."""

    def test_empty_when_identical(self) -> None:
        assert diff_canonical_payloads({"a": 1}, {"a": 1}) == ()

    def test_added_top_level_key(self) -> None:
        result = diff_canonical_payloads({}, {"a": 1})
        assert result == (
            SpecChange(path="a", op="added", old_value=None, new_value=1),
        )

    def test_removed_top_level_key(self) -> None:
        result = diff_canonical_payloads({"a": 1}, {})
        assert result == (
            SpecChange(path="a", op="removed", old_value=1, new_value=None),
        )

    def test_changed_scalar(self) -> None:
        result = diff_canonical_payloads({"a": 1}, {"a": 2})
        assert result == (SpecChange(path="a", op="changed", old_value=1, new_value=2),)

    def test_nested_dict_path_accumulates(self) -> None:
        base = {"pipeline": {"sequence": ["a", "b"]}}
        target = {"pipeline": {"sequence": ["a", "c"]}}
        result = diff_canonical_payloads(base, target)
        assert result == (
            SpecChange(
                path="pipeline.sequence[1]",
                op="changed",
                old_value="b",
                new_value="c",
            ),
        )

    def test_list_added_element(self) -> None:
        result = diff_canonical_payloads({"s": [1, 2]}, {"s": [1, 2, 3]})
        assert result == (
            SpecChange(path="s[2]", op="added", old_value=None, new_value=3),
        )

    def test_list_removed_element(self) -> None:
        result = diff_canonical_payloads({"s": [1, 2, 3]}, {"s": [1, 2]})
        assert result == (
            SpecChange(path="s[2]", op="removed", old_value=3, new_value=None),
        )

    def test_type_mismatch_records_changed(self) -> None:
        """base 是 dict、target 是 scalar 时整体记为 changed，不递归."""
        result = diff_canonical_payloads({"a": {"x": 1}}, {"a": 5})
        assert result == (
            SpecChange(path="a", op="changed", old_value={"x": 1}, new_value=5),
        )

    def test_multiple_changes_collected(self) -> None:
        result = diff_canonical_payloads(
            {"a": 1, "b": 2, "c": 3},
            {"a": 1, "b": 99, "d": 4},
        )
        assert SpecChange(path="b", op="changed", old_value=2, new_value=99) in result
        assert SpecChange(path="c", op="removed", old_value=3, new_value=None) in result
        assert SpecChange(path="d", op="added", old_value=None, new_value=4) in result
        assert len(result) == 3


class TestCanonicalSpecPayloadForRecord:
    """canonical_spec_payload_for_record 与 canonical_spec_hash_for_record 同源."""

    def test_payload_hashes_to_canonical_spec_hash(self) -> None:
        record = _seed_record()
        payload = canonical_spec_payload_for_record(record)
        digest = hashlib.sha256(
            orjson.dumps(payload, option=orjson.OPT_SORT_KEYS)
        ).hexdigest()
        assert digest == canonical_spec_hash_for_record(record)

    def test_payload_only_carries_execution_identity_fields(self) -> None:
        record = _seed_record()
        payload = canonical_spec_payload_for_record(record)
        assert set(payload.keys()) == {
            "parameter_schema",
            "pipeline",
            "schema_version",
            "strategy_family_id",
            "strategy_kind",
        }

    def test_two_distinct_seeds_produce_diff(self) -> None:
        """两个不同 seed 的 canonical payload 必有差异（diff 端到端 sanity）."""
        keys = list(SEED_STRATEGY_SPECS)
        if len(keys) < 2:
            return
        base_payload = canonical_spec_payload_for_record(_seed_record(keys[0]))
        target_payload = canonical_spec_payload_for_record(_seed_record(keys[1]))
        assert len(diff_canonical_payloads(base_payload, target_payload)) > 0
