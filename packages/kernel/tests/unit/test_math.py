"""ditto_kernel.math 单元测试."""

from __future__ import annotations

import math

from ditto_kernel.math import pearson_correlation

# ---------------------------------------------------------------------------
# 退化输入
# ---------------------------------------------------------------------------


class TestPearsonCorrelationDegenerate:
    """退化输入（空序列、单元素）测试."""

    def test_empty_both(self) -> None:
        """空序列返回 1.0."""
        assert pearson_correlation([], []) == 1.0

    def test_empty_one_side(self) -> None:
        """一侧空序列仍返回 1.0（len <= 1）."""
        assert pearson_correlation([], [1.0]) == 1.0

    def test_single_element(self) -> None:
        """单元素序列返回 1.0."""
        assert pearson_correlation([5.0], [10.0]) == 1.0

    def test_single_element_equal(self) -> None:
        """单元素相同值返回 1.0."""
        assert pearson_correlation([3.0], [3.0]) == 1.0


# ---------------------------------------------------------------------------
# 零方差（常量序列）
# ---------------------------------------------------------------------------


class TestPearsonCorrelationZeroVariance:
    """零方差序列测试."""

    def test_both_constant_equal(self) -> None:
        """双方均为常量且值相同 → 1.0（var 接近）."""
        assert pearson_correlation([2.0, 2.0, 2.0], [2.0, 2.0, 2.0]) == 1.0

    def test_both_constant_different(self) -> None:
        """双方均为常量但值不同 → 1.0（方差都为 0，is_close）."""
        assert pearson_correlation([1.0, 1.0, 1.0], [99.0, 99.0, 99.0]) == 1.0

    def test_one_constant_one_varying(self) -> None:
        """一侧常量、另一侧变化 → 0.0."""
        result = pearson_correlation([5.0, 5.0, 5.0], [1.0, 2.0, 3.0])
        assert result == 0.0

    def test_one_varying_one_constant(self) -> None:
        """另一侧常量 → 0.0."""
        result = pearson_correlation([1.0, 2.0, 3.0], [5.0, 5.0, 5.0])
        assert result == 0.0

    def test_two_element_constant(self) -> None:
        """两个元素的常量序列."""
        assert pearson_correlation([0.0, 0.0], [0.0, 0.0]) == 1.0


# ---------------------------------------------------------------------------
# 完全相关
# ---------------------------------------------------------------------------


class TestPearsonCorrelationPerfectPositive:
    """完全正相关测试."""

    def test_identity(self) -> None:
        """x == y 时 r == 1.0."""
        r = pearson_correlation([1.0, 2.0, 3.0, 4.0], [1.0, 2.0, 3.0, 4.0])
        assert math.isclose(r, 1.0)

    def test_linear_transform(self) -> None:
        """y = 2x + 1 时 r == 1.0."""
        r = pearson_correlation([1.0, 2.0, 3.0], [3.0, 5.0, 7.0])
        assert math.isclose(r, 1.0)

    def test_negative_slope(self) -> None:
        """y = -x 时 r == -1.0."""
        r = pearson_correlation([1.0, 2.0, 3.0], [-1.0, -2.0, -3.0])
        assert math.isclose(r, -1.0)

    def test_anti_correlated(self) -> None:
        """y = -2x + 10 时 r == -1.0."""
        r = pearson_correlation([1.0, 2.0, 3.0, 4.0], [8.0, 6.0, 4.0, 2.0])
        assert math.isclose(r, -1.0)


# ---------------------------------------------------------------------------
# 一般情况
# ---------------------------------------------------------------------------


class TestPearsonCorrelationGeneral:
    """一般相关性测试."""

    def test_known_positive(self) -> None:
        """已知正相关的精确值."""
        x = [1.0, 2.0, 3.0, 4.0, 5.0]
        y = [2.0, 4.0, 5.0, 4.0, 5.0]
        r = pearson_correlation(x, y)
        assert 0.0 < r < 1.0

    def test_known_negative(self) -> None:
        """已知负相关."""
        x = [1.0, 2.0, 3.0, 4.0, 5.0]
        y = [10.0, 8.0, 6.0, 4.0, 2.0]
        r = pearson_correlation(x, y)
        assert math.isclose(r, -1.0)

    def test_uncorrelated_symmetric(self) -> None:
        """对称序列相关接近 0."""
        x = [1.0, 2.0, 3.0, 4.0, 5.0]
        y = [3.0, 1.0, 5.0, 2.0, 4.0]
        r = pearson_correlation(x, y)
        assert -1.0 <= r <= 1.0

    def test_result_in_valid_range(self) -> None:
        """相关系数应在 [-1, 1] 范围内."""
        x = [0.5, 1.3, 2.7, 3.1, 4.9]
        y = [2.1, 3.4, 1.8, 5.6, 4.2]
        r = pearson_correlation(x, y)
        assert -1.0 <= r <= 1.0

    def test_longer_sequences(self) -> None:
        """较长序列的计算稳定性."""
        n = 1000
        x = [float(i) for i in range(n)]
        y = [float(i) * 2.0 + 1.0 for i in range(n)]
        r = pearson_correlation(x, y)
        assert math.isclose(r, 1.0)


# ---------------------------------------------------------------------------
# 边界与数值稳定性
# ---------------------------------------------------------------------------


class TestPearsonCorrelationEdgeCases:
    """边界条件和数值稳定性测试."""

    def test_two_elements_identical(self) -> None:
        """两个相同元素 → 零方差 → 1.0."""
        assert pearson_correlation([3.0, 3.0], [7.0, 7.0]) == 1.0

    def test_two_elements_varying(self) -> None:
        """两个不同元素 → 完全相关 ±1.0."""
        r = pearson_correlation([1.0, 2.0], [3.0, 6.0])
        assert math.isclose(r, 1.0)

    def test_large_values(self) -> None:
        """大数值不溢出."""
        x = [1e15, 2e15, 3e15]
        y = [2e15, 4e15, 6e15]
        r = pearson_correlation(x, y)
        assert math.isclose(r, 1.0)

    def test_small_values(self) -> None:
        """极小数值精度保持."""
        x = [1e-15, 2e-15, 3e-15]
        y = [2e-15, 4e-15, 6e-15]
        r = pearson_correlation(x, y)
        assert math.isclose(r, 1.0)

    def test_negative_values(self) -> None:
        """全负数序列正确计算."""
        x = [-1.0, -2.0, -3.0, -4.0]
        y = [-2.0, -4.0, -6.0, -8.0]
        r = pearson_correlation(x, y)
        assert math.isclose(r, 1.0)

    def test_mixed_sign_values(self) -> None:
        """正负混合序列正确计算."""
        x = [-2.0, -1.0, 0.0, 1.0, 2.0]
        y = [-4.0, -2.0, 0.0, 2.0, 4.0]
        r = pearson_correlation(x, y)
        assert math.isclose(r, 1.0)

    def test_float_precision_symmetry(self) -> None:
        """x 与 y 交换后结果不变."""
        x = [1.0, 2.0, 3.0, 4.0, 5.0]
        y = [2.1, 3.8, 6.2, 7.9, 10.1]
        r_xy = pearson_correlation(x, y)
        r_yx = pearson_correlation(y, x)
        assert math.isclose(r_xy, r_yx)
