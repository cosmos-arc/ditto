"""Tests for strategy/validation.py — validate_spec_params.

校验函数对非法参数抛出 ValueError，对合法参数静默通过。
"""

from __future__ import annotations

import pytest
from ditto_strategy.alpha.specs import (
    ParamConstraint,
    StrategySpec,
)
from ditto_strategy.alpha.validation import validate_spec_params


def _make_spec(
    params: dict[str, object],
    constraints: tuple[ParamConstraint, ...] = (),
) -> StrategySpec:
    """构造测试用 StrategySpec。"""
    return StrategySpec(
        strategy_id="test_strategy",
        name="Test Strategy",
        template="etf_rotation",
        universe="cn_etf",
        asset_class="etf",
        params=params,
        param_constraints=constraints,
    )


class TestValidateSpecParamsValid:
    """合法参数 — validate_spec_params 不抛异常。"""

    def test_valid_spec_no_constraints(self) -> None:
        """无约束时，任何参数都通过。"""
        spec = _make_spec(params={"lookback": 252})
        validate_spec_params(spec)  # 不应抛异常

    def test_valid_spec_all_constraints_pass(self) -> None:
        """所有约束都满足。"""
        constraints = (
            ParamConstraint(name="lookback", dtype="int", min_value=10, max_value=500),
            ParamConstraint(name="method", dtype="str", allowed_values=("a", "b")),
            ParamConstraint(
                name="threshold",
                dtype="float",
                min_value=0.0,
                max_value=1.0,
            ),
        )
        spec = _make_spec(
            params={"lookback": 252, "method": "a", "threshold": 0.5},
            constraints=constraints,
        )
        validate_spec_params(spec)  # 不应抛异常

    def test_int_accepted_as_float(self) -> None:
        """int 可以作为 float（Python 数值兼容）。"""
        constraints = (ParamConstraint(name="threshold", dtype="float"),)
        spec = _make_spec(params={"threshold": 1}, constraints=constraints)
        validate_spec_params(spec)  # 不应抛异常

    def test_numeric_at_boundary(self) -> None:
        """数值在边界上应通过。"""
        constraints = (
            ParamConstraint(name="val", dtype="float", min_value=0.0, max_value=1.0),
        )
        spec = _make_spec(params={"val": 0.0}, constraints=constraints)
        validate_spec_params(spec)
        spec = _make_spec(params={"val": 1.0}, constraints=constraints)
        validate_spec_params(spec)

    def test_enum_value_valid(self) -> None:
        """枚举值在允许列表内。"""
        constraints = (
            ParamConstraint(name="method", dtype="str", allowed_values=("a", "b")),
        )
        spec = _make_spec(params={"method": "a"}, constraints=constraints)
        validate_spec_params(spec)  # 不应抛异常

    def test_no_allowed_values_means_any_str_ok(self) -> None:
        """没有 allowed_values 时，任意 str 都通过。"""
        constraints = (ParamConstraint(name="name", dtype="str"),)
        spec = _make_spec(params={"name": "anything"}, constraints=constraints)
        validate_spec_params(spec)  # 不应抛异常


class TestValidateSpecParamsMissingRequired:
    """缺少必填参数 — 抛 ValueError。"""

    def test_missing_required_param(self) -> None:
        """缺少必填参数。"""
        constraints = (ParamConstraint(name="lookback", dtype="int"),)
        spec = _make_spec(params={}, constraints=constraints)
        with pytest.raises(ValueError, match=r"缺少必填参数.*lookback"):
            validate_spec_params(spec)

    def test_missing_multiple_params_reports_first(self) -> None:
        """缺少多个必填参数时，抛出异常包含第一个缺失参数信息。"""
        constraints = (
            ParamConstraint(name="a", dtype="int"),
            ParamConstraint(name="b", dtype="str"),
        )
        spec = _make_spec(params={}, constraints=constraints)
        with pytest.raises(ValueError, match="缺少必填参数"):
            validate_spec_params(spec)


class TestValidateSpecParamsWrongType:
    """参数类型错误 — 抛 ValueError。"""

    def test_wrong_type_int(self) -> None:
        """int 参数传入字符串。"""
        constraints = (ParamConstraint(name="lookback", dtype="int"),)
        spec = _make_spec(params={"lookback": "abc"}, constraints=constraints)
        with pytest.raises(ValueError, match=r"lookback.*类型错误"):
            validate_spec_params(spec)

    def test_wrong_type_float(self) -> None:
        """float 参数传入字符串。"""
        constraints = (ParamConstraint(name="threshold", dtype="float"),)
        spec = _make_spec(params={"threshold": "x"}, constraints=constraints)
        with pytest.raises(ValueError, match=r"threshold.*类型错误"):
            validate_spec_params(spec)

    def test_wrong_type_str(self) -> None:
        """str 参数传入整数。"""
        constraints = (ParamConstraint(name="method", dtype="str"),)
        spec = _make_spec(params={"method": 123}, constraints=constraints)
        with pytest.raises(ValueError, match=r"method.*类型错误"):
            validate_spec_params(spec)

    def test_bool_not_accepted_as_int(self) -> None:
        """bool 不被接受为 int（Python 中 bool 是 int 子类）。"""
        constraints = (ParamConstraint(name="flag", dtype="int"),)
        spec = _make_spec(params={"flag": True}, constraints=constraints)
        with pytest.raises(ValueError, match="类型错误"):
            validate_spec_params(spec)


class TestValidateSpecParamsOutOfRange:
    """数值越界 — 抛 ValueError。"""

    def test_numeric_below_min(self) -> None:
        """数值低于最小值。"""
        constraints = (ParamConstraint(name="lookback", dtype="int", min_value=10),)
        spec = _make_spec(params={"lookback": 5}, constraints=constraints)
        with pytest.raises(ValueError, match="小于最小值"):
            validate_spec_params(spec)

    def test_numeric_above_max(self) -> None:
        """数值高于最大值。"""
        constraints = (ParamConstraint(name="lookback", dtype="int", max_value=100),)
        spec = _make_spec(params={"lookback": 200}, constraints=constraints)
        with pytest.raises(ValueError, match="大于最大值"):
            validate_spec_params(spec)


class TestValidateSpecParamsInvalidEnum:
    """枚举值不在允许列表内 — 抛 ValueError。"""

    def test_enum_value_invalid(self) -> None:
        """枚举值不在允许列表内。"""
        constraints = (
            ParamConstraint(name="method", dtype="str", allowed_values=("a", "b")),
        )
        spec = _make_spec(params={"method": "c"}, constraints=constraints)
        with pytest.raises(ValueError, match="值无效"):
            validate_spec_params(spec)


class TestValidateSpecParamsEarlyExit:
    """类型错误时不再检查范围约束（短路行为）。"""

    def test_type_error_skips_range_check(self) -> None:
        """类型错误时不再进行范围检查。"""
        constraints = (ParamConstraint(name="lookback", dtype="int", min_value=10),)
        spec = _make_spec(params={"lookback": "bad"}, constraints=constraints)
        # 应只报类型错误，不应包含范围错误
        with pytest.raises(ValueError, match="类型错误") as exc_info:
            validate_spec_params(spec)
        msg = str(exc_info.value)
        assert "小于最小值" not in msg
