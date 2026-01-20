"""测试 models/quality.py 中的 DQ 模型."""

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ditto_datahub.models.quality import (
        DatasetRules,
        DQIssue,
        DQLevel,
        DQResult,
        DQSeverity,
        DQSpec,
        NotNullRule,
        PositiveRule,
        RuleType,
    )

# [REVIEW] __init__.py，直接导入模块以避免循环导入
import importlib.util

# [REVIEW]
quality_file = (
    Path(__file__).parent.parent.parent.parent
    / "src"
    / "ditto_datahub"
    / "models"
    / "quality.py"
)
spec = importlib.util.spec_from_file_location(
    "quality",
    str(quality_file),
)
if spec is None:
    raise ImportError("Failed to load quality module")

quality_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(quality_module)

# [REVIEW]
DatasetRules = quality_module.DatasetRules
DQIssue = quality_module.DQIssue
DQLevel = quality_module.DQLevel
DQResult = quality_module.DQResult
DQSeverity = quality_module.DQSeverity
DQSpec = quality_module.DQSpec
NotNullRule = quality_module.NotNullRule
PositiveRule = quality_module.PositiveRule
RuleType = quality_module.RuleType


class TestDQLevel:
    """测试 DQLevel 枚举."""

    def test_should_have_three_levels(self) -> None:
        """应该有三个 DQ 级别."""
        assert DQLevel.L1_TECHNICAL.value == "l1_technical"
        assert DQLevel.L2_BUSINESS.value == "l2_business"
        assert DQLevel.L3_STATISTICAL.value == "l3_statistical"

    def test_should_have_three_members(self) -> None:
        """应该有三个成员."""
        assert len(DQLevel) == 3


class TestDQSeverity:
    """测试 DQSeverity 枚举."""

    def test_should_have_three_severity_levels(self) -> None:
        """应该有三个严重程度级别."""
        assert DQSeverity.ERROR.value == "error"
        assert DQSeverity.WARNING.value == "warning"
        assert DQSeverity.ALERT.value == "alert"

    def test_should_have_three_members(self) -> None:
        """应该有三个成员."""
        assert len(DQSeverity) == 3


class TestRuleType:
    """测试 RuleType 枚举."""

    def test_should_have_all_rule_types(self) -> None:
        """应该有所有规则类型."""
        assert RuleType.NOT_NULL.value == "not_null"
        assert RuleType.UNIQUE.value == "unique"
        assert RuleType.POSITIVE.value == "positive"
        assert RuleType.ZSCORE.value == "zscore"

    def test_should_be_string_enum(self) -> None:
        """应该是字符串枚举."""
        assert isinstance(RuleType.NOT_NULL.value, str)


class TestDQIssue:
    """测试 DQIssue dataclass."""

    def test_should_create_dq_issue(self) -> None:
        """应该能够创建 DQ 问题."""
        issue = DQIssue(
            level=DQLevel.L1_TECHNICAL,
            severity=DQSeverity.ERROR,
            rule_name="not_null",
            message="Column 'close' cannot be null",
            affected_rows=5,
        )
        assert issue.level == DQLevel.L1_TECHNICAL
        assert issue.severity == DQSeverity.ERROR
        assert issue.rule_name == "not_null"
        assert issue.message == "Column 'close' cannot be null"
        assert issue.affected_rows == 5
        assert issue.sample_data == []

    def test_should_create_dq_issue_with_sample_data(self) -> None:
        """应该能够创建带样本数据的 DQ 问题."""
        issue = DQIssue(
            level=DQLevel.L2_BUSINESS,
            severity=DQSeverity.WARNING,
            rule_name="positive",
            message="Column 'volume' should be positive",
            affected_rows=2,
            sample_data=[{"code": "000001", "volume": -100}],
        )
        assert issue.sample_data == [{"code": "000001", "volume": -100}]


class TestDQResult:
    """测试 DQResult dataclass."""

    def test_should_create_dq_result(self) -> None:
        """应该能够创建 DQ 结果."""
        result = DQResult(dataset="daily_bars", passed=True)
        assert result.dataset == "daily_bars"
        assert result.passed is True
        assert result.issues == []

    def test_should_create_dq_result_with_issues(self) -> None:
        """应该能够创建带问题的 DQ 结果."""
        issues = [
            DQIssue(
                level=DQLevel.L1_TECHNICAL,
                severity=DQSeverity.ERROR,
                rule_name="not_null",
                message="Column 'close' cannot be null",
                affected_rows=5,
            ),
            DQIssue(
                level=DQLevel.L2_BUSINESS,
                severity=DQSeverity.WARNING,
                rule_name="positive",
                message="Column 'volume' should be positive",
                affected_rows=2,
            ),
        ]
        result = DQResult(dataset="daily_bars", passed=False, issues=issues)
        assert result.dataset == "daily_bars"
        assert result.passed is False
        assert len(result.issues) == 2

    def test_should_count_errors(self) -> None:
        """应该能够统计错误数量."""
        issues = [
            DQIssue(
                level=DQLevel.L1_TECHNICAL,
                severity=DQSeverity.ERROR,
                rule_name="not_null",
                message="Error 1",
            ),
            DQIssue(
                level=DQLevel.L1_TECHNICAL,
                severity=DQSeverity.ERROR,
                rule_name="unique",
                message="Error 2",
            ),
            DQIssue(
                level=DQLevel.L2_BUSINESS,
                severity=DQSeverity.WARNING,
                rule_name="positive",
                message="Warning",
            ),
        ]
        result = DQResult(dataset="daily_bars", passed=False, issues=issues)
        assert result.error_count == 2
        assert result.warn_count == 1
        assert result.alert_count == 0
        assert result.total_count == 3

    def test_should_check_has_errors(self) -> None:
        """应该能够检查是否有错误."""
        issues = [
            DQIssue(
                level=DQLevel.L1_TECHNICAL,
                severity=DQSeverity.ERROR,
                rule_name="not_null",
                message="Error",
            ),
        ]
        result = DQResult(dataset="daily_bars", passed=False, issues=issues)
        assert result.has_errors is True
        assert result.has_warnings is False
        assert result.has_alerts is False

    def test_should_check_has_warnings(self) -> None:
        """应该能够检查是否有警告."""
        issues = [
            DQIssue(
                level=DQLevel.L2_BUSINESS,
                severity=DQSeverity.WARNING,
                rule_name="positive",
                message="Warning",
            ),
        ]
        result = DQResult(dataset="daily_bars", passed=True, issues=issues)
        assert result.has_errors is False
        assert result.has_warnings is True
        assert result.has_alerts is False

    def test_should_check_has_alerts(self) -> None:
        """应该能够检查是否有告警."""
        issues = [
            DQIssue(
                level=DQLevel.L3_STATISTICAL,
                severity=DQSeverity.ALERT,
                rule_name="zscore",
                message="Alert",
            ),
        ]
        result = DQResult(dataset="daily_bars", passed=True, issues=issues)
        assert result.has_errors is False
        assert result.has_warnings is False
        assert result.has_alerts is True


class TestDatasetRules:
    """测试 DatasetRules Pydantic 模型."""

    def test_should_create_dataset_rules(self) -> None:
        """应该能够创建数据集规则."""
        rules = DatasetRules(
            dataset="daily_bars",
            description="Daily OHLC bars",
        )
        assert rules.dataset == "daily_bars"
        assert rules.description == "Daily OHLC bars"
        assert rules.l1_technical == []
        assert rules.l2_business == []
        assert rules.l3_statistical == []

    def test_should_create_dataset_rules_with_rules(self) -> None:
        """应该能够创建带规则的数据集规则."""
        rules = DatasetRules(
            dataset="daily_bars",
            description="Daily OHLC bars",
            l1_technical=[{"rule": "not_null", "columns": ["close"]}],
            l2_business=[{"rule": "positive", "columns": ["volume"]}],
        )
        assert len(rules.l1_technical) == 1
        assert len(rules.l2_business) == 1
        assert rules.l1_technical[0]["rule"] == "not_null"
        assert rules.l2_business[0]["rule"] == "positive"


class TestDQSpec:
    """测试 DQSpec Pydantic 模型."""

    def test_should_create_dq_spec(self) -> None:
        """应该能够创建 DQ 规范."""
        spec = DQSpec()
        assert spec.datasets == {}

    def test_should_create_dq_spec_with_datasets(self) -> None:
        """应该能够创建带数据集的 DQ 规范."""
        dataset_rules = DatasetRules(
            dataset="daily_bars",
            description="Daily OHLC bars",
        )
        spec = DQSpec(datasets={"daily_bars": dataset_rules})
        assert len(spec.datasets) == 1
        assert "daily_bars" in spec.datasets

    def test_should_get_rules_for_dataset(self) -> None:
        """应该能够获取数据集的规则."""
        dataset_rules = DatasetRules(
            dataset="daily_bars",
            description="Daily OHLC bars",
        )
        spec = DQSpec(datasets={"daily_bars": dataset_rules})
        rules = spec.get_rules("daily_bars")
        assert rules is not None
        assert rules.dataset == "daily_bars"

    def test_should_return_none_for_unknown_dataset(self) -> None:
        """对于未知数据集应该返回 None."""
        spec = DQSpec()
        rules = spec.get_rules("unknown")
        assert rules is None

    def test_should_check_has_dataset(self) -> None:
        """应该能够检查是否有数据集规则."""
        dataset_rules = DatasetRules(
            dataset="daily_bars",
            description="Daily OHLC bars",
        )
        spec = DQSpec(datasets={"daily_bars": dataset_rules})
        assert spec.has_dataset("daily_bars") is True
        assert spec.has_dataset("unknown") is False


class TestNotNullRule:
    """测试 NotNullRule 规则."""

    def test_should_create_not_null_rule(self) -> None:
        """应该能够创建非空规则."""
        rule = NotNullRule(
            columns=["close", "volume"], message="Columns cannot be null"
        )
        assert rule.rule == RuleType.NOT_NULL
        assert rule.columns == ["close", "volume"]
        assert rule.message == "Columns cannot be null"


class TestPositiveRule:
    """测试 PositiveRule 规则."""

    def test_should_create_positive_rule(self) -> None:
        """应该能够创建正数规则."""
        rule = PositiveRule(
            columns=["volume", "amount"], message="Values must be positive"
        )
        assert rule.rule == RuleType.POSITIVE
        assert rule.columns == ["volume", "amount"]
        assert rule.message == "Values must be positive"
