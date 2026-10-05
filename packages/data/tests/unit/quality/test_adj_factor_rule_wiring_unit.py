"""#438：adj_factor cross_source 规则接线 —— 注册规则驱动真实 engine 语义.

验证 config/default/dq_rules/adj_factor.yml 注册的 cross_source_compare
规则能被 QualityEngine 消费：基期不同但相对变化相同 → 比例匹配；
比例不一致 → 差异；零交集 → not_comparable。
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl
import pytest
import yaml
from ditto_data.quality.engine import QualityEngine
from ditto_data.quality.spec import DatasetRules, DQSpec

_D = date(2025, 6, 25)


def _repo_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "config" / "default" / "dq_rules").is_dir():
            return parent
    raise AssertionError("repo root with config/default/dq_rules not found")


def _engine() -> QualityEngine:
    data = yaml.safe_load(
        (_repo_root() / "config" / "default" / "dq_rules" / "adj_factor.yml").read_text(
            encoding="utf-8"
        )
    )
    spec = DQSpec(datasets={data["dataset"]: DatasetRules(**data)})
    return QualityEngine(config=spec)


def _ratios(rows: list[tuple[int, float | None]]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "instrument_id": [r[0] for r in rows],
            "trade_date": [_D] * len(rows),
            "adjustment_ratio": [r[1] for r in rows],
        },
        schema={
            "instrument_id": pl.Int64,
            "trade_date": pl.Date,
            "adjustment_ratio": pl.Float64,
        },
    )


@pytest.mark.unit
class TestAdjFactorRuleWiring:
    def test_equal_ratios_match_across_different_factor_bases(self) -> None:
        """基期不同(绝对因子 10→11 vs 2→2.2)但相对变化相同 → 匹配无差异."""
        comparison = _engine().compare_cross_source(
            primary=_ratios([(1, 1.1), (2, 1.1)]),
            secondary=_ratios([(1, 1.1), (2, 1.1)]),
            dataset="adj_factor",
        )

        assert comparison.comparable is True
        assert comparison.matched_count == 2
        assert comparison.diff_count == 0

    def test_ratio_mismatch_flags_difference(self) -> None:
        """比例不一致（超 0.5% 容差）→ 差异样本 field=adjustment_ratio."""
        result = _engine().check_cross_source(
            primary=_ratios([(1, 1.1)]),
            secondary=_ratios([(1, 1.15)]),
            dataset="adj_factor",
        )

        issues = result.issues
        assert len(issues) == 1
        assert issues[0].rule_name == "cross_source_compare"
        assert issues[0].sample_data[0]["field"] == "adjustment_ratio"

    def test_ratio_within_tolerance_passes(self) -> None:
        """0.5% 容差内（除权参考价 0.01 元取整量级）→ 不计差异."""
        result = _engine().check_cross_source(
            primary=_ratios([(1, 1.1)]),
            secondary=_ratios([(1, 1.103)]),
            dataset="adj_factor",
        )

        assert result.issues == []

    def test_zero_intersection_not_comparable(self) -> None:
        comparison = _engine().compare_cross_source(
            primary=_ratios([(1, 1.1)]),
            secondary=_ratios([(2, 1.1)]),
            dataset="adj_factor",
        )

        assert comparison.comparable is False
        assert comparison.status == "not_comparable"
