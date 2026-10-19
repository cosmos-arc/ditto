r"""
物化 csi_a_share 历史证券池（#196 策略腿回测前置）.

seed_stock_selection_rotation 声明 universe ``csi_a_share``，回测按
``asof=start_date`` 对 universe_constituent 做 PIT 成员查询。本脚本把
instrument 注册表全部 A 股（含退市）按 list_date/delist_date 区间写入
该证券池，使 2014 起任意 as_of 都有可投资证券池。

ID 语义：``csi_a_share`` 是种子策略声明的 universe 句柄（见
``ditto_strategy/alpha/seeds.py`` 的 ``_seed_stock_selection_rotation``），
内容为注册表全市场区间，不是中证指数成分声明。注意：selection 装配
车道（live 选池）要求宇宙成员==全量注册股票花名册，与本池的退市封闭
区间结构不兼容——该车道用 ``universe.cn.all``；本池仅供回测/研究
车道 PIT 成员消费。

用法::

    DITTO_CONFIG_ROOT=... DITTO_STATE_ROOT=... uv run --no-sync \\
        python -m ditto_apps.scripts.materialize_stock_universe [--force]

幂等性：默认已存在即失败退出；--force 删除重建（注册表新增/修订后重跑）。
"""

from __future__ import annotations

import argparse
import sys
from datetime import date

import orjson
import polars as pl
from ditto_data.services.metadata_service import MetadataService

from ditto_apps.registry.container import make_app_container

__all__ = ["build_constituent_records", "main"]

# 与 ditto_strategy/alpha/seeds.py::_seed_stock_selection_rotation 的
# universe 声明同值；改动任一侧须同步另一侧。
UNIVERSE_ID = "csi_a_share"

# 无效上市日下界：早于 A 股最早真实上市（1990-12-19，沪市开市首日）的
# list_date 必然是注册表占位值（实测 4 只 2026 新股为 1970-01-01，代理
# stock_basic 未提供），按 PIT 语义视为不可判 → 跳过，不进入任何历史
# 成员区间。取 12-01 月首仅为可读下界，效果等同「开市前一律无效」。
_MIN_VALID_LIST_DATE = date(1990, 12, 1)


def build_constituent_records(
    stocks: pl.DataFrame,
) -> tuple[list[dict[str, object]], int]:
    """注册表行 → PIT 成分记录；返回 (records, 跳过的无效上市日行数)."""
    if stocks.is_empty():
        return [], 0
    frame = stocks.filter(pl.col("asset_class") == "stock")
    if frame.schema.get("list_date") == pl.String:
        frame = frame.with_columns(
            pl.col("list_date").str.to_date(),
            pl.col("delist_date").str.to_date(strict=False),
        )
    valid = frame.filter(
        pl.col("list_date").is_not_null()
        & (pl.col("list_date") >= _MIN_VALID_LIST_DATE)
    )
    # find_securities 对 instrument_mapping 的 LEFT JOIN 每条 source 映射
    # 返回一行（fuyao 冗余源摄取会登记第二条映射）——同一 instrument 的
    # 重复行若不去重，裸 INSERT 撞 universe_constituent 主键
    # (universe_id, instrument_id, effective_from) 且发生在 create_universe
    # 已提交之后，残留 0 成员宇宙。按 instrument_id 去重，优先保留带
    # source_ticker 的映射行。
    listed = valid.sort(["instrument_id", "source_ticker"], nulls_last=True).unique(
        subset=["instrument_id"],
        keep="first",
    )
    records = [
        {
            "instrument_id": row["instrument_id"],
            "effective_from": str(row["list_date"]),
            "effective_to": (
                str(row["delist_date"]) if row["delist_date"] is not None else None
            ),
            "source": "instrument_registry",
            "source_ticker": row.get("source_ticker") or row.get("ticker"),
        }
        for row in listed.iter_rows(named=True)
    ]
    return records, frame.height - valid.height


def main(argv: list[str] | None = None) -> int:
    """物化 csi_a_share 证券池；成功返回 0，已存在/空注册表返回 2."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="已存在时删除重建")
    args = parser.parse_args(argv)

    container = make_app_container()
    try:
        metadata = container.get(MetadataService)
        existing = metadata.universe.get_universe_detail(UNIVERSE_ID)
        if existing is not None and not args.force:
            sys.stderr.write(
                f"{UNIVERSE_ID} 已存在: {existing}; 使用 --force 重建\n",
            )
            return 2

        stocks = metadata.find_securities(asset_class="stock", is_active=None)
        records, skipped = build_constituent_records(stocks)
        if not records:
            sys.stderr.write("注册表无带上市日的股票行 - 拒绝创建空证券池\n")
            return 2

        if existing is not None:
            metadata.universe.delete_universe(UNIVERSE_ID)
        metadata.universe.create_universe(
            UNIVERSE_ID,
            name="A股全市场(注册表PIT区间)",
            description=(
                "由 instrument 注册表 list_date/delist_date 物化的历史证券池"
                "(#196 策略腿回测车道); 新上市/退市后需 --force 重建"
            ),
            universe_type="derived",
            source_ref="instrument_registry",
        )
        added = metadata.universe.add_constituents(UNIVERSE_ID, records)
        summary = {
            "universe_id": UNIVERSE_ID,
            "constituents": added,
            "skipped_null_list_date": skipped,
        }
        sys.stdout.write(orjson.dumps(summary).decode() + "\n")
        return 0
    finally:
        container.close()


if __name__ == "__main__":
    raise SystemExit(main())
