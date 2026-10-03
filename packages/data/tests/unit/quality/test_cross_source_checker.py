"""CrossSourceChecker 单元测试."""

import polars as pl
from ditto_data.quality.checkers import (
    CompareMethod,
    CrossSourceChecker,
)
from ditto_data.quality.quality_types import DQLevel, DQSeverity


class TestCrossSourceChecker:
    """测试 CrossSourceChecker."""

    def test_init_default_rules(self) -> None:
        """测试默认容差规则初始化."""
        checker = CrossSourceChecker()
        assert "open" in checker.tolerance_rules
        assert "close" in checker.tolerance_rules
        assert "volume" in checker.tolerance_rules
        assert checker.tolerance_rules["open"].method == CompareMethod.TICK_ALIGNED
        assert checker.tolerance_rules["volume"].method == CompareMethod.RELATIVE

    def test_check_no_diff(self) -> None:
        """测试无差异场景."""
        primary = pl.DataFrame(
            {
                "symbol": ["000001", "000002"],
                "trade_date": ["20240101", "20240101"],
                "close": [10.0, 20.0],
            }
        )
        secondary = pl.DataFrame(
            {
                "symbol": ["000001", "000002"],
                "trade_date": ["20240101", "20240101"],
                "close": [10.0, 20.0],
            }
        )

        checker = CrossSourceChecker()
        issues = checker.check(
            primary=primary,
            secondary=secondary,
            rules=[
                {
                    "rule": "cross_source_compare",
                    "fields": ["close"],
                    "key_columns": ["symbol", "trade_date"],
                }
            ],
        )

        assert len(issues) == 0

    def test_check_with_diff(self) -> None:
        """测试有差异场景."""
        primary = pl.DataFrame(
            {
                "symbol": ["000001"],
                "trade_date": ["20240101"],
                "close": [10.05],  # 差异超过 0.01
            }
        )
        secondary = pl.DataFrame(
            {
                "symbol": ["000001"],
                "trade_date": ["20240101"],
                "close": [10.0],
            }
        )

        checker = CrossSourceChecker()
        issues = checker.check(
            primary=primary,
            secondary=secondary,
            rules=[
                {
                    "rule": "cross_source_compare",
                    "fields": ["close"],
                    "key_columns": ["symbol", "trade_date"],
                }
            ],
        )

        assert len(issues) == 1
        assert issues[0].level == DQLevel.STATISTICAL
        assert issues[0].severity == DQSeverity.ALERT
        assert issues[0].affected_rows == 1

    def test_check_disabled(self) -> None:
        """测试规则关闭场景."""
        primary = pl.DataFrame(
            {
                "symbol": ["1"],
                "trade_date": ["20240101"],
                "close": [10.0],
            }
        )
        secondary = pl.DataFrame(
            {
                "symbol": ["1"],
                "trade_date": ["20240101"],
                "close": [20.0],
            }
        )

        checker = CrossSourceChecker()
        issues = checker.check(
            primary=primary,
            secondary=secondary,
            rules=[
                {
                    "rule": "cross_source_compare",
                    "fields": ["close"],
                    "key_columns": ["symbol", "trade_date"],
                    "enabled": False,  # 关闭
                }
            ],
        )

        assert len(issues) == 0

    def test_custom_tolerance(self) -> None:
        """测试自定义容差规则."""
        primary = pl.DataFrame(
            {
                "symbol": ["1"],
                "trade_date": ["20240101"],
                "volume": [1000],
            }
        )
        secondary = pl.DataFrame(
            {
                "symbol": ["1"],
                "trade_date": ["20240101"],
                "volume": [1005],  # 0.5% 差异
            }
        )

        checker = CrossSourceChecker()
        issues = checker.check(
            primary=primary,
            secondary=secondary,
            rules=[
                {
                    "rule": "cross_source_compare",
                    "fields": ["volume"],
                    "key_columns": ["symbol", "trade_date"],
                    "tolerance_rules": {
                        "volume": {
                            "method": "relative",
                            "relative_tol": 0.01,  # 1%
                        },
                    },
                }
            ],
        )

        # 0.5% < 1%，应该通过
        assert len(issues) == 0


class TestCrossSourceComparisonReport:
    """#395 结构化对比报告：确定性反例与计数。"""

    KEYS = ("instrument_id", "trade_date")

    @staticmethod
    def _frame(instrument_ids: list[int], **columns: object) -> pl.DataFrame:
        data: dict[str, object] = {
            "instrument_id": instrument_ids,
            "trade_date": ["2026-09-18"] * len(instrument_ids),
        }
        data.update(columns)
        return pl.DataFrame(data)

    def test_zero_intersection_is_not_comparable(self) -> None:
        """确定性反例：零交集 = 不可比较，不算通过。"""
        checker = CrossSourceChecker()
        comparison = checker.compare(
            self._frame([1, 2], close=[10.0, 20.0]),
            self._frame([3, 4], close=[10.0, 20.0]),
            key_columns=list(self.KEYS),
            fields=["close"],
        )

        assert comparison.status == "not_comparable"
        assert comparison.comparable is False
        assert comparison.matched_count == 0
        assert comparison.primary_unmatched_count == 2
        assert comparison.secondary_unmatched_count == 2
        # DQ 侧产出显式 WARNING（而非静默通过）
        issues = checker.check(
            self._frame([1, 2], close=[10.0, 20.0]),
            self._frame([3, 4], close=[10.0, 20.0]),
            rules=[
                {
                    "rule": "cross_source_compare",
                    "fields": ["close"],
                    "key_columns": list(self.KEYS),
                }
            ],
        )
        assert len(issues) == 1
        assert issues[0].rule_name == "cross_source_not_comparable"
        assert issues[0].severity == DQSeverity.WARNING

    def test_duplicate_keys_reported(self) -> None:
        """确定性反例：重复键单独报告（不静默去重）。"""
        checker = CrossSourceChecker()
        primary = pl.DataFrame(
            {
                "instrument_id": [1, 1, 2],
                "trade_date": ["2026-09-18"] * 3,
                "close": [10.0, 10.1, 20.0],
            }
        )
        secondary = self._frame([1, 2], close=[10.0, 20.0])

        comparison = checker.compare(
            primary, secondary, key_columns=list(self.KEYS), fields=["close"]
        )
        assert comparison.primary_duplicate_keys == 1
        assert comparison.secondary_duplicate_keys == 0
        assert comparison.matched_count == 2

        issues = checker.check(
            primary,
            secondary,
            rules=[
                {
                    "rule": "cross_source_compare",
                    "fields": ["close"],
                    "key_columns": list(self.KEYS),
                }
            ],
        )
        assert len(issues) == 1
        assert issues[0].rule_name == "cross_source_duplicate_keys"

    def test_unit_mismatch_volumes_flagged(self) -> None:
        """确定性反例：单位不一致（股 vs 手 ×100）全量命中差异。"""
        checker = CrossSourceChecker()
        primary = self._frame([1, 2], volume=[1000.0, 2000.0])
        secondary = self._frame([1, 2], volume=[100_000.0, 200_000.0])  # 未归一股数

        comparison = checker.compare(
            primary, secondary, key_columns=self.KEYS, fields=["volume"]
        )
        assert comparison.comparable
        assert comparison.diff_count == 2
        assert all(row["field"] == "volume" for row in comparison.diff_rows)

    def test_adjustment_mismatch_closes_flagged(self) -> None:
        """确定性反例：复权口径不一致（原始 vs 前复权）价格全量差异。"""
        checker = CrossSourceChecker()
        primary = self._frame([1, 2], close=[10.0, 20.0])
        secondary = self._frame([1, 2], close=[25.4, 51.2])  # 前复权价

        comparison = checker.compare(
            primary, secondary, key_columns=list(self.KEYS), fields=["close"]
        )
        assert comparison.comparable
        assert comparison.diff_count == 2
        assert all(row["field"] == "close" for row in comparison.diff_rows)

    def test_ex_dividend_day_diffs_flagged_separately(self) -> None:
        """除权日（adj_factor 事件日）差异单列标记 ex_dividend_day。"""
        checker = CrossSourceChecker()
        primary = self._frame([1, 2], close=[10.0, 20.0])
        secondary = self._frame([1, 2], close=[9.0, 20.0])  # 标的 1 除权日跳空

        comparison = checker.compare(
            primary,
            secondary,
            key_columns=self.KEYS,
            fields=["close"],
            ex_dividend_instruments=frozenset({1}),
        )
        assert comparison.diff_count == 1
        diff = comparison.diff_rows[0]
        assert diff["instrument_id"] == 1
        assert diff["ex_dividend_day"] is True

    def test_outer_anti_counts_reported(self) -> None:
        """outer/anti 分析：两侧数量/匹配/未匹配计数齐全。"""
        checker = CrossSourceChecker()
        primary = self._frame([1, 2, 3], close=[10.0, 20.0, 30.0])
        secondary = self._frame([2, 3, 4], close=[20.0, 30.0, 40.0])

        comparison = checker.compare(
            primary, secondary, key_columns=list(self.KEYS), fields=["close"]
        )
        assert comparison.status == "compared"
        assert comparison.comparable
        assert comparison.primary_count == 3
        assert comparison.secondary_count == 3
        assert comparison.matched_count == 2
        assert comparison.primary_unmatched_count == 1  # 标的 1 仅在主侧
        assert comparison.secondary_unmatched_count == 1  # 标的 4 仅在辅侧
        assert comparison.diff_count == 0  # 匹配行无差异
