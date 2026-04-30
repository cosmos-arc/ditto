"""Tests for _spec_deserializer helpers."""

import pytest
from ditto_application.builders._spec_deserializer import (
    _read_clamped_float,
    as_float_tuple,
    as_object_dict,
    as_sequence,
    as_str_tuple,
    deserialize_regime_config,
    read_bool,
    read_float,
    read_int,
    read_optional_float,
    read_optional_int,
    read_optional_str,
    read_required_str,
    read_str_value,
)

# ---------------------------------------------------------------------------
# _read_clamped_float
# ---------------------------------------------------------------------------


class TestReadClampedFloat:
    @pytest.mark.unit
    def test_value_in_range(self) -> None:
        assert _read_clamped_float(0.65, field_name="x", lo=0.0, hi=1.0) == 0.65

    @pytest.mark.unit
    def test_boundary_lo(self) -> None:
        assert _read_clamped_float(0.0, field_name="x", lo=0.0, hi=1.0) == 0.0

    @pytest.mark.unit
    def test_boundary_hi(self) -> None:
        assert _read_clamped_float(1.0, field_name="x", lo=0.0, hi=1.0) == 1.0

    @pytest.mark.unit
    def test_above_range_raises(self) -> None:
        with pytest.raises(ValueError, match=r"x 必须在 \[0.0, 1.0\] 范围内"):
            _read_clamped_float(1.5, field_name="x", lo=0.0, hi=1.0)

    @pytest.mark.unit
    def test_below_range_raises(self) -> None:
        with pytest.raises(ValueError, match=r"x 必须在 \[0.0, 1.0\] 范围内"):
            _read_clamped_float(-0.1, field_name="x", lo=0.0, hi=1.0)

    @pytest.mark.unit
    def test_non_numeric_raises(self) -> None:
        with pytest.raises(ValueError, match="x 必须是数字"):
            _read_clamped_float("abc", field_name="x", lo=0.0, hi=1.0)


# ---------------------------------------------------------------------------
# deserialize_regime_config — threshold 范围校验
# ---------------------------------------------------------------------------


class TestDeserializeRegimeConfigThresholdRange:
    @pytest.mark.unit
    def test_bull_threshold_above_one_raises(self) -> None:
        """bull_threshold=70.0（百分比思维）应被拒绝."""
        with pytest.raises(ValueError, match=r"bull_threshold 必须在 \[0.0, 1.0\]"):
            deserialize_regime_config(
                {
                    "indicators": [],
                    "bull_threshold": 70.0,
                }
            )

    @pytest.mark.unit
    def test_bear_threshold_below_zero_raises(self) -> None:
        """bear_threshold=-0.5 应被拒绝."""
        with pytest.raises(ValueError, match=r"bear_threshold 必须在 \[0.0, 1.0\]"):
            deserialize_regime_config(
                {
                    "indicators": [],
                    "bear_threshold": -0.5,
                }
            )

    @pytest.mark.unit
    def test_bull_threshold_at_boundary_ok(self) -> None:
        """bull_threshold=1.0 应被接受（边界值）."""
        config = deserialize_regime_config(
            {
                "indicators": [],
                "bull_threshold": 1.0,
            }
        )
        assert config is not None
        assert config.bull_threshold == 1.0

    @pytest.mark.unit
    def test_bear_threshold_at_boundary_ok(self) -> None:
        """bear_threshold=0.0 应被接受（边界值）."""
        config = deserialize_regime_config(
            {
                "indicators": [],
                "bear_threshold": 0.0,
            }
        )
        assert config is not None
        assert config.bear_threshold == 0.0

    @pytest.mark.unit
    def test_normal_defaults_ok(self) -> None:
        """默认值 0.65/0.35 应被接受."""
        config = deserialize_regime_config({"indicators": []})
        assert config is not None
        assert config.bull_threshold == 0.65
        assert config.bear_threshold == 0.35


# ---------------------------------------------------------------------------
# read_int
# ---------------------------------------------------------------------------


class TestReadInt:
    @pytest.mark.unit
    def test_normal_value(self) -> None:
        assert read_int(42, field_name="x") == 42

    @pytest.mark.unit
    def test_float_rejected(self) -> None:
        with pytest.raises(ValueError):
            read_int(3.14, field_name="x")

    @pytest.mark.unit
    def test_true_rejected(self) -> None:
        with pytest.raises(ValueError):
            read_int(True, field_name="x")

    @pytest.mark.unit
    def test_false_rejected(self) -> None:
        with pytest.raises(ValueError):
            read_int(False, field_name="x")


# ---------------------------------------------------------------------------
# read_float
# ---------------------------------------------------------------------------


class TestReadFloat:
    @pytest.mark.unit
    def test_normal_float(self) -> None:
        assert read_float(3.14, field_name="x") == 3.14

    @pytest.mark.unit
    def test_int_promoted(self) -> None:
        assert read_float(42, field_name="x") == 42.0

    @pytest.mark.unit
    def test_true_rejected(self) -> None:
        with pytest.raises(ValueError):
            read_float(True, field_name="x")

    @pytest.mark.unit
    def test_string_rejected(self) -> None:
        with pytest.raises(ValueError):
            read_float("abc", field_name="x")


# ---------------------------------------------------------------------------
# read_optional_int
# ---------------------------------------------------------------------------


class TestReadOptionalInt:
    @pytest.mark.unit
    def test_none(self) -> None:
        assert read_optional_int(None, field_name="x") is None

    @pytest.mark.unit
    def test_normal_value(self) -> None:
        assert read_optional_int(42, field_name="x") == 42


# ---------------------------------------------------------------------------
# read_optional_float
# ---------------------------------------------------------------------------


class TestReadOptionalFloat:
    @pytest.mark.unit
    def test_none(self) -> None:
        assert read_optional_float(None, field_name="x") is None

    @pytest.mark.unit
    def test_normal_value(self) -> None:
        assert read_optional_float(3.14, field_name="x") == 3.14


# ---------------------------------------------------------------------------
# read_bool
# ---------------------------------------------------------------------------


class TestReadBool:
    @pytest.mark.unit
    def test_true(self) -> None:
        assert read_bool(True, field_name="x") is True

    @pytest.mark.unit
    def test_false(self) -> None:
        assert read_bool(False, field_name="x") is False

    @pytest.mark.unit
    def test_int_rejected(self) -> None:
        with pytest.raises(ValueError):
            read_bool(1, field_name="x")

    @pytest.mark.unit
    def test_string_rejected(self) -> None:
        with pytest.raises(ValueError):
            read_bool("true", field_name="x")


# ---------------------------------------------------------------------------
# read_required_str
# ---------------------------------------------------------------------------


class TestReadRequiredStr:
    @pytest.mark.unit
    def test_normal_value(self) -> None:
        assert read_required_str({"x": "hello"}, "x") == "hello"

    @pytest.mark.unit
    def test_none_value_rejected(self) -> None:
        with pytest.raises(ValueError):
            read_required_str({"x": None}, "x")

    @pytest.mark.unit
    def test_missing_key_rejected(self) -> None:
        with pytest.raises(ValueError):
            read_required_str({}, "x")

    @pytest.mark.unit
    def test_empty_string_rejected(self) -> None:
        with pytest.raises(ValueError):
            read_required_str({"x": ""}, "x")


# ---------------------------------------------------------------------------
# as_sequence
# ---------------------------------------------------------------------------


class TestAsSequence:
    @pytest.mark.unit
    def test_list(self) -> None:
        assert as_sequence([1, 2], field_name="x") == (1, 2)

    @pytest.mark.unit
    def test_tuple(self) -> None:
        assert as_sequence((1, 2), field_name="x") == (1, 2)

    @pytest.mark.unit
    def test_none(self) -> None:
        assert as_sequence(None, field_name="x") == ()

    @pytest.mark.unit
    def test_string_rejected(self) -> None:
        with pytest.raises(ValueError):
            as_sequence("abc", field_name="x")


# ---------------------------------------------------------------------------
# as_str_tuple
# ---------------------------------------------------------------------------


class TestAsStrTuple:
    @pytest.mark.unit
    def test_normal(self) -> None:
        assert as_str_tuple(["a", "b"], field_name="x") == ("a", "b")

    @pytest.mark.unit
    def test_element_type_error(self) -> None:
        with pytest.raises(ValueError):
            as_str_tuple([1, 2], field_name="x")


# ---------------------------------------------------------------------------
# as_float_tuple
# ---------------------------------------------------------------------------


class TestAsFloatTuple:
    @pytest.mark.unit
    def test_normal(self) -> None:
        assert as_float_tuple([1, 2.5], field_name="x") == (1.0, 2.5)

    @pytest.mark.unit
    def test_true_rejected(self) -> None:
        with pytest.raises(ValueError):
            as_float_tuple([True], field_name="x")


# ---------------------------------------------------------------------------
# as_object_dict
# ---------------------------------------------------------------------------


class TestAsObjectDict:
    @pytest.mark.unit
    def test_normal_dict(self) -> None:
        assert as_object_dict({"a": 1}, field_name="x") == {"a": 1}

    @pytest.mark.unit
    def test_none(self) -> None:
        assert as_object_dict(None, field_name="x") == {}

    @pytest.mark.unit
    def test_string_rejected(self) -> None:
        with pytest.raises(ValueError):
            as_object_dict("abc", field_name="x")

    @pytest.mark.unit
    def test_non_str_key_rejected(self) -> None:
        with pytest.raises(ValueError):
            as_object_dict({1: "a"}, field_name="x")


# ---------------------------------------------------------------------------
# read_optional_str
# ---------------------------------------------------------------------------


class TestReadOptionalStr:
    @pytest.mark.unit
    def test_none_returns_none(self) -> None:
        assert read_optional_str(None, field_name="x") is None

    @pytest.mark.unit
    def test_valid_string(self) -> None:
        assert read_optional_str("hello", field_name="x") == "hello"

    @pytest.mark.unit
    def test_empty_string_returns_value(self) -> None:
        assert read_optional_str("", field_name="x") == ""

    @pytest.mark.unit
    def test_non_string_raises(self) -> None:
        with pytest.raises(ValueError, match="x 必须是字符串"):
            read_optional_str(42, field_name="x")


# ---------------------------------------------------------------------------
# read_str_value
# ---------------------------------------------------------------------------


class TestReadStrValue:
    @pytest.mark.unit
    def test_valid_string(self) -> None:
        assert read_str_value("hello", field_name="x") == "hello"

    @pytest.mark.unit
    def test_empty_string_raises(self) -> None:
        with pytest.raises(ValueError, match="x 必须是非空字符串"):
            read_str_value("", field_name="x")

    @pytest.mark.unit
    def test_non_string_raises(self) -> None:
        with pytest.raises(ValueError, match="x 必须是非空字符串"):
            read_str_value(42, field_name="x")
