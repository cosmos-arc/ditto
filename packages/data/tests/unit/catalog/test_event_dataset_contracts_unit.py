"""#519 事件型数据集契约：frequency=event + dq 规则不配日历完整性.

票面验收「事件型完整性口径有测试锁定」——事件型（有上榜才有行）数据集
不得套用日历完整性期望；本测试锁死两端的回归口。
"""

from __future__ import annotations

from pathlib import Path

import yaml
from ditto_data.catalog.dataset_spec import resolve_dataset_spec

_EVENT_DATASETS = (
    "limit_list",
    "top_list",
    "top_inst",
    "hk_hold",
    "hsgt_top10",
)

_DQ_RULES_DIR = Path(__file__).parents[5] / "config" / "default" / "dq_rules"


def test_event_datasets_resolve_to_event_frequency() -> None:
    """五个事件型数据集的 spec frequency 必须保持 event."""
    for dataset_id in _EVENT_DATASETS:
        spec = resolve_dataset_spec(dataset_id)
        assert spec.frequency == "event", (
            f"{dataset_id} 必须保持事件型 frequency=event (有上榜才有行), "
            f"当前 {spec.frequency}"
        )


def test_event_dataset_dq_rules_have_no_calendar_completeness() -> None:
    """事件型数据集 dq 规则不得配置日历完整性（statistical.completeness）."""
    for dataset_id in _EVENT_DATASETS:
        rule_path = _DQ_RULES_DIR / f"{dataset_id}.yml"
        assert rule_path.exists(), f"missing dq rules for {dataset_id}"
        loaded = yaml.safe_load(rule_path.read_text()) or {}
        statistical = loaded.get("statistical") or []
        completeness = [
            rule
            for rule in statistical
            if isinstance(rule, dict)
            and rule.get("rule") == "completeness"
            and rule.get("expected_dates") == "trade_calendar"
        ]
        assert not completeness, (
            f"{dataset_id} 是事件型数据集, 不得配置 trade_calendar 完整性期望"
        )


def test_event_dataset_primary_keys_carry_event_dimensions() -> None:
    """事件维度（reason/exalter+side/limit_type/market_type）必须进主键."""
    expected_dimensions = {
        "limit_list": "limit_type",
        "top_list": "reason",
        "top_inst": "exalter",
        "hk_hold": "knowledge_date",
        "hsgt_top10": "market_type",
    }
    for dataset_id, dimension in expected_dimensions.items():
        spec = resolve_dataset_spec(dataset_id)
        assert dimension in spec.primary_key, (
            f"{dataset_id} 主键 {spec.primary_key} 缺事件维度 {dimension}"
        )
