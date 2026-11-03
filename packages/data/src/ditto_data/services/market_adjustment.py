"""
Market 复权调整函数 — 从 MarketService 提取的独立调整逻辑.

提供 apply_adjustment 和 apply_etf_adjustment 模块级函数，
供 MarketService 委托调用。
"""

from __future__ import annotations

from datetime import date

import polars as pl
from ditto_platform.foundation import logger

from ditto_data.errors.integrity import AdjustmentFactorMissingError
from ditto_data.helpers.adjustment import apply_hfq_adj, apply_qfq_adj
from ditto_data.services.deps import MarketReaders
from ditto_data.services.market_types import AdjType


def apply_adjustment(
    df: pl.DataFrame,
    adj: AdjType,
    instrument_ids: list[int],
    start: date | None,
    end: date | None,
    asof: date | None,
    readers: MarketReaders,
) -> pl.DataFrame:
    """
    应用股票价格调整.

    Args:
        df: K线数据 DataFrame.
        adj: 调整类型.
        instrument_ids: Instrument ID 列表.
        start: 开始日期.
        end: 结束日期.
        asof: Point-in-Time 查询日期.
        readers: Market 域读取依赖.

    Returns:
        调整后的 DataFrame.

    """
    # 读取调整因子
    start_str = start.isoformat() if start else None
    end_str = end.isoformat() if end else None

    adj_df = readers.stock_adj.read(
        instrument_ids=instrument_ids,
        start_date=start_str,
        end_date=end_str,
    )

    if adj_df.is_empty():
        # 股票复权请求在窗口内完全没有因子 = 摄取缺口，fail closed
        # （#514：此前静默返回 raw 价，hfq/qfq 收益失真无告警）。
        # 指数/未复权读取不经此路径（query_bars 仅对 asset_class=stock
        # 调用本函数，raw/adj=none 不进入）。
        logger.warning(
            "No adjustment factor data available for stock adjustment request",
            event="market_bars_adj_not_available",
            adj_type=adj.value,
            instrument_count=len(instrument_ids),
        )
        raise AdjustmentFactorMissingError(
            f"stock adjustment requested ({adj.value}) but the adj_factor "
            + f"window has no rows for {len(instrument_ids)} instrument(s) — "
            + "ingest adj_factor or query with adj=none/raw (#514)"
        )

    # 确保排序以正确处理 last() 聚合；knowledge_date 参与排序使 join_asof
    # 的同 trade_date 并列取"最新已知修订"成为结构性保证（join_asof 取右帧
    # ≤ 键的最后一行，排序键含 knowledge_date 即晚知者胜）。
    sort_keys = ["instrument_id", "trade_date"]
    has_knowledge = "knowledge_date" in adj_df.columns
    if has_knowledge:
        sort_keys.append("knowledge_date")
    adj_df = adj_df.sort(sort_keys)

    # 关联调整因子。PIT 安全：asof 语义下 bar 行关联"截至 asof 已知、不晚于
    # 该行 trade_date"的最近因子（join_asof backward）——窗口越过 asof 的行
    # 不得因精确 join miss 而 fail-closed，PIT 回放正是要用 asof 时点已知
    # 因子覆盖整窗；标的完全无已知因子仍由 #514 行级守卫拦截。
    cols = ["instrument_id", "trade_date", "adj_factor"]
    if has_knowledge:
        cols.append("knowledge_date")
    # 行序契约：asof 与非 asof 路径对同一查询返回一致行序（下游 limit 依赖），
    # join 的任何重排以行号还原。
    df = df.with_row_index("__ditto_input_order")
    if asof is not None and has_knowledge:
        join_adj_df = adj_df.filter(pl.col("knowledge_date") <= asof)
        df = df.sort("trade_date").join_asof(
            join_adj_df.select(cols).sort(sort_keys),
            on="trade_date",
            by="instrument_id",
            strategy="backward",
        )
    else:
        df = df.join(
            adj_df.select(cols),
            on=["instrument_id", "trade_date"],
            how="left",
        )

    # 根据调整类型调用相应方法
    if adj == AdjType.QFQ:
        adjusted = apply_qfq_adj(df, adj_df, asof)
    else:  # HFQ
        adjusted = apply_hfq_adj(df, adj_df)
    return adjusted.sort("__ditto_input_order").drop("__ditto_input_order")


def apply_etf_adjustment(
    df: pl.DataFrame,
    adj: AdjType,
    start: str | None,
    end: str | None,
    readers: MarketReaders,
    *,
    instrument_ids: list[int] | None = None,
    asof: date | None = None,
) -> pl.DataFrame:
    """
    应用 ETF 价格调整.

    与 apply_adjustment() 同构，但读取 fund_adj（etf_adj 端口）。缺端口、
    整窗无因子、部分行关联不到因子均 fail closed（#514/#658 批次1D——
    此前缺端口静默返回 raw，通用入口则完全忽略 ETF 复权请求）。
    asof 语义与股票路径一致：bar 行关联"截至 asof 已知、不晚于该行
    trade_date"的最近因子（join_asof backward）。

    Args:
        df: ETF K线数据 DataFrame.
        adj: 调整类型.
        start: 开始日期 (YYYY-MM-DD).
        end: 结束日期 (YYYY-MM-DD).
        readers: Market 域读取依赖.
        instrument_ids: 可选的标的范围（None=全市场，专用入口口径）.
        asof: Point-in-Time 查询日期（通用入口 asof 查询）.

    Returns:
        调整后的 DataFrame.

    Raises:
        AdjustmentFactorMissingError: etf_adj 端口未配置、请求窗口内没有
            任何 fund_adj 行，或任一行关联不到因子（行级，#514）。

    """
    etf_adj = readers.etf_adj
    if etf_adj is None:
        raise AdjustmentFactorMissingError(
            f"ETF adjustment requested ({adj.value}) but the etf_adj reader "
            + "is not configured — refusing to return raw prices as "
            + "adjusted (#658 B1D); query with adj=none/raw explicitly"
        )

    adj_df = etf_adj.read(
        instrument_ids=instrument_ids,
        start_date=start,
        end_date=end,
    )

    if adj_df.is_empty():
        logger.warning(
            "No ETF adjustment factor data available for adjustment request",
            event="market_etf_bars_adj_not_available",
            adj_type=adj.value,
        )
        raise AdjustmentFactorMissingError(
            f"ETF adjustment requested ({adj.value}) but the fund_adj "
            + f"window [{start}, {end}] has no rows — ingest fund_adj or "
            + "query with adj=none (#514)"
        )

    # 确保排序以正确处理 last() 聚合；knowledge_date 参与排序使 join_asof
    # 的同 trade_date 并列取"最新已知修订"（与股票路径同构）。
    sort_keys = ["instrument_id", "trade_date"]
    has_knowledge = "knowledge_date" in adj_df.columns
    if has_knowledge:
        sort_keys.append("knowledge_date")
    adj_df = adj_df.sort(sort_keys)

    cols = ["instrument_id", "trade_date", "adj_factor"]
    if has_knowledge:
        cols.append("knowledge_date")
    # 行序契约：与非 asof 路径返回一致行序，join 重排以行号还原（同股票路径）。
    df = df.with_row_index("__ditto_input_order")
    if asof is not None and has_knowledge:
        join_adj_df = adj_df.filter(pl.col("knowledge_date") <= asof)
        df = df.sort("trade_date").join_asof(
            join_adj_df.select(cols).sort(sort_keys),
            on="trade_date",
            by="instrument_id",
            strategy="backward",
        )
    else:
        df = df.join(
            adj_df.select(cols),
            on=["instrument_id", "trade_date"],
            how="left",
        )

    # 根据调整类型调用相应方法
    if adj == AdjType.QFQ:
        adjusted = apply_qfq_adj(df, adj_df, asof)
    else:  # HFQ
        adjusted = apply_hfq_adj(df, adj_df)
    return adjusted.sort("__ditto_input_order").drop("__ditto_input_order")
