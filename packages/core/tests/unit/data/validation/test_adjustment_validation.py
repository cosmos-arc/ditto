"""复权因子验证测试."""

from datetime import date

import pytest
from ditto_core.data.validation.adjustment_validation import AdjustmentFactorValidator


class TestAdjustmentFactorValidator:
    """复权因子验证器测试."""

    @pytest.fixture
    def validator(self) -> AdjustmentFactorValidator:
        """创建验证器实例."""
        return AdjustmentFactorValidator()

    def test_validate_continuous_adjustment_sequence(
        self, validator: AdjustmentFactorValidator
    ) -> None:
        """测试连续复权因子的验证."""
        data = [
            {
                "symbol": "510300",
                "date": "2024-06-01",
                "adj_factor": 1.0,
                "adj_type": "dividend",
            },
            {
                "symbol": "510300",
                "date": "2024-06-02",
                "adj_factor": 1.05,
                "adj_type": None,
            },
            {
                "symbol": "510300",
                "date": "2024-06-03",
                "adj_factor": 1.05,
                "adj_type": None,
            },
        ]

        result = validator.validate_adjustment_factors("510300", data)

        assert result.symbol == "510300"
        assert result.is_valid is True
        assert len(result.issues) == 0
        assert result.cumulative_factor == pytest.approx(1.05)

    def test_detect_missing_dividend_record(
        self, validator: AdjustmentFactorValidator
    ) -> None:
        """检测缺失的分红记录."""
        data = [
            {
                "symbol": "510300",
                "date": "2024-06-01",
                "adj_factor": 1.0,
                "adj_type": None,
            },
            {
                "symbol": "510300",
                "date": "2024-06-02",
                "adj_factor": 1.05,
                "adj_type": None,
            },
            {
                "symbol": "510300",
                "date": "2024-06-03",
                "adj_factor": 1.05,
                "adj_type": "dividend",
            },
        ]

        result = validator.validate_adjustment_factors("510300", data)

        assert result.is_valid is False
        assert len(result.issues) > 0
        assert any(
            "missing dividend record" in issue.lower() for issue in result.issues
        )

    def test_detect_inconsistent_cumulative_factors(
        self, validator: AdjustmentFactorValidator
    ) -> None:
        """检测累积因子不一致."""
        data = [
            {
                "symbol": "510300",
                "date": "2024-06-01",
                "adj_factor": 1.0,
                "adj_type": "dividend",
            },
            {
                "symbol": "510300",
                "date": "2024-06-02",
                "adj_factor": 1.05,
                "adj_type": None,
            },
            {
                "symbol": "510300",
                "date": "2024-06-03",
                "adj_factor": 1.10,
                "adj_type": None,
            },
        ]

        result = validator.validate_adjustment_factors("510300", data)

        assert result.is_valid is False
        assert any("inconsistent" in issue.lower() for issue in result.issues)
        assert result.expected_cumulative_factor == pytest.approx(1.05)

    def test_detect_extreme_adjustment_factor(
        self, validator: AdjustmentFactorValidator
    ) -> None:
        """检测异常的复权因子(>3或<0.1)."""
        data = [
            {
                "symbol": "510300",
                "date": "2024-06-01",
                "adj_factor": 5.0,
                "adj_type": "dividend",
            },  # 异常值
        ]

        result = validator.validate_adjustment_factors("510300", data)

        assert result.is_valid is False
        assert any(
            "extreme adjustment factor" in issue.lower() for issue in result.issues
        )
        assert result.factor_stats["max"] == 5.0

    def test_generate_validation_report(
        self, validator: AdjustmentFactorValidator
    ) -> None:
        """测试生成验证报告."""
        symbols_data = {
            "510300": [
                {
                    "symbol": "510300",
                    "date": "2024-06-01",
                    "adj_factor": 1.0,
                    "adj_type": "dividend",
                },
                {
                    "symbol": "510300",
                    "date": "2024-06-02",
                    "adj_factor": 1.05,
                    "adj_type": None,
                },
            ],
            "159915": [
                {
                    "symbol": "159915",
                    "date": "2024-06-01",
                    "adj_factor": 0.95,
                    "adj_type": "split",
                },  # 股票分割
                {
                    "symbol": "159915",
                    "date": "2024-06-02",
                    "adj_factor": 0.95,
                    "adj_type": None,
                },
            ],
            "513100": [
                {
                    "symbol": "513100",
                    "date": "2024-06-01",
                    "adj_factor": 3.5,
                    "adj_type": "dividend",
                },  # 异常值
            ],
        }

        report = validator.generate_validation_report(symbols_data)

        assert "summary" in report
        assert report["summary"]["total_symbols"] == 3
        assert report["summary"]["valid_symbols"] == 2
        assert report["summary"]["invalid_symbols"] == 1

        assert "510300" in report["details"]
        assert report["details"]["510300"]["is_valid"] is True

        assert "513100" in report["details"]
        assert report["details"]["513100"]["is_valid"] is False

    def test_calculate_adjustment_statistics(
        self, validator: AdjustmentFactorValidator
    ) -> None:
        """测试复权因子统计计算."""
        data = [
            {"symbol": "510300", "date": "2024-06-01", "adj_factor": 1.0},
            {"symbol": "510300", "date": "2024-06-02", "adj_factor": 1.05},
            {"symbol": "510300", "date": "2024-06-03", "adj_factor": 1.05},
            {"symbol": "510300", "date": "2024-06-04", "adj_factor": 0.98},
        ]

        stats = validator._calculate_statistics(data)

        assert stats["count"] == 4
        assert stats["mean"] == pytest.approx(1.02)
        assert stats["min"] == 0.98
        assert stats["max"] == 1.05
        assert stats["std"] > 0

    def test_detect_missing_dates(self, validator: AdjustmentFactorValidator) -> None:
        """检测缺失的日期记录."""
        data = [
            {"symbol": "510300", "date": "2024-06-01", "adj_factor": 1.0},
            {"symbol": "510300", "date": "2024-06-03", "adj_factor": 1.05},  # 缺少6-02
        ]

        # 提供预期的日期范围
        expected_dates = [date(2024, 6, 1), date(2024, 6, 2), date(2024, 6, 3)]

        issues = validator._detect_missing_dates("510300", data, expected_dates)

        assert len(issues) == 1
        assert "2024-06-02" in issues[0]

    def test_validate_date_sequence(self, validator: AdjustmentFactorValidator) -> None:
        """测试日期序列的连续性."""
        data = [
            {"symbol": "510300", "date": "2024-06-01", "adj_factor": 1.0},
            {
                "symbol": "510300",
                "date": "2024-06-03",
                "adj_factor": 1.05,
            },  # 跳过了6-02
        ]

        issues = validator._validate_date_sequence(data)

        assert len(issues) > 0
        assert any("gap" in issue.lower() for issue in issues)

    def test_batch_validate_multiple_symbols(
        self, validator: AdjustmentFactorValidator
    ) -> None:
        """测试批量验证多个股票."""
        symbols_data = {
            "510300": [
                {
                    "symbol": "510300",
                    "date": "2024-06-01",
                    "adj_factor": 1.0,
                    "adj_type": "dividend",
                },
            ],
            "159915": [
                {
                    "symbol": "159915",
                    "date": "2024-06-01",
                    "adj_factor": 0.95,
                    "adj_type": "split",
                },
            ],
        }

        results = validator.batch_validate(symbols_data)

        assert len(results) == 2
        assert "510300" in results
        assert "159915" in results
        assert all(results[symbol].symbol == symbol for symbol in results)
