"""涨跌停识别准确率测试."""

from datetime import date

import pytest
from ditto_core.data.validation.limit_accuracy import (
    AccuracyMetrics,
    LimitAccuracyValidator,
)


class TestLimitAccuracyValidator:
    """涨跌停识别准确率验证器测试."""

    @pytest.fixture
    def validator(self) -> LimitAccuracyValidator:
        """创建验证器实例."""
        return LimitAccuracyValidator()

    def test_perfect_accuracy(self, validator: LimitAccuracyValidator) -> None:
        """测试完美识别的情况."""
        predicted = [
            {"date": date(2024, 6, 1), "is_limit_up": True, "is_limit_down": False},
            {"date": date(2024, 6, 2), "is_limit_up": False, "is_limit_down": False},
            {"date": date(2024, 6, 3), "is_limit_up": False, "is_limit_down": True},
        ]

        actual = [
            {
                "date": date(2024, 6, 1),
                "actual_limit_up": True,
                "actual_limit_down": False,
            },
            {
                "date": date(2024, 6, 2),
                "actual_limit_up": False,
                "actual_limit_down": False,
            },
            {
                "date": date(2024, 6, 3),
                "actual_limit_up": False,
                "actual_limit_down": True,
            },
        ]

        report = validator.validate_accuracy("510300", predicted, actual)

        # 检查涨停指标
        assert report.limit_up_metrics.accuracy == pytest.approx(1.0)
        assert report.limit_up_metrics.precision == pytest.approx(1.0)
        assert report.limit_up_metrics.recall == pytest.approx(1.0)
        assert report.limit_up_metrics.f1_score == pytest.approx(1.0)

        # 检查跌停指标
        assert report.limit_down_metrics.accuracy == pytest.approx(1.0)
        assert report.limit_down_metrics.precision == pytest.approx(1.0)
        assert report.limit_down_metrics.recall == pytest.approx(1.0)
        assert report.limit_down_metrics.f1_score == pytest.approx(1.0)

        # 检查总体指标
        assert report.overall_metrics.accuracy == pytest.approx(1.0)

    def test_mixed_predictions(self, validator: LimitAccuracyValidator) -> None:
        """测试混合预测情况."""
        predicted = [
            {"date": date(2024, 6, 1), "is_limit_up": True, "is_limit_down": False},
            {
                "date": date(2024, 6, 2),
                "is_limit_up": True,
                "is_limit_down": False,
            },  # False positive
            {"date": date(2024, 6, 3), "is_limit_up": False, "is_limit_down": False},
            {"date": date(2024, 6, 4), "is_limit_up": False, "is_limit_down": True},
        ]

        actual = [
            {
                "date": date(2024, 6, 1),
                "actual_limit_up": True,
                "actual_limit_down": False,
            },
            {
                "date": date(2024, 6, 2),
                "actual_limit_up": False,
                "actual_limit_down": False,
            },
            {
                "date": date(2024, 6, 3),
                "is_limit_up": False,
                "actual_limit_down": False,
            },
            {"date": date(2024, 6, 4), "is_limit_up": False, "actual_limit_down": True},
        ]

        report = validator.validate_accuracy("510300", predicted, actual)

        # 涨停: 1个TP, 1个FP, 2个TN
        assert report.limit_up_metrics.true_positives == 1
        assert report.limit_up_metrics.false_positives == 1
        assert report.limit_up_metrics.true_negatives == 2
        assert report.limit_up_metrics.false_negatives == 0
        assert report.limit_up_metrics.precision == pytest.approx(0.5)
        assert report.limit_up_metrics.accuracy == pytest.approx(0.75)

    def test_all_negative(self, validator: LimitAccuracyValidator) -> None:
        """测试全部为负样本的情况."""
        predicted = [
            {"date": date(2024, 6, 1), "is_limit_up": False, "is_limit_down": False},
            {"date": date(2024, 6, 2), "is_limit_up": False, "is_limit_down": False},
            {"date": date(2024, 6, 3), "is_limit_up": False, "is_limit_down": False},
        ]

        actual = [
            {
                "date": date(2024, 6, 1),
                "actual_limit_up": False,
                "actual_limit_down": False,
            },
            {
                "date": date(2024, 6, 2),
                "actual_limit_up": False,
                "actual_limit_down": False,
            },
            {
                "date": date(2024, 6, 3),
                "actual_limit_up": False,
                "actual_limit_down": False,
            },
        ]

        report = validator.validate_accuracy("510300", predicted, actual)

        # 全部正确预测为非涨停/跌停
        assert report.overall_metrics.accuracy == pytest.approx(1.0)
        assert report.overall_metrics.true_negatives == 6  # 涨停和跌停各3个
        assert report.overall_metrics.true_positives == 0

    def test_batch_validate_accuracy(self, validator: LimitAccuracyValidator) -> None:
        """测试批量验证."""
        symbols_data = {
            "510300": {
                "predicted": [
                    {
                        "date": date(2024, 6, 1),
                        "is_limit_up": True,
                        "is_limit_down": False,
                    },
                ],
                "actual": [
                    {
                        "date": date(2024, 6, 1),
                        "actual_limit_up": True,
                        "actual_limit_down": False,
                    },
                ],
            },
            "159915": {
                "predicted": [
                    {
                        "date": date(2024, 6, 1),
                        "is_limit_up": False,
                        "is_limit_down": True,
                    },
                ],
                "actual": [
                    {
                        "date": date(2024, 6, 1),
                        "actual_limit_up": False,
                        "actual_limit_down": False,
                    },
                ],
            },
        }

        reports = validator.batch_validate_accuracy(symbols_data)

        assert len(reports) == 2
        assert "510300" in reports
        assert "159915" in reports

        # 510300应该有100%准确率
        assert reports["510300"].overall_metrics.accuracy == pytest.approx(1.0)

        # 159915应该有误报
        assert reports["159915"].overall_metrics.accuracy < 1.0

    def test_generate_summary_report(self, validator: LimitAccuracyValidator) -> None:
        """测试生成汇总报告."""
        # 创建多个报告
        reports = {
            "510300": validator.validate_accuracy(
                "510300",
                [
                    {
                        "date": date(2024, 6, 1),
                        "is_limit_up": True,
                        "is_limit_down": False,
                    }
                ],
                [
                    {
                        "date": date(2024, 6, 1),
                        "actual_limit_up": True,
                        "actual_limit_down": False,
                    }
                ],
            ),
            "159915": validator.validate_accuracy(
                "159915",
                [
                    {
                        "date": date(2024, 6, 1),
                        "is_limit_up": False,
                        "is_limit_down": False,
                    }
                ],
                [
                    {
                        "date": date(2024, 6, 1),
                        "actual_limit_up": False,
                        "actual_limit_down": False,
                    }
                ],
            ),
        }

        summary = validator.generate_summary_report(reports)

        assert summary["total_symbols"] == 2
        assert summary["average_accuracy"] == pytest.approx(1.0)
        assert "best_performing_symbol" in summary
        assert "worst_performing_symbol" in summary

    def test_empty_data(self, validator: LimitAccuracyValidator) -> None:
        """测试空数据情况."""
        report = validator.validate_accuracy("510300", [], [])

        assert report.symbol == "510300"
        assert report.overall_metrics.total_samples == 0

        summary = validator.generate_summary_report({})
        assert "message" in summary

    def test_misaligned_dates(self, validator: LimitAccuracyValidator) -> None:
        """测试日期不对齐的情况."""
        predicted = [
            {"date": date(2024, 6, 1), "is_limit_up": True, "is_limit_down": False},
            {
                "date": date(2024, 6, 3),
                "is_limit_up": False,
                "is_limit_down": True,
            },  # 缺少6-02
        ]

        actual = [
            {
                "date": date(2024, 6, 1),
                "actual_limit_up": True,
                "actual_limit_down": False,
            },
            {
                "date": date(2024, 6, 2),
                "actual_limit_up": False,
                "actual_limit_down": False,
            },  # 缺少6-03
        ]

        report = validator.validate_accuracy("510300", predicted, actual)

        # 应该正确处理不对齐的日期
        assert len(report.detailed_results) == 3  # 合并后的总记录数

    def test_accuracy_metrics_calculation(self) -> None:
        """测试准确率指标计算."""
        # 测试标准情况
        metrics = AccuracyMetrics(
            total_samples=100,
            true_positives=20,
            false_positives=10,
            true_negatives=60,
            false_negatives=10,
        )

        # 验证计算结果
        assert metrics.precision == pytest.approx(0.6666667)  # 20/(20+10)
        assert metrics.recall == pytest.approx(0.6666667)  # 20/(20+10)
        assert metrics.accuracy == pytest.approx(0.8)  # (20+60)/100

    def test_edge_cases(self, validator: LimitAccuracyValidator) -> None:
        """测试边界情况."""
        # 只有正样本且全部正确
        predicted = [
            {"date": date(2024, 6, 1), "is_limit_up": True, "is_limit_down": False},
        ]
        actual = [
            {
                "date": date(2024, 6, 1),
                "actual_limit_up": True,
                "actual_limit_down": False,
            },
        ]

        report = validator.validate_accuracy("510300", predicted, actual)
        assert report.limit_up_metrics.precision == pytest.approx(1.0)
        assert report.limit_up_metrics.recall == pytest.approx(1.0)

        # 只有负样本且全部正确
        predicted = [
            {"date": date(2024, 6, 1), "is_limit_up": False, "is_limit_down": False},
        ]
        actual = [
            {
                "date": date(2024, 6, 1),
                "actual_limit_up": False,
                "actual_limit_down": False,
            },
        ]

        report = validator.validate_accuracy("510300", predicted, actual)
        assert report.limit_up_metrics.precision == 0.0  # 没有正样本预测
        assert report.limit_up_metrics.recall == 0.0  # 没有正样本实际
