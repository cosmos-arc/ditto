"""Tests for _spec_deserializer helpers."""

import pytest
from ditto_app.builders._spec_deserializer import (
    as_float_tuple,
    as_object_dict,
    as_sequence,
    as_str_tuple,
    read_bool,
    read_float,
    read_int,
    read_optional_float,
    read_optional_int,
    read_required_str,
)

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
