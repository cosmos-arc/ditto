"""#606 fund_portfolio 北交所双码持仓收敛单元测试."""

import polars as pl
import pytest
from ditto_application.processes.ingestion.data_writer import (
    _settle_fund_portfolio_dual_code,
)

_HOLDING_ID = 1005126


def _dual_code_frame(
    old_values: dict[str, object], new_values: dict[str, object]
) -> pl.DataFrame:
    """430017.BJ ↔ 920017.BJ 同披露键双行，值列由参数给定."""
    base = {
        "instrument_id": [2000001, 2000001],
        "report_date": ["2025-09-30", "2025-09-30"],
        "knowledge_date": ["2025-10-25", "2025-10-25"],
        "holding_symbol": ["430017.BJ", "920017.BJ"],
    }
    indicators = sorted(set(old_values) | set(new_values))
    for col in indicators:
        base[col] = [old_values.get(col), new_values.get(col)]
    return pl.DataFrame(base)


def _map() -> dict[str, int]:
    return {"430017.BJ": _HOLDING_ID, "920017.BJ": _HOLDING_ID}


@pytest.mark.unit
def test_no_duplicate_keys_untouched() -> None:
    frame = _dual_code_frame({"market_value": 1.0}, {"market_value": 1.0})
    frame = frame.filter(pl.col("holding_symbol") == "430017.BJ")
    out = _settle_fund_portfolio_dual_code(frame, _map())
    assert out.equals(frame)


@pytest.mark.unit
def test_identical_values_keeps_new_code() -> None:
    frame = _dual_code_frame(
        {"market_value": 100.0, "holding_shares": 500.0},
        {"market_value": 100.0, "holding_shares": 500.0},
    )
    out = _settle_fund_portfolio_dual_code(frame, _map())
    assert out.height == 1
    assert out["holding_symbol"].to_list() == ["920017.BJ"]
    assert out["market_value"].to_list() == [100.0]


@pytest.mark.unit
def test_old_richer_keeps_old() -> None:
    # 少 null 优先：老码行 stk_mkv_ratio 有值、新码行 null → 保老码
    frame = _dual_code_frame(
        {"market_value": 100.0, "stk_mkv_ratio": 1.2},
        {"market_value": 100.0, "stk_mkv_ratio": None},
    )
    out = _settle_fund_portfolio_dual_code(frame, _map())
    assert out.height == 1
    assert out["holding_symbol"].to_list() == ["430017.BJ"]
    assert out["stk_mkv_ratio"].to_list() == [1.2]


@pytest.mark.unit
def test_new_richer_keeps_new() -> None:
    frame = _dual_code_frame(
        {"market_value": 100.0, "stk_mkv_ratio": None},
        {"market_value": 100.0, "stk_mkv_ratio": 3.4},
    )
    out = _settle_fund_portfolio_dual_code(frame, _map())
    assert out.height == 1
    assert out["holding_symbol"].to_list() == ["920017.BJ"]


@pytest.mark.unit
def test_double_old_code_tie_breaks_by_symbol_order() -> None:
    # 多段改名可让同一 instrument 挂两条老码别名：(null 数, 新码) 全平
    # 仍可达 → holding_symbol 升序保证胜者与行序无关（对齐 #599 F3）。
    base = {
        "instrument_id": [2000001] * 2,
        "report_date": ["2025-09-30"] * 2,
        "knowledge_date": ["2025-10-25"] * 2,
        "holding_symbol": ["830017.BJ", "430017.BJ"],
        "market_value": [100.0, 100.0],
    }
    holding_map = {
        "830017.BJ": _HOLDING_ID,
        "430017.BJ": _HOLDING_ID,
        "920017.BJ": _HOLDING_ID,
    }
    base = pl.DataFrame(base)
    winners = set()
    for seed in range(20):
        shuffled = base.sample(fraction=1.0, shuffle=True, seed=seed)
        out = _settle_fund_portfolio_dual_code(shuffled, holding_map)
        assert out.height == 1
        winners.add(out["holding_symbol"].to_list()[0])
    assert winners == {"830017.BJ"}


@pytest.mark.unit
def test_unresolved_codes_not_merged() -> None:
    # 未解析码（如 .HK 未注册、老码别名缺失）各占自身键，不收敛不丢失。
    frame = pl.DataFrame(
        {
            "instrument_id": [2000001, 2000001],
            "report_date": ["2025-09-30", "2025-09-30"],
            "knowledge_date": ["2025-10-25", "2025-10-25"],
            "holding_symbol": ["00002.HK", "920017.BJ"],
            "market_value": [10.0, 20.0],
        }
    )
    out = _settle_fund_portfolio_dual_code(frame, {"920017.BJ": _HOLDING_ID})
    assert out.height == 2


@pytest.mark.unit
def test_same_code_different_instruments_not_merged() -> None:
    # 不同基金各持同一标的：双键分离，互不收敛。
    frame = pl.DataFrame(
        {
            "instrument_id": [2000001, 2000002],
            "report_date": ["2025-09-30", "2025-09-30"],
            "knowledge_date": ["2025-10-25", "2025-10-25"],
            "holding_symbol": ["920017.BJ", "920017.BJ"],
            "market_value": [10.0, 20.0],
        }
    )
    out = _settle_fund_portfolio_dual_code(frame, {"920017.BJ": _HOLDING_ID})
    assert out.height == 2
    assert sorted(out["instrument_id"].to_list()) == [2000001, 2000002]


@pytest.mark.unit
def test_revision_knowledge_date_not_merged() -> None:
    # 修订以新 knowledge_date 行呈现（#452 观察事实语义），不属双码对。
    frame = pl.DataFrame(
        {
            "instrument_id": [2000001, 2000001],
            "report_date": ["2025-09-30", "2025-09-30"],
            "knowledge_date": ["2025-10-25", "2025-11-01"],
            "holding_symbol": ["430017.BJ", "920017.BJ"],
            "market_value": [10.0, 20.0],
        }
    )
    out = _settle_fund_portfolio_dual_code(frame, _map())
    assert out.height == 2
