"""ditto_kernel.quality 单元测试."""

from __future__ import annotations

import pytest
from ditto_kernel.quality import DQIssue, DQLevel, DQResult, DQSeverity

# ---------------------------------------------------------------------------
# DQLevel
# ---------------------------------------------------------------------------


class TestDQLevel:
    """DQLevel 枚举测试."""

    def test_members(self) -> None:
        """应包含 3 个成员."""
        assert len(DQLevel) == 3

    def test_values(self) -> None:
        """验证所有成员值（普通 Enum，需通过 .value 比较）."""
        assert DQLevel.TECHNICAL.value == "technical"
        assert DQLevel.BUSINESS.value == "business"
        assert DQLevel.STATISTICAL.value == "statistical"

    def test_not_equal_to_plain_string(self) -> None:
        """DQLevel 是 Enum 而非 StrEnum，不等于纯字符串."""
        assert DQLevel.TECHNICAL != "technical"

    def test_iteration(self) -> None:
        """枚举可迭代且包含全部成员."""
        members = list(DQLevel)
        assert len(members) == 3
        assert DQLevel.TECHNICAL in members
        assert DQLevel.BUSINESS in members
        assert DQLevel.STATISTICAL in members

    def test_value_to_member(self) -> None:
        """可通过 value 反查成员."""
        assert DQLevel("technical") is DQLevel.TECHNICAL
        assert DQLevel("business") is DQLevel.BUSINESS
        assert DQLevel("statistical") is DQLevel.STATISTICAL

    def test_invalid_value_raises(self) -> None:
        """无效值应抛出 ValueError."""
        with pytest.raises(ValueError, match="unknown"):
            DQLevel("unknown")


# ---------------------------------------------------------------------------
# DQSeverity
# ---------------------------------------------------------------------------


class TestDQSeverity:
    """DQSeverity 枚举测试."""

    def test_members(self) -> None:
        """应包含 3 个成员."""
        assert len(DQSeverity) == 3

    def test_values(self) -> None:
        """验证所有成员值（普通 Enum，需通过 .value 比较）."""
        assert DQSeverity.ERROR.value == "error"
        assert DQSeverity.WARNING.value == "warning"
        assert DQSeverity.ALERT.value == "alert"

    def test_not_equal_to_plain_string(self) -> None:
        """DQSeverity 是 Enum 而非 StrEnum，不等于纯字符串."""
        assert DQSeverity.ERROR != "error"

    def test_iteration(self) -> None:
        """枚举可迭代且包含全部成员."""
        members = list(DQSeverity)
        assert len(members) == 3
        assert DQSeverity.ERROR in members

    def test_value_to_member(self) -> None:
        """可通过 value 反查成员."""
        assert DQSeverity("error") is DQSeverity.ERROR
        assert DQSeverity("warning") is DQSeverity.WARNING
        assert DQSeverity("alert") is DQSeverity.ALERT

    def test_invalid_value_raises(self) -> None:
        """无效值应抛出 ValueError."""
        with pytest.raises(ValueError, match="critical"):
            DQSeverity("critical")


# ---------------------------------------------------------------------------
# DQIssue
# ---------------------------------------------------------------------------


class TestDQIssue:
    """DQIssue frozen dataclass 测试."""

    def test_creation_defaults(self) -> None:
        """affected_rows 和 sample_data 应有默认值."""
        issue = DQIssue(
            level=DQLevel.TECHNICAL,
            severity=DQSeverity.ERROR,
            rule_name="not_null",
            message="列存在空值",
        )
        assert issue.affected_rows == 0
        assert issue.sample_data == []

    def test_creation_with_all_fields(self) -> None:
        """所有字段正确赋值."""
        sample = [{"col": "a", "value": None}]
        issue = DQIssue(
            level=DQLevel.BUSINESS,
            severity=DQSeverity.WARNING,
            rule_name="ohlc_invariant",
            message="OHLC 不变式违反",
            affected_rows=5,
            sample_data=sample,
        )
        assert issue.level is DQLevel.BUSINESS
        assert issue.severity is DQSeverity.WARNING
        assert issue.rule_name == "ohlc_invariant"
        assert issue.message == "OHLC 不变式违反"
        assert issue.affected_rows == 5
        assert issue.sample_data == sample

    def test_frozen(self) -> None:
        """frozen dataclass 不可变."""
        issue = DQIssue(
            level=DQLevel.STATISTICAL,
            severity=DQSeverity.ALERT,
            rule_name="z_score",
            message="异常值",
        )
        with pytest.raises(AttributeError):
            issue.rule_name = "changed"  # type: ignore[misc]

    def test_equality(self) -> None:
        """相同字段值的两个实例应相等."""
        a = DQIssue(
            level=DQLevel.TECHNICAL,
            severity=DQSeverity.ERROR,
            rule_name="not_null",
            message="空值",
            affected_rows=1,
        )
        b = DQIssue(
            level=DQLevel.TECHNICAL,
            severity=DQSeverity.ERROR,
            rule_name="not_null",
            message="空值",
            affected_rows=1,
        )
        assert a == b

    def test_inequality(self) -> None:
        """不同字段值应不等."""
        a = DQIssue(
            level=DQLevel.TECHNICAL,
            severity=DQSeverity.ERROR,
            rule_name="r1",
            message="m1",
        )
        b = DQIssue(
            level=DQLevel.BUSINESS,
            severity=DQSeverity.WARNING,
            rule_name="r2",
            message="m2",
        )
        assert a != b

    def test_sample_data_default_is_independent(self) -> None:
        """每个实例的 sample_data 默认值应是独立列表."""
        a = DQIssue(
            level=DQLevel.TECHNICAL,
            severity=DQSeverity.ERROR,
            rule_name="r",
            message="m",
        )
        b = DQIssue(
            level=DQLevel.TECHNICAL,
            severity=DQSeverity.ERROR,
            rule_name="r",
            message="m",
        )
        assert a.sample_data is not b.sample_data


# ---------------------------------------------------------------------------
# DQResult — 构造与属性
# ---------------------------------------------------------------------------


class TestDQResultConstruction:
    """DQResult 构造测试."""

    def test_defaults(self) -> None:
        """issues 默认为空列表."""
        result = DQResult(dataset="test_ds", passed=True)
        assert result.issues == []

    def test_passed_true(self) -> None:
        """passed=True 时基础属性正确."""
        result = DQResult(dataset="ds", passed=True)
        assert result.passed is True
        assert result.dataset == "ds"

    def test_passed_false(self) -> None:
        """passed=False 时基础属性正确."""
        result = DQResult(dataset="ds", passed=False)
        assert result.passed is False

    def test_frozen(self) -> None:
        """frozen dataclass 不可变."""
        result = DQResult(dataset="ds", passed=True)
        with pytest.raises(AttributeError):
            result.dataset = "other"  # type: ignore[misc]

    def test_issues_default_is_independent(self) -> None:
        """每个实例的 issues 默认值应是独立列表."""
        a = DQResult(dataset="a", passed=True)
        b = DQResult(dataset="b", passed=True)
        assert a.issues is not b.issues

    def test_with_issues(self) -> None:
        """传入 issues 列表正确赋值."""
        issues = [
            DQIssue(DQLevel.TECHNICAL, DQSeverity.ERROR, "r1", "m1"),
            DQIssue(DQLevel.BUSINESS, DQSeverity.WARNING, "r2", "m2"),
        ]
        result = DQResult(dataset="ds", passed=False, issues=issues)
        assert len(result.issues) == 2


class TestDQResultHasProperties:
    """DQResult has_errors / has_warnings / has_alerts 属性测试."""

    def _make_result(self, *severities: DQSeverity) -> DQResult:
        issues = [
            DQIssue(DQLevel.TECHNICAL, sev, f"rule_{i}", f"msg_{i}")
            for i, sev in enumerate(severities)
        ]
        return DQResult(dataset="ds", passed=len(severities) == 0, issues=issues)

    def test_no_issues(self) -> None:
        """无 issue 时所有 has_* 返回 False."""
        r = self._make_result()
        assert r.has_errors is False
        assert r.has_warnings is False
        assert r.has_alerts is False

    def test_has_errors_true(self) -> None:
        r = self._make_result(DQSeverity.ERROR)
        assert r.has_errors is True
        assert r.has_warnings is False
        assert r.has_alerts is False

    def test_has_warnings_true(self) -> None:
        r = self._make_result(DQSeverity.WARNING)
        assert r.has_errors is False
        assert r.has_warnings is True
        assert r.has_alerts is False

    def test_has_alerts_true(self) -> None:
        r = self._make_result(DQSeverity.ALERT)
        assert r.has_errors is False
        assert r.has_warnings is False
        assert r.has_alerts is True

    def test_mixed_severities(self) -> None:
        """混合严重级别时所有相关属性为 True."""
        r = self._make_result(DQSeverity.ERROR, DQSeverity.WARNING, DQSeverity.ALERT)
        assert r.has_errors is True
        assert r.has_warnings is True
        assert r.has_alerts is True


class TestDQResultCountProperties:
    """DQResult error_count / warn_count / alert_count / total_count 测试."""

    def _make_result(self, *severities: DQSeverity) -> DQResult:
        issues = [
            DQIssue(DQLevel.TECHNICAL, sev, f"rule_{i}", f"msg_{i}")
            for i, sev in enumerate(severities)
        ]
        return DQResult(dataset="ds", passed=len(severities) == 0, issues=issues)

    def test_empty(self) -> None:
        """无 issue 时所有计数为 0."""
        r = self._make_result()
        assert r.error_count == 0
        assert r.warn_count == 0
        assert r.alert_count == 0
        assert r.total_count == 0

    def test_single_error(self) -> None:
        r = self._make_result(DQSeverity.ERROR)
        assert r.error_count == 1
        assert r.warn_count == 0
        assert r.alert_count == 0
        assert r.total_count == 1

    def test_multiple_same_severity(self) -> None:
        """同级别多个 issue 计数正确."""
        w = DQSeverity.WARNING
        r = self._make_result(w, w, w)
        assert r.warn_count == 3
        assert r.error_count == 0
        assert r.alert_count == 0
        assert r.total_count == 3

    def test_mixed_severity_counts(self) -> None:
        """混合级别计数正确."""
        r = self._make_result(
            DQSeverity.ERROR,
            DQSeverity.ERROR,
            DQSeverity.WARNING,
            DQSeverity.ALERT,
            DQSeverity.ALERT,
            DQSeverity.ALERT,
        )
        assert r.error_count == 2
        assert r.warn_count == 1
        assert r.alert_count == 3
        assert r.total_count == 6


class TestDQResultEquality:
    """DQResult 相等性测试."""

    def test_equal(self) -> None:
        """相同字段值的两个实例应相等."""
        issues = [DQIssue(DQLevel.TECHNICAL, DQSeverity.ERROR, "r", "m")]
        a = DQResult(dataset="ds", passed=False, issues=issues)
        b = DQResult(dataset="ds", passed=False, issues=issues)
        assert a == b

    def test_not_equal_dataset(self) -> None:
        a = DQResult(dataset="a", passed=True)
        b = DQResult(dataset="b", passed=True)
        assert a != b

    def test_not_equal_passed(self) -> None:
        a = DQResult(dataset="ds", passed=True)
        b = DQResult(dataset="ds", passed=False)
        assert a != b
