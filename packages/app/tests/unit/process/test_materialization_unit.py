"""_compute_value_jump_rate 单元测试 — 阈值基于 pct_change 自身分布的 z-score。"""

import polars as pl
from ditto_app.process.materialization_helpers import _compute_value_jump_rate

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_frame(
    dates: list[str],
    values: list[float],
    entity: str = "A",
    date_col: str = "trade_date",
    entity_col: str = "instrument_id",
) -> pl.DataFrame:
    """构造符合 _compute_value_jump_rate 输入要求的 DataFrame。"""
    return pl.DataFrame(
        {
            entity_col: [entity] * len(dates),
            date_col: dates,
            "value": values,
        }
    )


# ---------------------------------------------------------------------------
# 1. 正常数据 — 存在跳跃点时返回正确比例
# ---------------------------------------------------------------------------


def test_compute_value_jump_rate_normal() -> None:
    """正常数据：构造一个远超 3σ 的跳跃点，验证返回比例正确。"""
    # 10 个均匀小幅变化 + 1 个巨幅跳跃
    values = [100.0 + i * 1.0 for i in range(10)] + [200.0]  # 最后一个跳了 ~100%
    dates = [f"2025-01-{d:02d}" for d in range(1, 12)]

    frame = _make_frame(dates, values)
    rate = _compute_value_jump_rate(frame)

    # pct_change: 前 9 个约 0.01，最后一个约 1.0 → std 偏小，跳跃被检出
    assert rate > 0.0
    assert rate <= 1.0


# ---------------------------------------------------------------------------
# 2. 均匀变化 — 无跳跃时返回 0
# ---------------------------------------------------------------------------


def test_compute_value_jump_rate_no_jumps() -> None:
    """所有 value 完全相同时 pct_change 全为 0/null → std=0 → 返回 0。

    这与 test_compute_value_jump_rate_zero_pct_std 类似，但使用非零常量值，
    验证函数在"无任何变化"场景下正确返回 0。
    """
    values = [100.0, 100.0, 100.0, 100.0, 100.0]
    dates = [f"2025-01-{d:02d}" for d in range(1, 6)]

    frame = _make_frame(dates, values)
    rate = _compute_value_jump_rate(frame)

    # 所有 value 相同 → pct_change 全为 0 → std=0 → 返回 0
    assert rate == 0.0


# ---------------------------------------------------------------------------
# 3. 空数据 — 返回 0
# ---------------------------------------------------------------------------


def test_compute_value_jump_rate_empty_frame() -> None:
    """空 DataFrame 返回 0.0。"""
    frame = pl.DataFrame(
        {
            "instrument_id": pl.Series([], dtype=pl.Utf8),
            "trade_date": pl.Series([], dtype=pl.Utf8),
            "value": pl.Series([], dtype=pl.Float64),
        }
    )
    rate = _compute_value_jump_rate(frame)
    assert rate == 0.0


# ---------------------------------------------------------------------------
# 4. 单行数据 — 返回 0
# ---------------------------------------------------------------------------


def test_compute_value_jump_rate_single_row() -> None:
    """单行数据无法计算 pct_change，返回 0。"""
    frame = _make_frame(["2025-01-01"], [100.0])
    rate = _compute_value_jump_rate(frame)
    assert rate == 0.0


# ---------------------------------------------------------------------------
# 5. 所有值相同 — pct_std=0，返回 0
# ---------------------------------------------------------------------------


def test_compute_value_jump_rate_zero_pct_std() -> None:
    """所有 value 相同时 pct_change 全为 0 → std=0 → 返回 0。"""
    values = [42.0] * 5
    dates = [f"2025-01-{d:02d}" for d in range(1, 6)]

    frame = _make_frame(dates, values)
    rate = _compute_value_jump_rate(frame)
    assert rate == 0.0


# ---------------------------------------------------------------------------
# 6. 多 entity 场景
# ---------------------------------------------------------------------------


def test_compute_value_jump_rate_multiple_entities() -> None:
    """多 entity：一个有跳跃一个没有，返回全局跳跃比例。"""
    # Entity A: 均匀变化（20 个点，pct_change 均约 0.01）
    dates_a = [f"2025-01-{d:02d}" for d in range(1, 21)]
    values_a = [float(100 + i) for i in range(20)]

    # Entity B: 大部分均匀 + 一个极端跳跃
    dates_b = [f"2025-01-{d:02d}" for d in range(1, 21)]
    values_b = [float(100 + i) for i in range(19)] + [10000.0]

    frame = pl.concat(
        [
            _make_frame(dates_a, values_a, entity="A"),
            _make_frame(dates_b, values_b, entity="B"),
        ]
    )

    rate = _compute_value_jump_rate(frame)

    assert rate >= 0.0
    assert rate <= 1.0

    # Entity B 最后一个 pct_change ≈ 99 倍，远超其他 ≈ 0.01
    # 大量正常点（~38 个 pct_change ≈ 0.01）使 std 仍然很小
    # 3σ 阈值远小于 99，跳跃应被检出
    assert rate > 0.0, "应该检出 Entity B 的跳跃点"
