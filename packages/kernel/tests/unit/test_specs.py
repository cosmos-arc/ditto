"""ditto_kernel.specs 单元测试."""

from __future__ import annotations

import pytest
from ditto_features.derived_types import (
    DerivedRole,
    DerivedSpec,
    MaterializationProfile,
)
from ditto_kernel.market import (
    CALENDAR_TO_TIMEZONE,
    GRAIN_TO_TIME_KEYS,
    TimeSpec,
)
from ditto_kernel.strategy import ExecutionPolicy

# ---------------------------------------------------------------------------
# DerivedRole
# ---------------------------------------------------------------------------


class TestDerivedRole:
    """DerivedRole 枚举测试."""

    def test_members(self) -> None:
        """应包含 4 个成员."""
        assert len(DerivedRole) == 4

    def test_values(self) -> None:
        """验证所有成员值."""
        assert DerivedRole.FEATURE == "feature"
        assert DerivedRole.FACTOR == "factor"
        assert DerivedRole.SIGNAL == "signal"
        assert DerivedRole.LABEL == "label"

    def test_is_strenum(self) -> None:
        """应为 StrEnum，支持直接字符串比较."""
        assert DerivedRole.FEATURE == "feature"

    def test_iteration(self) -> None:
        """枚举可迭代且包含全部成员."""
        members = list(DerivedRole)
        assert len(members) == 4
        assert DerivedRole.FEATURE in members
        assert DerivedRole.FACTOR in members
        assert DerivedRole.SIGNAL in members
        assert DerivedRole.LABEL in members

    def test_value_to_member(self) -> None:
        """可通过 value 反查成员."""
        assert DerivedRole("feature") is DerivedRole.FEATURE
        assert DerivedRole("factor") is DerivedRole.FACTOR

    def test_invalid_value_raises(self) -> None:
        """无效值应抛出 ValueError."""
        with pytest.raises(ValueError):
            DerivedRole("unknown")


# ---------------------------------------------------------------------------
# MaterializationProfile
# ---------------------------------------------------------------------------


class TestMaterializationProfile:
    """MaterializationProfile 枚举测试."""

    def test_members(self) -> None:
        """应包含 4 个成员."""
        assert len(MaterializationProfile) == 4

    def test_values(self) -> None:
        """验证所有成员值（大写）."""
        assert MaterializationProfile.SERIES == "SERIES"
        assert MaterializationProfile.STATE == "STATE"
        assert MaterializationProfile.DERIVE == "DERIVE"
        assert MaterializationProfile.OFFLINE == "OFFLINE"

    def test_is_strenum(self) -> None:
        """应为 StrEnum，支持直接字符串比较."""
        assert MaterializationProfile.SERIES == "SERIES"

    def test_invalid_value_raises(self) -> None:
        """无效值应抛出 ValueError."""
        with pytest.raises(ValueError):
            MaterializationProfile("REALTIME")


# ---------------------------------------------------------------------------
# 模块级常量
# ---------------------------------------------------------------------------


class TestGrainToTimeKeys:
    """GRAIN_TO_TIME_KEYS 映射测试."""

    def test_keys(self) -> None:
        """应包含 1d 和 1m 两个 grain."""
        assert set(GRAIN_TO_TIME_KEYS.keys()) == {"1d", "1m"}

    def test_daily_grain(self) -> None:
        """1d grain 应包含 trade_date."""
        assert GRAIN_TO_TIME_KEYS["1d"] == ("trade_date",)

    def test_minute_grain(self) -> None:
        """1m grain 应包含 trade_date 和 bar_time."""
        assert GRAIN_TO_TIME_KEYS["1m"] == ("trade_date", "bar_time")


class TestCalendarToTimezone:
    """CALENDAR_TO_TIMEZONE 映射测试."""

    def test_cn_stock(self) -> None:
        """cn_stock 应映射到 Asia/Shanghai."""
        assert CALENDAR_TO_TIMEZONE["cn_stock"] == "Asia/Shanghai"

    def test_only_cn_stock(self) -> None:
        """当前仅支持 cn_stock 日历."""
        assert set(CALENDAR_TO_TIMEZONE.keys()) == {"cn_stock"}


# ---------------------------------------------------------------------------
# TimeSpec
# ---------------------------------------------------------------------------


class TestTimeSpec:
    """TimeSpec frozen dataclass 测试."""

    def test_required_field(self) -> None:
        """event_time_key 为必填字段."""
        spec = TimeSpec(event_time_key="trade_date")
        assert spec.event_time_key == "trade_date"

    def test_availability_time_key_default_none(self) -> None:
        """availability_time_key 默认为 None."""
        spec = TimeSpec(event_time_key="trade_date")
        assert spec.availability_time_key is None

    def test_all_fields(self) -> None:
        """所有字段正确赋值."""
        spec = TimeSpec(event_time_key="trade_date", availability_time_key="bar_time")
        assert spec.event_time_key == "trade_date"
        assert spec.availability_time_key == "bar_time"

    def test_frozen(self) -> None:
        """frozen dataclass 不可变."""
        spec = TimeSpec(event_time_key="trade_date")
        with pytest.raises(AttributeError):
            spec.event_time_key = "changed"  # type: ignore[misc]

    def test_equality(self) -> None:
        """相同字段值的两个实例应相等."""
        a = TimeSpec(event_time_key="trade_date", availability_time_key="bar_time")
        b = TimeSpec(event_time_key="trade_date", availability_time_key="bar_time")
        assert a == b

    def test_inequality(self) -> None:
        """不同字段值应不等."""
        a = TimeSpec(event_time_key="trade_date")
        b = TimeSpec(event_time_key="bar_time")
        assert a != b


# ---------------------------------------------------------------------------
# ExecutionPolicy
# ---------------------------------------------------------------------------


class TestExecutionPolicy:
    """ExecutionPolicy frozen dataclass 测试."""

    def test_defaults(self) -> None:
        """默认值: pit_required=True, preset='default', adj_type='none'."""
        policy = ExecutionPolicy()
        assert policy.pit_required is True
        assert policy.normalization_preset == "default"
        assert policy.adj_type == "none"

    def test_custom_values(self) -> None:
        """自定义值正确赋值."""
        policy = ExecutionPolicy(
            pit_required=False,
            normalization_preset="zscore",
            adj_type="qfq",
        )
        assert policy.pit_required is False
        assert policy.normalization_preset == "zscore"
        assert policy.adj_type == "qfq"

    def test_frozen(self) -> None:
        """frozen dataclass 不可变."""
        policy = ExecutionPolicy()
        with pytest.raises(AttributeError):
            policy.pit_required = False  # type: ignore[misc]

    def test_equality(self) -> None:
        """相同字段值的两个实例应相等."""
        a = ExecutionPolicy()
        b = ExecutionPolicy()
        assert a == b

    def test_inequality(self) -> None:
        """不同字段值应不等."""
        a = ExecutionPolicy(pit_required=True)
        b = ExecutionPolicy(pit_required=False)
        assert a != b


# ---------------------------------------------------------------------------
# DerivedSpec
# ---------------------------------------------------------------------------


class TestDerivedSpec:
    """DerivedSpec frozen dataclass 测试."""

    def _make_spec(self, **overrides: object) -> DerivedSpec:
        """构造最小有效 DerivedSpec."""
        base = {
            "id": "test_factor",
            "version": 1,
            "role": DerivedRole.FACTOR,
            "materialization_profile": MaterializationProfile.SERIES,
            "expression": "close / close.shift(1)",
        }
        base.update(overrides)
        return DerivedSpec(**base)  # type: ignore[arg-type]

    def test_required_fields(self) -> None:
        """必填字段正确赋值."""
        spec = self._make_spec()
        assert spec.id == "test_factor"
        assert spec.version == 1
        assert spec.role is DerivedRole.FACTOR
        assert spec.materialization_profile is MaterializationProfile.SERIES
        assert spec.expression == "close / close.shift(1)"

    def test_entity_keys_default(self) -> None:
        """entity_keys 默认为 ('instrument_id',)."""
        spec = self._make_spec()
        assert spec.entity_keys == ("instrument_id",)

    def test_grain_default(self) -> None:
        """grain 默认为 '1d'."""
        spec = self._make_spec()
        assert spec.grain == "1d"

    def test_time_keys_default_none(self) -> None:
        """time_keys 默认为 None."""
        spec = self._make_spec()
        assert spec.time_keys is None

    def test_calendar_default(self) -> None:
        """calendar 默认为 'cn_stock'."""
        spec = self._make_spec()
        assert spec.calendar == "cn_stock"

    def test_description_default_none(self) -> None:
        """description 默认为 None."""
        spec = self._make_spec()
        assert spec.description is None

    def test_time_spec_default_none(self) -> None:
        """time_spec 默认为 None."""
        spec = self._make_spec()
        assert spec.time_spec is None

    def test_operator_versions_default_empty(self) -> None:
        """operator_versions 默认为空字典."""
        spec = self._make_spec()
        assert spec.operator_versions == {}

    def test_universe_id_default_none(self) -> None:
        """universe_id 默认为 None."""
        spec = self._make_spec()
        assert spec.universe_id is None

    def test_execution_policy_default(self) -> None:
        """execution_policy 默认为 ExecutionPolicy()."""
        spec = self._make_spec()
        assert spec.execution_policy == ExecutionPolicy()

    def test_all_fields_custom(self) -> None:
        """所有字段自定义赋值."""
        time_spec = TimeSpec(event_time_key="bar_time")
        policy = ExecutionPolicy(pit_required=False, adj_type="hfq")
        spec = self._make_spec(
            entity_keys=("instrument_id", "sector"),
            grain="1m",
            time_keys=("trade_date", "bar_time"),
            calendar="cn_stock",
            description="分钟级因子",
            time_spec=time_spec,
            operator_versions={"ma": "2.0"},
            universe_id="hs300",
            execution_policy=policy,
        )
        assert spec.entity_keys == ("instrument_id", "sector")
        assert spec.grain == "1m"
        assert spec.time_keys == ("trade_date", "bar_time")
        assert spec.description == "分钟级因子"
        assert spec.time_spec is time_spec
        assert spec.operator_versions == {"ma": "2.0"}
        assert spec.universe_id == "hs300"
        assert spec.execution_policy is policy

    def test_frozen(self) -> None:
        """frozen dataclass 不可变."""
        spec = self._make_spec()
        with pytest.raises(AttributeError):
            spec.id = "changed"  # type: ignore[misc]

    def test_equality(self) -> None:
        """相同字段值的两个实例应相等."""
        a = self._make_spec()
        b = self._make_spec()
        assert a == b

    def test_inequality(self) -> None:
        """不同字段值应不等."""
        a = self._make_spec()
        b = self._make_spec(id="other_factor")
        assert a != b

    def test_entity_keys_default_is_independent(self) -> None:
        """每个实例的 entity_keys 默认值应是独立元组."""
        a = self._make_spec()
        b = self._make_spec()
        # tuple 是不可变的，但 default_factory 确保每次创建新实例
        assert a.entity_keys == b.entity_keys

    def test_operator_versions_default_is_independent(self) -> None:
        """每个实例的 operator_versions 默认值应是独立字典."""
        a = self._make_spec()
        b = self._make_spec()
        assert a.operator_versions is not b.operator_versions


class TestDerivedSpecEffectiveTimeKeys:
    """DerivedSpec.effective_time_keys 属性测试."""

    def _make_spec(self, **overrides: object) -> DerivedSpec:
        base = {
            "id": "test",
            "version": 1,
            "role": DerivedRole.FACTOR,
            "materialization_profile": MaterializationProfile.SERIES,
            "expression": "expr",
        }
        base.update(overrides)
        return DerivedSpec(**base)  # type: ignore[arg-type]

    def test_daily_grain_default(self) -> None:
        """grain=1d 且无显式 time_keys 时，使用 GRAIN_TO_TIME_KEYS['1d']."""
        spec = self._make_spec()
        assert spec.effective_time_keys == ("trade_date",)

    def test_minute_grain_default(self) -> None:
        """grain=1m 且无显式 time_keys 时，使用 GRAIN_TO_TIME_KEYS['1m']."""
        spec = self._make_spec(grain="1m")
        assert spec.effective_time_keys == ("trade_date", "bar_time")

    def test_explicit_time_keys_override(self) -> None:
        """显式 time_keys 优先于 grain-derived 默认."""
        spec = self._make_spec(grain="1d", time_keys=("custom_key",))
        assert spec.effective_time_keys == ("custom_key",)

    def test_explicit_time_keys_with_minute_grain(self) -> None:
        """显式 time_keys 在任意 grain 下都优先."""
        spec = self._make_spec(grain="1m", time_keys=("ts",))
        assert spec.effective_time_keys == ("ts",)


class TestDerivedSpecTimezone:
    """DerivedSpec.timezone 属性测试."""

    def _make_spec(self, **overrides: object) -> DerivedSpec:
        base = {
            "id": "test",
            "version": 1,
            "role": DerivedRole.FACTOR,
            "materialization_profile": MaterializationProfile.SERIES,
            "expression": "expr",
        }
        base.update(overrides)
        return DerivedSpec(**base)  # type: ignore[arg-type]

    def test_cn_stock_calendar(self) -> None:
        """calendar='cn_stock' 应返回 Asia/Shanghai."""
        spec = self._make_spec()
        assert spec.timezone == "Asia/Shanghai"

    def test_timezone_consistent_with_constant(self) -> None:
        """timezone 属性应与 CALENDAR_TO_TIMEZONE 常量一致."""
        spec = self._make_spec()
        assert spec.timezone == CALENDAR_TO_TIMEZONE["cn_stock"]
