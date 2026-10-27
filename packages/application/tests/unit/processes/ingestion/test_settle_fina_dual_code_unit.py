"""#599 fina_indicator 北交所双码同披露键收敛单元测试."""

import polars as pl
import pytest
from ditto_application.processes.ingestion.data_writer import (
    _settle_fina_indicator_dual_code,
)


def _dual_code_frame(
    old_values: dict[str, object], new_values: dict[str, object]
) -> pl.DataFrame:
    """430017.BJ ↔ 920017.BJ 同披露键双行，指标列由参数给定."""
    base = {
        "instrument_id": [1005126, 1005126],
        "report_date": ["2012-12-31", "2012-12-31"],
        "knowledge_date": ["2013-04-27", "2013-04-27"],
        "source_ticker": ["430017.BJ", "920017.BJ"],
    }
    indicators = sorted(set(old_values) | set(new_values))
    for col in indicators:
        base[col] = [old_values.get(col), new_values.get(col)]
    return pl.DataFrame(base)


@pytest.mark.unit
def test_no_duplicate_keys_untouched() -> None:
    frame = _dual_code_frame({"eps": 0.1}, {"eps": 0.1})
    frame = frame.filter(pl.col("source_ticker") == "430017.BJ")
    out = _settle_fina_indicator_dual_code(frame)
    assert out.equals(frame)


@pytest.mark.unit
def test_identical_values_keeps_new_code() -> None:
    # 52/55 实测形态：两码指标值完全相同 → 保 920 新码行
    frame = _dual_code_frame({"eps": 0.4, "roe": 20.9}, {"eps": 0.4, "roe": 20.9})
    out = _settle_fina_indicator_dual_code(frame)
    assert out.height == 1
    assert out["source_ticker"].to_list() == ["920017.BJ"]
    assert out["eps"].to_list() == [0.4]


@pytest.mark.unit
def test_old_richer_keeps_old() -> None:
    # 430017 实测形态：老码行 fcff 有值、新码行 null → 少 null 优先保老码
    frame = _dual_code_frame(
        {"eps": 0.1, "fcff": -112842757.9578}, {"eps": 0.1, "fcff": None}
    )
    out = _settle_fina_indicator_dual_code(frame)
    assert out.height == 1
    assert out["source_ticker"].to_list() == ["430017.BJ"]
    assert out["fcff"].to_list() == [-112842757.9578]


@pytest.mark.unit
def test_new_richer_keeps_new() -> None:
    frame = _dual_code_frame({"eps": 0.1, "fcff": None}, {"eps": 0.1, "fcff": 1.5})
    out = _settle_fina_indicator_dual_code(frame)
    assert out.height == 1
    assert out["source_ticker"].to_list() == ["920017.BJ"]
    assert out["fcff"].to_list() == [1.5]


@pytest.mark.unit
def test_equal_null_count_tie_keeps_new_code() -> None:
    # 同 null 数、不同值：平局取 920 新码（换码后权威口径）
    frame = _dual_code_frame({"eps": 0.1, "roe": None}, {"eps": 0.2, "roe": None})
    out = _settle_fina_indicator_dual_code(frame)
    assert out.height == 1
    assert out["source_ticker"].to_list() == ["920017.BJ"]
    assert out["eps"].to_list() == [0.2]


@pytest.mark.unit
def test_settle_is_idempotent() -> None:
    frame = _dual_code_frame({"eps": 0.1, "fcff": None}, {"eps": 0.1, "fcff": 2.0})
    once = _settle_fina_indicator_dual_code(frame)
    twice = _settle_fina_indicator_dual_code(once)
    assert once.equals(twice)


@pytest.mark.unit
def test_non_duplicate_groups_preserved() -> None:
    # 其他披露键的行不触碰
    frame = _dual_code_frame({"eps": 0.4}, {"eps": 0.4}).vstack(
        pl.DataFrame(
            {
                "instrument_id": [1004807],
                "report_date": ["2012-03-31"],
                "knowledge_date": ["2012-06-01"],
                "source_ticker": ["430418.BJ"],
                "eps": [None],
            }
        )
    )
    out = _settle_fina_indicator_dual_code(frame)
    assert out.height == 2
    assert out.filter(pl.col("instrument_id") == 1004807).height == 1


@pytest.mark.unit
def test_two_old_code_tie_winner_stable_across_shuffles() -> None:
    # #599 F3：多段改名可让同一 instrument 挂两条老码别名——(null 数,
    # 新码) 全平时无最终键则胜者随行序漂移；source_ticker 升序兜底全序。
    winners = set()
    for seed in range(20):
        frame = pl.DataFrame(
            {
                "instrument_id": [1005126, 1005126],
                "report_date": ["2012-12-31", "2012-12-31"],
                "knowledge_date": ["2013-04-27", "2013-04-27"],
                "source_ticker": ["430001.BJ", "830001.BJ"],
                "eps": [0.1, 0.2],
            }
        )
        shuffled = frame.sample(fraction=1.0, shuffle=True, seed=seed)
        winners.add(
            _settle_fina_indicator_dual_code(shuffled)["source_ticker"].to_list()[0]
        )
    assert winners == {"830001.BJ"}


@pytest.mark.unit
def test_empty_value_columns_settles_by_code_preference() -> None:
    # #599 F4：仅键+代码列的帧不能撞 sum_horizontal([]) 空 fold
    frame = pl.DataFrame(
        {
            "instrument_id": [1005126, 1005126],
            "report_date": ["2012-12-31", "2012-12-31"],
            "knowledge_date": ["2013-04-27", "2013-04-27"],
            "source_ticker": ["430017.BJ", "920017.BJ"],
        }
    )
    out = _settle_fina_indicator_dual_code(frame)
    assert out.height == 1
    assert out["source_ticker"].to_list() == ["920017.BJ"]


@pytest.mark.unit
def test_output_order_deterministic_across_input_shuffles() -> None:
    # #606 F2 同修：unique 不保序——收敛路径须按写侧键全序输出，否则
    # 同输入的 WriteResult.checksum 逐次漂移。
    frame = pl.DataFrame(
        {
            "instrument_id": [1005126] * 4,
            "report_date": ["2012-12-31"] * 2 + ["2012-09-30"] * 2,
            "knowledge_date": ["2013-04-27"] * 4,
            "source_ticker": ["430017.BJ", "920017.BJ", "430001.BJ", "920001.BJ"],
            "eps": [0.1, 0.1, 0.2, 0.2],
        }
    )
    outputs = set()
    for seed in range(10):
        shuffled = frame.sample(fraction=1.0, shuffle=True, seed=seed)
        out = _settle_fina_indicator_dual_code(shuffled)
        assert out.height == 2
        outputs.add(str(out.hash_rows().to_list()))
    assert len(outputs) == 1


@pytest.mark.unit
def test_correction_marker_outranks_code_preference() -> None:
    """#613 G F2:老码修正行(flag=True)胜过等全新码陈旧行。"""
    frame = _dual_code_frame({"fcff": 5.5e8}, {"fcff": 3.9e8})
    frame = frame.with_columns(
        pl.Series(
            "is_provider_correction",
            [True, False],
        )
    )
    out = _settle_fina_indicator_dual_code(frame)
    assert out.height == 1
    assert out["source_ticker"].to_list() == ["430017.BJ"]
    assert out["fcff"].to_list() == [5.5e8]


@pytest.mark.unit
def test_correction_marker_outranks_richer_new_code() -> None:
    """修正行胜过"更少 null"的新码行——未同步后端不得挤掉修正。"""
    frame = _dual_code_frame({"fcff": 5.5e8}, {"fcff": 3.9e8, "roe": 20.9})
    frame = frame.with_columns(
        pl.Series(
            "is_provider_correction",
            [True, False],
        )
    )
    out = _settle_fina_indicator_dual_code(frame)
    assert out.height == 1
    assert out["source_ticker"].to_list() == ["430017.BJ"]
    assert out["fcff"].to_list() == [5.5e8]
