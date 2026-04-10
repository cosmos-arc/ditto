"""Tests for Golden Dataset model validation."""

import pytest
from ditto_data.quality.golden import GoldenDatasetSpec
from pydantic import ValidationError


@pytest.mark.unit
class TestGoldenDatasetSpecValidation:
    """测试 GoldenDatasetSpec 验证."""

    def test_tickers_accepts_list(self) -> None:
        """接受列表类型的 tickers."""
        spec = GoldenDatasetSpec(tickers=["600519", "000001"])

        assert spec.tickers == ["000001", "600519"]

    def test_tickers_rejects_string_scalar(self) -> None:
        """拒绝字符串标量（常见 YAML 误写）."""
        with pytest.raises(ValidationError) as exc_info:
            GoldenDatasetSpec(tickers="600519")  # type: ignore[arg-type]

        error_msg = str(exc_info.value).lower()
        assert "tickers" in error_msg
        assert "list" in error_msg

    def test_tickers_rejects_int_scalar(self) -> None:
        """拒绝整数标量."""
        with pytest.raises(ValidationError) as exc_info:
            GoldenDatasetSpec(tickers=600519)  # type: ignore[arg-type]

        error_msg = str(exc_info.value).lower()
        assert "tickers" in error_msg

    def test_tickers_rejects_dict(self) -> None:
        """拒绝字典类型."""
        with pytest.raises(ValidationError) as exc_info:
            GoldenDatasetSpec(tickers={"600519": "茅台"})  # type: ignore[arg-type]

        error_msg = str(exc_info.value).lower()
        assert "tickers" in error_msg

    def test_tickers_empty_list_allowed(self) -> None:
        """允许空列表."""
        spec = GoldenDatasetSpec(tickers=[])

        assert spec.tickers == []
        assert spec.is_enabled is False

    def test_tickers_none_allowed(self) -> None:
        """允许 None 值."""
        spec = GoldenDatasetSpec(tickers=None)  # type: ignore[arg-type]

        assert spec.tickers == []

    def test_tickers_deduplicates_and_sorts(self) -> None:
        """去重并排序."""
        spec = GoldenDatasetSpec(tickers=["600519", "000001", "600519"])

        assert spec.tickers == ["000001", "600519"]
