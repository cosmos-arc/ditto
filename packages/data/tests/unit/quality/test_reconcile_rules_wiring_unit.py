"""#473-#474：跨源对账规则接线 —— 注册 yml 驱动真实 engine 语义.

验证 config/default/dq_rules/{income_statement,balance_sheet,cash_flow}.yml
注册的 cross_source_compare 规则能被 QualityEngine 消费：财务相对容差 /
eps 绝对容差、非日线比较键（report_date）、零交集 not_comparable。
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl
import pytest
import yaml
from ditto_data.quality.engine import QualityEngine
from ditto_data.quality.spec import DatasetRules, DQSpec

_D = date(2026, 9, 30)


def _repo_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "config" / "default" / "dq_rules").is_dir():
            return parent
    raise AssertionError("repo root with config/default/dq_rules not found")


def _engine(dataset: str) -> QualityEngine:
    data = yaml.safe_load(
        (_repo_root() / "config" / "default" / "dq_rules" / f"{dataset}.yml").read_text(
            encoding="utf-8"
        )
    )
    spec = DQSpec(datasets={data["dataset"]: DatasetRules(**data)})
    return QualityEngine(config=spec)


def _index_frame(rows: list[tuple[int, float, float]]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "instrument_id": [r[0] for r in rows],
            "trade_date": [_D] * len(rows),
            "close": [r[1] for r in rows],
            "volume": [r[2] for r in rows],
        },
        schema={
            "instrument_id": pl.Int64,
            "trade_date": pl.Date,
            "close": pl.Float64,
            "volume": pl.Float64,
        },
    )


@pytest.mark.unit
class TestIndexDailyRuleWiring:
    def test_two_decimal_rounding_within_tolerance(self) -> None:
        """fuyao 2 位小数舍入（3839.2527→3839.25）容差内 → 匹配无差异."""
        primary = _index_frame([(3000002, 3839.2527, 414_560_247.0)])
        secondary = _index_frame([(3000002, 3839.25, 414_560_250.0)])

        comparison = _engine("index_daily").compare_cross_source(
            primary=primary, secondary=secondary, dataset="index_daily"
        )

        assert comparison.comparable is True
        assert comparison.matched_count == 1
        assert comparison.diff_count == 0

    def test_material_price_gap_flags_difference(self) -> None:
        primary = _index_frame([(3000002, 3839.2527, 414_560_247.0)])
        secondary = _index_frame([(3000002, 3939.25, 414_560_247.0)])

        result = _engine("index_daily").check_cross_source(
            primary=primary, secondary=secondary, dataset="index_daily"
        )

        assert len(result.issues) == 1
        sample = result.issues[0].sample_data[0]
        assert sample["field"] == "close"
        assert sample["primary_value"] == pytest.approx(3839.2527)
        assert sample["secondary_value"] == pytest.approx(3939.25)

    def test_volume_relative_tolerance(self) -> None:
        """量额走相对容差 0.1%：0.5% 偏差 → 差异."""
        primary = _index_frame([(3000002, 3839.25, 100.0)])
        secondary = _index_frame([(3000002, 3839.25, 100.5)])

        result = _engine("index_daily").check_cross_source(
            primary=primary, secondary=secondary, dataset="index_daily"
        )

        assert any(s["field"] == "volume" for i in result.issues for s in i.sample_data)


def _income_frame(rows: list[tuple[int, float, float]]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "instrument_id": [r[0] for r in rows],
            "report_date": [_D] * len(rows),
            "revenue": [r[1] for r in rows],
            "eps": [r[2] for r in rows],
        },
        schema={
            "instrument_id": pl.Int64,
            "report_date": pl.Date,
            "revenue": pl.Float64,
            "eps": pl.Float64,
        },
    )


@pytest.mark.unit
class TestIncomeStatementRuleWiring:
    def test_same_values_match_on_report_date_key(self) -> None:
        comparison = _engine("income_statement").compare_cross_source(
            primary=_income_frame([(1, 90_703_260_964.48, 35.57)]),
            secondary=_income_frame([(1, 90_703_260_964.48, 35.57)]),
            dataset="income_statement",
        )

        assert comparison.comparable is True
        assert comparison.matched_count == 1
        assert comparison.key_columns == ("instrument_id", "report_date")

    def test_amount_relative_tolerance_covers_million_rounding(self) -> None:
        """辅源百万级舍入（337,532,000,000 vs 337,532,432,000）在 1e-4 内 → 匹配."""
        comparison = _engine("income_statement").compare_cross_source(
            primary=_income_frame([(2, 337_532_432_000.0, 5.7)]),
            secondary=_income_frame([(2, 337_532_000_000.0, 5.7)]),
            dataset="income_statement",
        )

        assert comparison.diff_count == 0

    def test_eps_absolute_tolerance_not_relative(self) -> None:
        """eps 小量纲字段按绝对 0.005：0.004 偏差在容差内；若按相对容差
        （0.004/5.7≈0.07%）将误报——精度口径单列的实测依据."""
        result = _engine("income_statement").check_cross_source(
            primary=_income_frame([(1, 1e10, 35.57)]),
            secondary=_income_frame([(1, 1e10, 35.574)]),
            dataset="income_statement",
        )

        assert result.issues == []

    def test_eps_material_gap_flags_difference(self) -> None:
        result = _engine("income_statement").check_cross_source(
            primary=_income_frame([(1, 1e10, 35.57)]),
            secondary=_income_frame([(1, 1e10, 36.07)]),
            dataset="income_statement",
        )

        assert any(s["field"] == "eps" for i in result.issues for s in i.sample_data)


@pytest.mark.unit
class TestBalanceAndCashFlowRuleWiring:
    def test_balance_sheet_registered_fields(self) -> None:
        engine = _engine("balance_sheet")
        comparison = engine.compare_cross_source(
            primary=pl.DataFrame(
                {
                    "instrument_id": [1],
                    "report_date": [_D],
                    "total_assets": [1.0e12],
                    "total_liabilities": [1.0e11],
                    "net_assets": [9.0e11],
                    "current_assets": [5.0e11],
                }
            ),
            secondary=pl.DataFrame(
                {
                    "instrument_id": [1],
                    "report_date": [_D],
                    "total_assets": [1.0e12],
                    "total_liabilities": [1.0e11],
                    "net_assets": [9.0e11],
                    "current_assets": [5.0e11],
                }
            ),
            dataset="balance_sheet",
        )

        assert comparison.matched_count == 1
        assert comparison.diff_count == 0

    def test_cash_flow_registered_fields(self) -> None:
        engine = _engine("cash_flow")
        comparison = engine.compare_cross_source(
            primary=pl.DataFrame(
                {
                    "instrument_id": [1],
                    "report_date": [_D],
                    "operating_cash_flow": [9.2e10],
                    "investing_cash_flow": [-3.0e9],
                    "financing_cash_flow": [-6.5e10],
                }
            ),
            secondary=pl.DataFrame(
                {
                    "instrument_id": [1],
                    "report_date": [_D],
                    "operating_cash_flow": [9.2e10],
                    "investing_cash_flow": [-3.0e9],
                    "financing_cash_flow": [-6.5e10],
                }
            ),
            dataset="cash_flow",
        )

        assert comparison.matched_count == 1
        assert comparison.diff_count == 0
