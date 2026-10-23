"""#592 双制度双份月度权重塌缩单元测试."""

import polars as pl
import pytest
from ditto_application.processes.ingestion.data_writer import (
    _collapse_dual_regime_weight_month,
)


def _dual_month_frame() -> pl.DataFrame:
    # 899050.BJ 2023-11 实测形状：老码 50 行 + 新码 50 行（各和≈100）
    rows = {"index_id": [], "source_ticker": [], "trade_date": [], "weight": []}
    for i in range(4):
        rows["index_id"].append("899050.BJ")
        rows["source_ticker"].append(f"83{i:04d}.BJ")
        rows["trade_date"].append("2023-11-30")
        rows["weight"].append(25.0)
    for i in range(3):
        rows["index_id"].append("899050.BJ")
        rows["source_ticker"].append(f"920{i:03d}.BJ")
        rows["trade_date"].append("2023-11-30")
        rows["weight"].append(100.0 / 3)
    # 同帧其他指数/月份（无制度标注）必须原样保留
    rows["index_id"] += ["000300.SH", "000300.SH"]
    rows["source_ticker"] += ["600000.SH", "000001.SZ"]
    rows["trade_date"] += ["2023-11-30", "2023-11-30"]
    rows["weight"] += [50.0, 50.0]
    return pl.DataFrame(rows)


@pytest.mark.unit
def test_dual_regime_month_keeps_larger_regime() -> None:
    out = _collapse_dual_regime_weight_month(_dual_month_frame(), "source_ticker")
    bse = out.filter(pl.col("index_id") == "899050.BJ")
    # 老码 4 行 > 新码 3 行 → 保留老码制度
    assert bse["source_ticker"].to_list() == sorted(
        t for t in bse["source_ticker"] if t.startswith("83")
    )
    assert bse.height == 4
    # 非北交所行不触碰
    assert out.filter(pl.col("index_id") == "000300.SH").height == 2


@pytest.mark.unit
def test_duplicate_form_tie_keeps_old_regime() -> None:
    # 重复形并列：两制度各 2 行、子和各=100 → 保留老码制度
    frame = (
        _dual_month_frame()
        .filter(pl.col("index_id") == "899050.BJ")
        .filter(
            pl.col("source_ticker").is_in(
                ["830000.BJ", "830001.BJ", "920000.BJ", "920001.BJ"]
            )
        )
        .with_columns(pl.lit(50.0).alias("weight"))
    )
    out = _collapse_dual_regime_weight_month(frame, "source_ticker")
    assert out.height == 2
    assert all(t.startswith("83") for t in out["source_ticker"])
    assert abs(float(out["weight"].sum()) - 100.0) < 0.01


@pytest.mark.unit
def test_unrecognized_partial_shape_passes_through() -> None:
    # 未知形态（子和 50/66.7、合集≈116.7）：不触碰，交由总额校验 fail-closed
    frame = (
        _dual_month_frame()
        .filter(pl.col("index_id") == "899050.BJ")
        .filter(
            pl.col("source_ticker").is_in(
                ["830000.BJ", "830001.BJ", "920000.BJ", "920001.BJ"]
            )
        )
    )
    out = _collapse_dual_regime_weight_month(frame, "source_ticker")
    assert out.height == 4


@pytest.mark.unit
def test_single_regime_untouched() -> None:
    frame = _dual_month_frame().filter(
        ~pl.col("source_ticker").str.contains(r"^920\d{3}\.BJ$")
    )
    out = _collapse_dual_regime_weight_month(frame, "source_ticker")
    assert out.height == frame.height


@pytest.mark.unit
def test_empty_frame() -> None:
    empty = pl.DataFrame(
        schema={
            "index_id": pl.String,
            "source_ticker": pl.String,
            "trade_date": pl.String,
            "weight": pl.Float64,
        }
    )
    assert _collapse_dual_regime_weight_month(empty, "source_ticker").height == 0


def _complementary_month_frame() -> pl.DataFrame:
    # 899050.BJ 2025-04 实测形状：老码 46 行 sum≈92.4 + 新码 4 行 sum≈7.6
    rows = {"index_id": [], "source_ticker": [], "trade_date": [], "weight": []}
    for i in range(3):
        rows["index_id"].append("899050.BJ")
        rows["source_ticker"].append(f"83{i:04d}.BJ")
        rows["trade_date"].append("2025-04-30")
        rows["weight"].append(30.8)
    for i in range(2):
        rows["index_id"].append("899050.BJ")
        rows["source_ticker"].append(f"920{i:03d}.BJ")
        rows["trade_date"].append("2025-04-30")
        rows["weight"].append(3.8)
    return pl.DataFrame(rows)


@pytest.mark.unit
def test_complementary_month_keeps_union() -> None:
    out = _collapse_dual_regime_weight_month(
        _complementary_month_frame(), "source_ticker"
    )
    assert out.height == 5
    assert abs(float(out["weight"].sum()) - 100.0) < 0.01


@pytest.mark.unit
def test_settle_same_issuer_dual_code_keeps_new_regime() -> None:
    # #592 correctness F2：富化后同 instrument 双码行保 920 新码行
    from ditto_application.processes.ingestion.data_writer import (
        _settle_same_issuer_dual_code,
    )

    frame = pl.DataFrame(
        {
            "index_id": ["899050.BJ"] * 3,
            "instrument_id": [1004807, 1004807, 1004806],
            "trade_date": ["2025-04-30"] * 3,
            "source_ticker": ["430418.BJ", "920418.BJ", "920964.BJ"],
            "weight": [3.0, 4.0, 5.0],
        }
    )
    out = _settle_same_issuer_dual_code(frame, "source_ticker")
    assert out.height == 2
    kept = out.filter(pl.col("instrument_id") == 1004807)
    assert kept["source_ticker"].to_list() == ["920418.BJ"]


@pytest.mark.unit
def test_settle_no_op_without_dupes() -> None:
    from ditto_application.processes.ingestion.data_writer import (
        _settle_same_issuer_dual_code,
    )

    frame = pl.DataFrame(
        {
            "index_id": ["899050.BJ"] * 2,
            "instrument_id": [1004807, 1004806],
            "trade_date": ["2025-04-30"] * 2,
            "source_ticker": ["430418.BJ", "920964.BJ"],
            "weight": [3.0, 5.0],
        }
    )
    assert _settle_same_issuer_dual_code(frame, "source_ticker").equals(frame)
