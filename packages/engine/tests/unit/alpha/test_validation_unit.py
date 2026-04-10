"""Tests for strategy/validation.py — validate_spec_params."""

from __future__ import annotations

from ditto_engine.alpha.specs import (
    ParamConstraint,
    StrategySpec,
)
from ditto_engine.alpha.validation import validate_spec_params


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


class TestValidateSpecParams:
    def test_valid_spec_no_constraints(self) -> None:
        """无约束时，任何参数都通过。"""
        spec = _make_spec(params={"lookback": 252})
        assert validate_spec_params(spec) == []

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
        assert validate_spec_params(spec) == []

    def test_missing_required_param(self) -> None:
        """缺少必填参数。"""
        constraints = (ParamConstraint(name="lookback", dtype="int"),)
        spec = _make_spec(params={}, constraints=constraints)
        errors = validate_spec_params(spec)
        assert any("缺少必填参数" in e for e in errors)

    def test_missing_multiple_params(self) -> None:
        """缺少多个必填参数。"""
        constraints = (
            ParamConstraint(name="a", dtype="int"),
            ParamConstraint(name="b", dtype="str"),
        )
        spec = _make_spec(params={}, constraints=constraints)
        errors = validate_spec_params(spec)
        assert len(errors) == 2

    def test_wrong_type_int(self) -> None:
        """int 参数传入字符串。"""
        constraints = (ParamConstraint(name="lookback", dtype="int"),)
        spec = _make_spec(params={"lookback": "abc"}, constraints=constraints)
        errors = validate_spec_params(spec)
        assert any("类型错误" in e for e in errors)

    def test_wrong_type_float(self) -> None:
        """float 参数传入字符串。"""
        constraints = (ParamConstraint(name="threshold", dtype="float"),)
        spec = _make_spec(params={"threshold": "x"}, constraints=constraints)
        errors = validate_spec_params(spec)
        assert any("类型错误" in e for e in errors)

    def test_wrong_type_str(self) -> None:
        """str 参数传入整数。"""
        constraints = (ParamConstraint(name="method", dtype="str"),)
        spec = _make_spec(params={"method": 123}, constraints=constraints)
        errors = validate_spec_params(spec)
        assert any("类型错误" in e for e in errors)

    def test_bool_not_accepted_as_int(self) -> None:
        """bool 不被接受为 int（Python 中 bool 是 int 子类）。"""
        constraints = (ParamConstraint(name="flag", dtype="int"),)
        spec = _make_spec(params={"flag": True}, constraints=constraints)
        errors = validate_spec_params(spec)
        assert any("类型错误" in e for e in errors)

    def test_int_accepted_as_float(self) -> None:
        """int 可以作为 float（Python 数值兼容）。"""
        constraints = (ParamConstraint(name="threshold", dtype="float"),)
        spec = _make_spec(params={"threshold": 1}, constraints=constraints)
        assert validate_spec_params(spec) == []

    def test_numeric_below_min(self) -> None:
        """数值低于最小值。"""
        constraints = (ParamConstraint(name="lookback", dtype="int", min_value=10),)
        spec = _make_spec(params={"lookback": 5}, constraints=constraints)
        errors = validate_spec_params(spec)
        assert any("小于最小值" in e for e in errors)

    def test_numeric_above_max(self) -> None:
        """数值高于最大值。"""
        constraints = (ParamConstraint(name="lookback", dtype="int", max_value=100),)
        spec = _make_spec(params={"lookback": 200}, constraints=constraints)
        errors = validate_spec_params(spec)
        assert any("大于最大值" in e for e in errors)

    def test_numeric_at_boundary(self) -> None:
        """数值在边界上应通过。"""
        constraints = (
            ParamConstraint(name="val", dtype="float", min_value=0.0, max_value=1.0),
        )
        spec = _make_spec(params={"val": 0.0}, constraints=constraints)
        assert validate_spec_params(spec) == []
        spec = _make_spec(params={"val": 1.0}, constraints=constraints)
        assert validate_spec_params(spec) == []

    def test_enum_value_valid(self) -> None:
        """枚举值在允许列表内。"""
        constraints = (
            ParamConstraint(name="method", dtype="str", allowed_values=("a", "b")),
        )
        spec = _make_spec(params={"method": "a"}, constraints=constraints)
        assert validate_spec_params(spec) == []

    def test_enum_value_invalid(self) -> None:
        """枚举值不在允许列表内。"""
        constraints = (
            ParamConstraint(name="method", dtype="str", allowed_values=("a", "b")),
        )
        spec = _make_spec(params={"method": "c"}, constraints=constraints)
        errors = validate_spec_params(spec)
        assert any("值无效" in e for e in errors)

    def test_no_allowed_values_means_any_str_ok(self) -> None:
        """没有 allowed_values 时，任意 str 都通过。"""
        constraints = (ParamConstraint(name="name", dtype="str"),)
        spec = _make_spec(params={"name": "anything"}, constraints=constraints)
        assert validate_spec_params(spec) == []

    def test_multiple_errors_accumulated(self) -> None:
        """多个错误应全部返回。"""
        constraints = (
            ParamConstraint(name="lookback", dtype="int", min_value=10),
            ParamConstraint(name="method", dtype="str", allowed_values=("a",)),
        )
        spec = _make_spec(
            params={"lookback": 5, "method": "invalid"},
            constraints=constraints,
        )
        errors = validate_spec_params(spec)
        assert len(errors) == 2

    def test_type_error_skips_range_check(self) -> None:
        """类型错误时不再进行范围检查。"""
        constraints = (ParamConstraint(name="lookback", dtype="int", min_value=10),)
        spec = _make_spec(params={"lookback": "bad"}, constraints=constraints)
        errors = validate_spec_params(spec)
        # 应只有类型错误，不应有范围错误
        assert len(errors) == 1
        assert "类型错误" in errors[0]
