"""CrossSourceChecker 单元测试."""

import polars as pl
from ditto_core.quality.checkers import (
    CompareMethod,
    CrossSourceChecker,
)
from ditto_core.quality.spec import DQLevel
from ditto_foundation import DQSeverity


class TestCrossSourceChecker:
    """测试 CrossSourceChecker."""

    def test_init_default_rules(self) -> None:
        """测试默认容差规则初始化."""
        checker = CrossSourceChecker()
        assert "open" in checker.tolerance_rules
        assert "close" in checker.tolerance_rules
        assert "vol" in checker.tolerance_rules
        assert checker.tolerance_rules["open"].method == CompareMethod.TICK_ALIGNED
        assert checker.tolerance_rules["vol"].method == CompareMethod.RELATIVE

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
        assert issues[0].level == DQLevel.L3_STATISTICAL
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
                "vol": [1000],
            }
        )
        secondary = pl.DataFrame(
            {
                "symbol": ["1"],
                "trade_date": ["20240101"],
                "vol": [1005],  # 0.5% 差异
            }
        )

        checker = CrossSourceChecker()
        issues = checker.check(
            primary=primary,
            secondary=secondary,
            rules=[
                {
                    "rule": "cross_source_compare",
                    "fields": ["vol"],
                    "key_columns": ["symbol", "trade_date"],
                    "tolerance_rules": {
                        "vol": {
                            "method": "relative",
                            "relative_tol": 0.01,  # 1%
                        },
                    },
                }
            ],
        )

        # 0.5% < 1%，应该通过
        assert len(issues) == 0
