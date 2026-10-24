"""#606 fund_portfolio 北交所双码持仓收敛单元测试."""

from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_application.processes.ingestion.data_writer import (
    IngestionDataWriter,
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


@pytest.mark.unit
def test_empty_map_returns_frame_unchanged() -> None:
    # 全部未解析（resolve 返回空）不得因空帧 schema 崩写入（review 实测
    # 复现：空 dict 构造 Null dtype 列 → join SchemaError）。
    frame = _dual_code_frame({"market_value": 1.0}, {"market_value": 2.0})
    out = _settle_fund_portfolio_dual_code(frame, {})
    assert out.equals(frame)


@pytest.mark.unit
def test_settle_is_idempotent() -> None:
    frame = _dual_code_frame(
        {"market_value": 100.0, "stk_mkv_ratio": None},
        {"market_value": 100.0, "stk_mkv_ratio": 3.4},
    )
    once = _settle_fund_portfolio_dual_code(frame, _map())
    twice = _settle_fund_portfolio_dual_code(once, _map())
    assert once.equals(twice)


@pytest.mark.unit
def test_output_order_deterministic_across_input_shuffles() -> None:
    # unique 不保序——收敛路径必须按写侧键全序输出，否则同输入的
    # WriteResult.checksum 逐次漂移（correctness #606 F2）。
    frame = pl.DataFrame(
        {
            "instrument_id": [2000001] * 4,
            "report_date": ["2025-09-30"] * 2 + ["2025-06-30"] * 2,
            "knowledge_date": ["2025-10-25"] * 4,
            "holding_symbol": ["430017.BJ", "920017.BJ", "830017.BJ", "430017.BJ"],
            "market_value": [100.0, 100.0, 50.0, 50.0],
        }
    )
    holding_map = {
        "430017.BJ": _HOLDING_ID,
        "920017.BJ": _HOLDING_ID,
        "830017.BJ": _HOLDING_ID,
    }
    outputs = set()
    for seed in range(10):
        shuffled = frame.sample(fraction=1.0, shuffle=True, seed=seed)
        out = _settle_fund_portfolio_dual_code(shuffled, holding_map)
        assert out.height == 2
        outputs.add(str(out.hash_rows().to_list()))
    assert len(outputs) == 1


@pytest.mark.unit
def test_key_only_frame_settles_by_code_preference() -> None:
    # 仅键+代码列的帧（空 value_cols）不崩，退化为纯代码偏好保 920。
    frame = _dual_code_frame({}, {})
    out = _settle_fund_portfolio_dual_code(frame, _map())
    assert out.height == 1
    assert out["holding_symbol"].to_list() == ["920017.BJ"]


def _writer_with_resolver(
    resolved: dict[str, int],
) -> tuple[IngestionDataWriter, MagicMock]:
    metadata_service = MagicMock()
    metadata_service.instrument.resolve_instrument_ids_batch.return_value = resolved
    writer = IngestionDataWriter(
        metadata_service=metadata_service,
        market_write_service=MagicMock(),
        fundamental_store=MagicMock(),
        capital_store=MagicMock(),
        macro_service=MagicMock(),
        source_name="tushare",
    )
    return writer, metadata_service


@pytest.mark.unit
def test_entry_resolves_only_bse_shaped_codes() -> None:
    # 43x/83x/87x 全段老码（833171/871981）+920 新码均入解析名单；
    # 非 BSE 码（.SZ/.HK）不进名单（review：前缀白名单漏老码段）。
    frame = pl.DataFrame(
        {
            "instrument_id": [2000001] * 4,
            "report_date": ["2025-09-30"] * 4,
            "knowledge_date": ["2025-10-25"] * 4,
            "holding_symbol": ["833171.BJ", "871981.BJ", "000001.SZ", "00002.HK"],
            "market_value": [1.0, 2.0, 3.0, 4.0],
        }
    )
    writer, metadata_service = _writer_with_resolver({})
    out = writer._settle_fund_portfolio_dual_code(frame)
    assert out.equals(frame)
    resolved_arg = metadata_service.instrument.resolve_instrument_ids_batch.call_args
    assert sorted(resolved_arg.kwargs["identifiers"]) == [
        "833171.BJ",
        "871981.BJ",
    ]


@pytest.mark.unit
def test_entry_skips_resolve_without_bse_codes() -> None:
    # 无 BSE 形持仓码：零解析零收敛，行为与修复前一致。
    frame = pl.DataFrame(
        {
            "instrument_id": [2000001],
            "report_date": ["2025-09-30"],
            "knowledge_date": ["2025-10-25"],
            "holding_symbol": ["000001.SZ"],
            "market_value": [3.0],
        }
    )
    writer, metadata_service = _writer_with_resolver({"000001.SZ": 1})
    out = writer._settle_fund_portfolio_dual_code(frame)
    assert out.equals(frame)
    metadata_service.instrument.resolve_instrument_ids_batch.assert_not_called()
