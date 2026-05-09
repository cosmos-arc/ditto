"""Kernel frozen dataclass 纯计算 @property 测试 — TDD RED 阶段.

测试 5 个新增 property:
1. InstrumentIngestParams.has_identifier
2. InstrumentIngestParams.primary_identifier
3. TimeSpec.has_availability_time
4. ExecutionPolicy.is_pit_mode
5. DQIssue.is_error
"""

from __future__ import annotations

from ditto_data.quality.kernel_types import DQIssue, DQLevel, DQSeverity
from ditto_kernel.instrument import InstrumentIngestParams
from ditto_kernel.market import TimeSpec
from ditto_kernel.strategy import ExecutionPolicy

# ---------------------------------------------------------------------------
# InstrumentIngestParams.has_identifier
# ---------------------------------------------------------------------------


class TestInstrumentIngestParamsHasIdentifier:
    """InstrumentIngestParams.has_identifier -> bool."""

    def test_all_none_returns_false(self) -> None:
        """三个标识符均为 None 时返回 False."""
        params = InstrumentIngestParams()
        assert params.has_identifier is False

    def test_with_instrument_id(self) -> None:
        """仅 instrument_id 非空时返回 True."""
        params = InstrumentIngestParams(instrument_id=1)
        assert params.has_identifier is True

    def test_with_standard_ticker(self) -> None:
        """仅 standard_ticker 非空时返回 True."""
        params = InstrumentIngestParams(standard_ticker="000001.XSHE")
        assert params.has_identifier is True

    def test_with_ticker(self) -> None:
        """仅 ticker 非空时返回 True."""
        params = InstrumentIngestParams(ticker="000001")
        assert params.has_identifier is True

    def test_with_instrument_id_and_standard_ticker(self) -> None:
        """多个标识符非空时返回 True."""
        params = InstrumentIngestParams(instrument_id=1, standard_ticker="000001.XSHE")
        assert params.has_identifier is True

    def test_with_all_identifiers(self) -> None:
        """三个标识符全部非空时返回 True."""
        params = InstrumentIngestParams(
            instrument_id=1,
            standard_ticker="000001.XSHE",
            ticker="000001",
        )
        assert params.has_identifier is True


# ---------------------------------------------------------------------------
# InstrumentIngestParams.primary_identifier
# ---------------------------------------------------------------------------


class TestInstrumentIngestParamsPrimaryIdentifier:
    """InstrumentIngestParams.primary_identifier -> str | None."""

    def test_all_none_returns_none(self) -> None:
        """三个标识符均为 None 时返回 None."""
        params = InstrumentIngestParams()
        assert params.primary_identifier is None

    def test_with_instrument_id_only(self) -> None:
        """仅 instrument_id 时返回 str(instrument_id)."""
        params = InstrumentIngestParams(instrument_id=1_000_001)
        assert params.primary_identifier == "1000001"

    def test_with_standard_ticker_only(self) -> None:
        """仅 standard_ticker 时返回该值."""
        params = InstrumentIngestParams(standard_ticker="000001.XSHE")
        assert params.primary_identifier == "000001.XSHE"

    def test_with_ticker_only(self) -> None:
        """仅 ticker 时返回该值."""
        params = InstrumentIngestParams(ticker="000001")
        assert params.primary_identifier == "000001"

    def test_priority_instrument_id_over_standard_ticker(self) -> None:
        """instrument_id 优先于 standard_ticker."""
        params = InstrumentIngestParams(instrument_id=42, standard_ticker="000001.XSHE")
        assert params.primary_identifier == "42"

    def test_priority_instrument_id_over_ticker(self) -> None:
        """instrument_id 优先于 ticker."""
        params = InstrumentIngestParams(instrument_id=42, ticker="000001")
        assert params.primary_identifier == "42"

    def test_priority_standard_ticker_over_ticker(self) -> None:
        """standard_ticker 优先于 ticker（当 instrument_id 为 None 时）."""
        params = InstrumentIngestParams(standard_ticker="000001.XSHE", ticker="000001")
        assert params.primary_identifier == "000001.XSHE"

    def test_priority_order_with_all_set(self) -> None:
        """三个标识符全部设置时，instrument_id 优先级最高."""
        params = InstrumentIngestParams(
            instrument_id=99,
            standard_ticker="000001.XSHE",
            ticker="000001",
        )
        assert params.primary_identifier == "99"

    def test_instrument_id_zero_is_valid(self) -> None:
        """instrument_id=0 仍为非 None，应被视为有效标识符."""
        params = InstrumentIngestParams(instrument_id=0)
        assert params.primary_identifier == "0"


# ---------------------------------------------------------------------------
# TimeSpec.has_availability_time
# ---------------------------------------------------------------------------


class TestTimeSpecHasAvailabilityTime:
    """TimeSpec.has_availability_time -> bool."""

    def test_with_none_returns_false(self) -> None:
        """availability_time_key 为 None 时返回 False."""
        spec = TimeSpec(event_time_key="trade_date")
        assert spec.has_availability_time is False

    def test_with_value_returns_true(self) -> None:
        """availability_time_key 有值时返回 True."""
        spec = TimeSpec(event_time_key="trade_date", availability_time_key="bar_time")
        assert spec.has_availability_time is True

    def test_with_empty_string_returns_true(self) -> None:
        """availability_time_key 为空字符串时仍返回 True（非 None 即视为已设置）."""
        spec = TimeSpec(event_time_key="trade_date", availability_time_key="")
        assert spec.has_availability_time is True


# ---------------------------------------------------------------------------
# ExecutionPolicy.is_pit_mode
# ---------------------------------------------------------------------------


class TestExecutionPolicyIsPitMode:
    """ExecutionPolicy.is_pit_mode -> bool (pit_required 的语义别名)."""

    def test_default_returns_true(self) -> None:
        """默认构造时 pit_required=True，is_pit_mode 应为 True."""
        policy = ExecutionPolicy()
        assert policy.is_pit_mode is True

    def test_pit_required_true(self) -> None:
        """显式设置 pit_required=True 时返回 True."""
        policy = ExecutionPolicy(pit_required=True)
        assert policy.is_pit_mode is True

    def test_pit_required_false(self) -> None:
        """显式设置 pit_required=False 时返回 False."""
        policy = ExecutionPolicy(pit_required=False)
        assert policy.is_pit_mode is False

    def test_mirrors_pit_required(self) -> None:
        """is_pit_mode 应始终与 pit_required 一致."""
        for pit_val in (True, False):
            policy = ExecutionPolicy(pit_required=pit_val)
            assert policy.is_pit_mode is policy.pit_required


# ---------------------------------------------------------------------------
# DQIssue.is_error
# ---------------------------------------------------------------------------


class TestDQIssueIsError:
    """DQIssue.is_error -> bool."""

    def test_severity_error_returns_true(self) -> None:
        """severity 为 ERROR 时返回 True."""
        issue = DQIssue(
            level=DQLevel.TECHNICAL,
            severity=DQSeverity.ERROR,
            rule_name="not_null",
            message="空值",
        )
        assert issue.is_error is True

    def test_severity_warning_returns_false(self) -> None:
        """severity 为 WARNING 时返回 False."""
        issue = DQIssue(
            level=DQLevel.BUSINESS,
            severity=DQSeverity.WARNING,
            rule_name="ohlc_invariant",
            message="OHLC 不变式违反",
        )
        assert issue.is_error is False

    def test_severity_alert_returns_false(self) -> None:
        """severity 为 ALERT 时返回 False."""
        issue = DQIssue(
            level=DQLevel.STATISTICAL,
            severity=DQSeverity.ALERT,
            rule_name="z_score",
            message="异常值",
        )
        assert issue.is_error is False

    def test_consistent_with_severity_comparison(self) -> None:
        """is_error 应与 severity == DQSeverity.ERROR 一致."""
        for severity in list(DQSeverity):
            issue = DQIssue(
                level=DQLevel.TECHNICAL,
                severity=severity,
                rule_name="r",
                message="m",
            )
            assert issue.is_error is (severity == DQSeverity.ERROR)
