"""统一数据写入器 — 行情/基本面/资本面/宏观/元数据写入."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import ClassVar, Literal, cast

import polars as pl
from ditto_data.catalog.source_snapshot import ProviderSnapshot
from ditto_data.config.dataset_checksum import dataset_sort_keys
from ditto_data.models import Dataset, Source
from ditto_data.services.capital_store import CapitalStore
from ditto_data.services.fundamental_store import FundamentalStore
from ditto_data.services.macro_service import MacroService
from ditto_data.services.market_write_service import MarketWriteService
from ditto_data.services.metadata_service import MetadataService
from ditto_platform.foundation import ChecksumCompute, OnDuplicate, WriteResult, logger
from ditto_platform.foundation.storage import CORRECTION_FLAG_COLUMN

from ditto_application.exceptions import AppProcessError
from ditto_application.processes.ingestion.dataset_registry import (
    DatasetRegistration,
    WriteKind,
    default_dataset_registry,
)


def _enrich_with_instrument_id(
    df: pl.DataFrame,
    instrument_id_mapping: dict[str, int],
    source_ticker_col: str,
    source: str,
) -> pl.DataFrame:
    """
    为 DataFrame 添加 instrument_id/source_ticker/source 列。

    Args:
        df: 输入 DataFrame，必须包含 source_ticker_col 指定的列
        instrument_id_mapping: {source_ticker: instrument_id} 映射字典
        source_ticker_col: 源代码列名
        source: 数据源标识符

    Returns:
        添加了 instrument_id、source_ticker 和 source 列的 DataFrame

    """
    standardized_df = (
        df.rename({source_ticker_col: "source_ticker"})
        if source_ticker_col != "source_ticker"
        else df
    )
    standardized_df = standardized_df.with_columns(
        pl.col("source_ticker").cast(pl.Utf8)
    )

    # 处理空 DataFrame
    if len(standardized_df) == 0:
        return standardized_df.with_columns(
            pl.lit(None, dtype=pl.Int64).alias("instrument_id"),
            pl.lit(source).alias("source"),
        )

    # 将 instrument_id 映射转换为 DataFrame 并 join
    mapping_df = pl.DataFrame(
        {
            "source_ticker": list(instrument_id_mapping.keys()),
            "instrument_id": list(instrument_id_mapping.values()),
        },
        schema={"source_ticker": pl.Utf8, "instrument_id": pl.Int64},
    )

    return standardized_df.join(
        mapping_df, on="source_ticker", how="left"
    ).with_columns(pl.lit(source).alias("source"))


def _to_write_result(
    dataset: str,
    year: int,
    df: pl.DataFrame,
    rows_written: int,
    *,
    on_duplicate: OnDuplicate = OnDuplicate.ERROR,
) -> WriteResult:
    """
    将写入结果转换为 WriteResult。

    Args:
        dataset: 数据集名称
        year: 年份
        df: 写入的 DataFrame（用于计算 checksum）
        rows_written: 写入行数
        on_duplicate: 重试校验模式按已接受载荷记录行数

    Returns:
        WriteResult 对象

    """
    if on_duplicate is OnDuplicate.VERIFY_IDENTICAL:
        rows_written = len(df)
    checksum = ChecksumCompute.from_dataframe(df, dataset_sort_keys(dataset))
    return WriteResult(
        file_path=f"{dataset}/{year}",
        checksum=checksum,
        rows_written=rows_written,
        rows_total=rows_written,
        blocked=False,  # blocked 仅由显式 DQ 检查设置，不从 rows_written 推断
    )


def _normalize_iso_date(value: str) -> str:
    """把 YYYYMMDD / YYYY-MM-DD 统一为 YYYY-MM-DD。"""
    compact = value.replace("-", "")
    return f"{compact[:4]}-{compact[4:6]}-{compact[6:8]}"


def _validate_index_weight_totals(df: pl.DataFrame) -> None:
    """
    Reject incomplete index snapshots using provider percentage tolerance.

    校验对象是供应商帧（FK 富化前），不要求 instrument_id 列。
    """
    percentage_scale_threshold = 2.0
    required = {"index_id", "trade_date", "weight"}
    missing = required - set(df.columns)
    if missing:
        raise AppProcessError(
            f"index_weight missing required columns: {sorted(missing)}",
            field="columns",
            value=tuple(sorted(missing)),
        )
    totals = df.group_by("index_id", "trade_date").agg(
        pl.col("weight").sum().alias("weight_total")
    )
    invalid: list[tuple[str, str, float]] = []
    for row in totals.to_dicts():
        total = float(row["weight_total"])
        expected = 100.0 if total > percentage_scale_threshold else 1.0
        if abs(total - expected) > expected * 0.02:
            invalid.append((str(row["index_id"]), str(row["trade_date"]), total))
    if invalid:
        raise AppProcessError(
            "index_weight total is outside 2% tolerance",
            field="weight",
            value=tuple(invalid),
        )


_DUAL_REGIME_TOLERANCE = 2.0


def _collapse_dual_regime_weight_month(
    df: pl.DataFrame, source_ticker_col: str
) -> pl.DataFrame:
    """
    同一观察日的双制度月度权重归一 (#592，形态分化规则).

    北交所 2025-10 换码过渡期，上游对同一 (index, 观察日) 会混发
    43/83/87 老码与 920 新码两种制度行。两种实测形态（2026-10-23 全量
    探针，899050.BJ）：
    - **重复形**（2023-11）：两制度各为完整快照，子和各≈100、
      合计≈200——保留行数多的制度；并列保留老码（与前后月连续）。
    - **互补形**（2025-04~08）：两制度各携带部分成员（老码≈92 +
      新码≈8），合计恰≈100——保留并集（同一快照的成员被拆到两种
      代码制度）。
    两种形态都不满足的月份不触碰，交由总额校验 fail-closed。
    非北交所形状（无制度标注）不触碰。
    """
    if df.is_empty():
        return df
    ticker = pl.col(source_ticker_col)
    old_regime = ticker.str.contains(r"^(43|83|87)\d{4}\.BJ$")
    new_regime = ticker.str.contains(r"^920\d{3}\.BJ$")
    if not df.filter(old_regime).height or not df.filter(new_regime).height:
        return df
    annotated = df.with_columns(
        pl.when(old_regime)
        .then(pl.lit("old"))
        .when(new_regime)
        .then(pl.lit("new"))
        .otherwise(pl.lit(None))
        .alias("_regime")
    )
    per_month = (
        annotated.group_by("index_id", "trade_date")
        .agg(
            (pl.col("_regime") == "old").sum().alias("_old_rows"),
            (pl.col("_regime") == "new").sum().alias("_new_rows"),
            pl.when(pl.col("_regime") == "old")
            .then(pl.col("weight"))
            .otherwise(0.0)
            .sum()
            .alias("_old_sum"),
            pl.when(pl.col("_regime") == "new")
            .then(pl.col("weight"))
            .otherwise(0.0)
            .sum()
            .alias("_new_sum"),
        )
        .filter((pl.col("_old_rows") > 0) & (pl.col("_new_rows") > 0))
    )
    if per_month.is_empty():
        return df
    # 重复形判定：两制度和都在 100±2 → 丢弃行数少的制度（并列丢新码）
    duplicate_form = ((pl.col("_old_sum") - 100.0).abs() <= _DUAL_REGIME_TOLERANCE) & (
        (pl.col("_new_sum") - 100.0).abs() <= _DUAL_REGIME_TOLERANCE
    )
    keep = per_month.select(
        "index_id",
        "trade_date",
        pl.when(duplicate_form & (pl.col("_old_rows") >= pl.col("_new_rows")))
        .then(pl.lit("old"))
        .when(duplicate_form)
        .then(pl.lit("new"))
        # 互补形/未判定 → 保留全部（_keep_regime 为 null 时不过滤）
        .otherwise(pl.lit(None))
        .alias("_keep_regime"),
    )
    collapsed = keep.filter(pl.col("_keep_regime").is_not_null()).height
    if collapsed:
        logger.warning(
            "index_weight collapsed dual-regime duplicate month",
            event="index_weight_dual_regime_collapse",
            months=collapsed,
        )
    return (
        annotated.join(keep, on=["index_id", "trade_date"], how="left")
        .filter(
            pl.col("_keep_regime").is_null()
            | pl.col("_regime").is_null()
            | (pl.col("_regime") == pl.col("_keep_regime"))
        )
        .drop("_regime", "_keep_regime")
    )


def _settle_same_issuer_dual_code(
    enriched_df: pl.DataFrame, source_ticker_col: str
) -> pl.DataFrame:
    """
    FK 富化后的同发行人双码行确定性收敛 (#592 correctness F2).

    互补形月里同一发行人可同时以新旧两码出现，别名解析后两行命中写侧
    PK (index_id, instrument_id, trade_date)，ON CONFLICT 会静默吞行且
    胜者随行序漂移。收敛：保 920 新码行（换码后权威口径），告警留痕。
    """
    pk_cols = ["index_id", "instrument_id", "trade_date"]
    pk_dupes = enriched_df.group_by(pk_cols).len().filter(pl.col("len") > 1)
    if not pk_dupes.height:
        return enriched_df
    is_new_code = pl.col(source_ticker_col).str.contains(r"^920\d{3}\.BJ$")
    settled = (
        enriched_df.with_columns(is_new_code.cast(pl.UInt8).alias("_r"))
        .sort([*pk_cols, "_r"])
        .unique(subset=pk_cols, keep="last")
        .drop("_r")
    )
    logger.warning(
        "index_weight settled same-issuer dual-code rows after FK",
        event="index_weight_same_issuer_dual_code",
        dropped_rows=enriched_df.height - settled.height,
        affected_keys=pk_dupes.height,
    )
    return settled


# BSE 持仓码形：6 位数字 + .BJ（老码 43x/83x/87x 全段 + 新码 920 段，#592）。
_BSE_CODE_PATTERN = re.compile(r"\d{6}\.BJ")


def _settle_fund_portfolio_dual_code(
    enriched_df: pl.DataFrame, holding_id_map: dict[str, int]
) -> pl.DataFrame:
    """
    FK 富化后的 fund_portfolio 北交所双码持仓收敛 (#606).

    tushare 可把同一 BSE 持仓同时挂新旧两码返回；写侧键含
    holding_symbol 原码（双码=不同键），两行都落库后 instrument 级
    聚合重复计数同一持仓（#599 F5）。收敛：holding_id_map 给出持仓码
    →instrument 解析（含 #592 别名）时，同 (基金 instrument_id,
    report_date, knowledge_date, 持仓 instrument) 的多码行保一行——
    少 null 优先（保数据），平局取 920 新码（换码后权威口径），再平局
    按 holding_symbol 升序保证全序。未解析码（map 外，如 .HK）各占
    自身键，不参与收敛。确定性、重拉幂等。
    """
    if not holding_id_map:
        return enriched_df
    pk_cols = ["instrument_id", "report_date", "knowledge_date"]
    joined = enriched_df.join(
        pl.DataFrame(
            {
                "holding_symbol": list(holding_id_map),
                "_holding_id": list(holding_id_map.values()),
            }
        ),
        on="holding_symbol",
        how="left",
    ).with_columns(
        # ponytail: null holding_symbol 行坍缩为同一 null 键且胜者随输入
        # 行序漂移——与修复前 store 批内同键去重同类坍缩（非回归），
        # 真要逐行保键时改用行唯一占位键。
        pl.when(pl.col("_holding_id").is_not_null())
        .then(pl.format("id:{}", pl.col("_holding_id")))
        .otherwise(pl.format("code:{}", pl.col("holding_symbol")))
        .alias("_holding_key")
    )
    settle_keys = [*pk_cols, "_holding_key"]
    pk_dupes = joined.group_by(settle_keys).len().filter(pl.col("len") > 1)
    if not pk_dupes.height:
        return enriched_df
    value_cols = [
        c for c in enriched_df.columns if c not in {*pk_cols, "holding_symbol"}
    ]
    # 空 value_cols（仅键+代码列的帧）不能交给 sum_horizontal([])——空
    # fold 会 ComputeError；此时收敛退化为纯代码偏好。
    null_count = (
        pl.sum_horizontal([pl.col(c).is_null().cast(pl.UInt32) for c in value_cols])
        if value_cols
        else pl.lit(0, dtype=pl.UInt32)
    ).alias("_nulls")
    is_new_code = pl.col("holding_symbol").str.contains(r"^920\d{3}\.BJ$")
    settled = (
        joined.with_columns(null_count, is_new_code.cast(pl.UInt8).alias("_r"))
        .sort(
            [*settle_keys, "_nulls", "_r", "holding_symbol"],
            descending=[False, False, False, False, True, False, False],
        )
        .unique(subset=settle_keys, keep="last")
        .drop("_nulls", "_r", "_holding_id", "_holding_key")
        # unique 不保序——按写侧键全序输出，否则同输入的 checksum 逐次
        # 漂移（correctness review #606 F2，fund_portfolio 缺席 _SORT_KEYS）。
        .sort([*pk_cols, "holding_symbol"])
    )
    logger.warning(
        "fund_portfolio settled BSE dual-code holding rows after FK",
        event="fund_portfolio_bse_dual_code",
        dropped_rows=enriched_df.height - settled.height,
        affected_keys=pk_dupes.height,
    )
    return settled


def _settle_fina_indicator_dual_code(
    enriched_df: pl.DataFrame, source_ticker_col: str = "source_ticker"
) -> pl.DataFrame:
    """
    FK 富化后的 fina_indicator 北交所双码同披露键收敛 (#599).

    tushare 把 BSE 历史行同时挂在新旧两码下返回，#592 别名注册后两码都
    解析到同一 instrument_id，适配器按 source_ticker 选版（两码不同键）
    无法收敛，双行命中写侧键 (instrument_id, report_date, knowledge_date)
    → 批内冲突 raise。收敛：少 null 行优先（920017 实测老码行多 4 个
    fcff 族值，保数据），平局取 920 新码行（换码后权威口径），再平局
    按 source_ticker 升序保证全序——多段改名可让同一 instrument 挂两条
    老码别名，(null 数, 新码) 全平仍可达，无最终键则胜者随行序漂移
    （correctness review #599 F3）。确定性、重拉幂等。
    """
    pk_cols = ["instrument_id", "report_date", "knowledge_date"]
    pk_dupes = enriched_df.group_by(pk_cols).len().filter(pl.col("len") > 1)
    if not pk_dupes.height:
        return enriched_df
    value_cols = [
        c
        for c in enriched_df.columns
        if c not in {*pk_cols, source_ticker_col, CORRECTION_FLAG_COLUMN}
    ]
    # 空 value_cols（仅键+代码列的帧）不能交给 sum_horizontal([])——空 fold
    # 会 ComputeError；此时收敛退化为纯代码偏好。
    null_count = (
        pl.sum_horizontal([pl.col(c).is_null().cast(pl.UInt32) for c in value_cols])
        if value_cols
        else pl.lit(0, dtype=pl.UInt32)
    ).alias("_nulls")
    is_new_code = pl.col(source_ticker_col).str.contains(r"^920\d{3}\.BJ$")
    # #613 G F2：修正标记是选版最高优先级——双码同键时未同步后端的陈旧
    # 920 行不得挤掉老码上的 update_flag 修正行。缺列（非 fina 生产者）
    # 退化为既有偏好序。
    correction_pref = (
        pl.col(CORRECTION_FLAG_COLUMN).fill_null(False).cast(pl.UInt8)
        if CORRECTION_FLAG_COLUMN in enriched_df.columns
        else pl.lit(0, dtype=pl.UInt8)
    ).alias("_corr")
    settled = (
        enriched_df.with_columns(null_count, is_new_code.cast(pl.UInt8).alias("_r"))
        .with_columns(correction_pref)
        .sort(
            [*pk_cols, "_corr", "_nulls", "_r", source_ticker_col],
            descending=[False, False, False, False, True, False, False],
        )
        .unique(subset=pk_cols, keep="last")
        .drop("_nulls", "_r", "_corr")
        # 同 #606 F2：全序输出防 checksum 逐次漂移（fina_indicator 同样
        # 缺席 _SORT_KEYS）。
        .sort([*pk_cols, source_ticker_col])
    )
    logger.warning(
        "fina_indicator settled BSE dual-code disclosure rows after FK",
        event="fina_indicator_bse_dual_code",
        dropped_rows=enriched_df.height - settled.height,
        affected_keys=pk_dupes.height,
    )
    return settled


@dataclass(frozen=True)
class _WriteContext:
    """Packed parameters for write handler dispatch."""

    registration: DatasetRegistration
    dataset: str
    dataset_enum: Dataset
    df: pl.DataFrame
    year: int
    on_duplicate: OnDuplicate
    source_ticker_col: str
    trade_date: str


class IngestionDataWriter:
    """统一数据写入器。"""

    def __init__(
        self,
        metadata_service: MetadataService,
        market_write_service: MarketWriteService,
        fundamental_store: FundamentalStore,
        capital_store: CapitalStore,
        macro_service: MacroService,
        source_name: str,
    ) -> None:
        """
        初始化 IngestionDataWriter。

        Args:
            metadata_service: MetadataService 实例
            market_write_service: MarketWriteService 实例
            fundamental_store: FundamentalStore 实例
            capital_store: CapitalStore 实例
            macro_service: MacroService 实例
            source_name: 数据源名称

        """
        self._metadata_service = metadata_service
        self._market_write_service = market_write_service
        self._fundamental_store = fundamental_store
        self._capital_store = capital_store
        self._macro_service = macro_service
        self._source_name = source_name

    def write_data(
        self,
        dataset: str,
        df: pl.DataFrame,
        trade_date: str,
        on_duplicate: OnDuplicate = OnDuplicate.ERROR,
    ) -> WriteResult:
        """
        根据数据集类型写入对应的 Store。

        Args:
            dataset: 数据集名称
            df: 要写入的数据
            trade_date: 交易日期
            on_duplicate: 重复数据处理策略

        Returns:
            WriteResult: 写入结果

        Raises:
            AppProcessError: 不支持的数据集

        """
        try:
            dataset_enum = Dataset(dataset)
        except ValueError as e:
            raise AppProcessError(
                f"不支持写入数据集: {dataset}",
                field="dataset",
                value=dataset,
            ) from e

        registration = default_dataset_registry().require(dataset_enum)
        year = int(trade_date[:4]) if registration.requires_year_partition else 0

        ctx = _WriteContext(
            registration=registration,
            dataset=dataset,
            dataset_enum=dataset_enum,
            df=df,
            year=year,
            on_duplicate=on_duplicate,
            source_ticker_col="source_ticker",
            trade_date=trade_date,
        )
        handler = self._build_write_handler(ctx)
        return handler()

    def _build_write_handler(self, ctx: _WriteContext) -> Callable[[], WriteResult]:
        """Build the writer callable from registry metadata."""
        if ctx.registration.write_kind == WriteKind.UNSUPPORTED:
            raise AppProcessError(
                f"不支持写入数据集: {ctx.dataset}",
                field="dataset",
                value=ctx.dataset,
            )
        handler_name = self._HANDLER_NAMES.get(ctx.registration.write_kind)
        if handler_name is None:
            raise AppProcessError(
                f"未知写入路由: {ctx.registration.write_kind.value}",
                field="dataset",
                value=ctx.dataset,
            )
        handler = getattr(self, handler_name)
        return handler(ctx)

    _HANDLER_NAMES: ClassVar[dict[WriteKind, str]] = {
        WriteKind.TRADED_BARS: "_handler_traded_bars",
        WriteKind.INSTRUMENT_CODE_BARS: "_handler_instrument_code_bars",
        WriteKind.STOCK_STATUS: "_handler_stock_status",
        WriteKind.ADJ_FACTOR: "_handler_adj_factor",
        WriteKind.FUND_ADJ: "_handler_fund_adj",
        WriteKind.ETF_NAV: "_handler_etf_nav",
        WriteKind.STOCK_LIMIT: "_handler_stock_limit",
        WriteKind.LIMIT_LIST: "_handler_limit_list",
        WriteKind.FUND_SHARE: "_handler_fund_share",
        WriteKind.INDEX_WEIGHT: "_handler_index_weight",
        WriteKind.FUNDAMENTAL: "_handler_fundamental",
        WriteKind.CAPITAL: "_handler_capital",
        WriteKind.MACRO: "_handler_macro",
        WriteKind.CALENDAR: "_handler_calendar",
        WriteKind.BASIC: "_handler_basic",
        WriteKind.GLOBAL_INDEX_BARS: "_handler_global_index_bars",
        WriteKind.INDUSTRY_CLASSIFICATION: "_handler_industry_classification",
        WriteKind.INDUSTRY_MAPPING: "_handler_industry_mapping",
        WriteKind.NAME_HISTORY: "_handler_name_history",
        WriteKind.ST_CHANGE_HISTORY: "_handler_st_change_history",
        WriteKind.ETF_REFERENCE: "_handler_etf_reference",
        WriteKind.ETF_REFERENCE_CONFIG: "_handler_etf_reference_config",
        WriteKind.FUTURES_BARS: "_handler_futures_bars",
        WriteKind.FUTURES_BASIC: "_handler_futures_basic",
        WriteKind.EARNINGS_EVENT: "_handler_earnings_event",
        WriteKind.INDEX_VALUATION: "_handler_index_valuation",
    }

    def _handler_traded_bars(self, ctx: _WriteContext) -> Callable[[], WriteResult]:
        bars_dataset = cast(
            Literal[
                "stock_daily",
                "etf_daily",
                "index_daily",
                "fx_daily",
                "commodity_daily",
            ],
            ctx.registration.write_dataset,
        )
        return lambda: self._write_traded_bars(
            ctx.dataset,
            ctx.df,
            ctx.year,
            ctx.on_duplicate,
            ctx.source_ticker_col,
            bars_dataset,
        )

    def _handler_instrument_code_bars(
        self, ctx: _WriteContext
    ) -> Callable[[], WriteResult]:
        bars_dataset = cast(
            Literal["fx_daily", "commodity_daily"],
            ctx.registration.write_dataset,
        )
        return lambda: self._write_instrument_code_bars(
            ctx.dataset, ctx.df, ctx.year, ctx.on_duplicate, bars_dataset
        )

    def _handler_stock_status(self, ctx: _WriteContext) -> Callable[[], WriteResult]:
        return lambda: self._write_stock_status(
            ctx.dataset, ctx.df, ctx.year, ctx.source_ticker_col
        )

    def _handler_adj_factor(self, ctx: _WriteContext) -> Callable[[], WriteResult]:
        return lambda: self._write_adj_factor(
            ctx.dataset, ctx.df, ctx.year, ctx.on_duplicate, ctx.source_ticker_col
        )

    def _handler_futures_bars(self, ctx: _WriteContext) -> Callable[[], WriteResult]:
        return lambda: self._write_futures_bars(
            ctx.dataset, ctx.df, ctx.year, ctx.on_duplicate
        )

    def _handler_futures_basic(self, ctx: _WriteContext) -> Callable[[], WriteResult]:
        return lambda: self._write_futures_basic(
            ctx.dataset, ctx.df, ctx.year, ctx.on_duplicate
        )

    def _handler_fund_adj(self, ctx: _WriteContext) -> Callable[[], WriteResult]:
        return lambda: self._write_fund_adj(
            ctx.dataset, ctx.df, ctx.year, ctx.on_duplicate, ctx.source_ticker_col
        )

    def _handler_etf_nav(self, ctx: _WriteContext) -> Callable[[], WriteResult]:
        return lambda: self._write_etf_nav(
            ctx.dataset, ctx.df, ctx.year, ctx.on_duplicate, ctx.source_ticker_col
        )

    def _handler_stock_limit(self, ctx: _WriteContext) -> Callable[[], WriteResult]:
        return lambda: self._write_stock_limit(
            ctx.dataset, ctx.df, ctx.year, ctx.on_duplicate, ctx.source_ticker_col
        )

    def _handler_limit_list(self, ctx: _WriteContext) -> Callable[[], WriteResult]:
        return lambda: self._write_limit_list(
            ctx.dataset, ctx.df, ctx.year, ctx.on_duplicate, ctx.source_ticker_col
        )

    def _handler_fund_share(self, ctx: _WriteContext) -> Callable[[], WriteResult]:
        return lambda: self._write_fund_share(
            ctx.dataset, ctx.df, ctx.year, ctx.on_duplicate, ctx.source_ticker_col
        )

    def _handler_index_weight(self, ctx: _WriteContext) -> Callable[[], WriteResult]:
        return lambda: self._write_index_weight(
            ctx.dataset, ctx.df, ctx.year, ctx.source_ticker_col
        )

    def _handler_earnings_event(self, ctx: _WriteContext) -> Callable[[], WriteResult]:
        return lambda: self._write_earnings_event(
            ctx.dataset, ctx.dataset_enum, ctx.df, ctx.year, ctx.on_duplicate
        )

    def _handler_index_valuation(self, ctx: _WriteContext) -> Callable[[], WriteResult]:
        return lambda: self._write_index_valuation(
            ctx.dataset, ctx.df, ctx.year, ctx.on_duplicate, ctx.source_ticker_col
        )

    def _handler_fundamental(self, ctx: _WriteContext) -> Callable[[], WriteResult]:
        return lambda: self._write_fundamental(
            ctx.dataset,
            ctx.dataset_enum,
            ctx.df,
            ctx.year,
            on_duplicate=ctx.on_duplicate,
        )

    def _handler_capital(self, ctx: _WriteContext) -> Callable[[], WriteResult]:
        return lambda: self._write_capital(
            ctx.dataset, ctx.dataset_enum, ctx.df, ctx.year, ctx.on_duplicate
        )

    def _handler_macro(self, ctx: _WriteContext) -> Callable[[], WriteResult]:
        return lambda: self._write_macro(ctx.dataset, ctx.df, ctx.year)

    def _handler_calendar(self, ctx: _WriteContext) -> Callable[[], WriteResult]:
        return lambda: self._write_calendar(ctx.df, ctx.trade_date)

    def _handler_basic(self, ctx: _WriteContext) -> Callable[[], WriteResult]:
        asset_class = ctx.registration.basic_asset_class
        if asset_class is None:
            raise AppProcessError(
                f"数据集 {ctx.dataset} 缺少 basic_asset_class 定义",
                field="dataset",
                value=ctx.dataset,
            )
        return lambda: self._write_basic(ctx.df, ctx.trade_date, asset_class)

    def _handler_global_index_bars(
        self, ctx: _WriteContext
    ) -> Callable[[], WriteResult]:
        return lambda: self._write_global_index_bars(
            ctx.dataset,
            ctx.df,
            ctx.year,
            ctx.on_duplicate,
        )

    def _handler_industry_classification(
        self, ctx: _WriteContext
    ) -> Callable[[], WriteResult]:
        return lambda: self._write_industry_read_model(
            ctx.dataset,
            ctx.df,
            "save_industry_classification",
        )

    def _handler_industry_mapping(
        self, ctx: _WriteContext
    ) -> Callable[[], WriteResult]:
        return lambda: self._write_industry_read_model(
            ctx.dataset,
            ctx.df,
            "save_industry_mapping",
        )

    def _handler_name_history(self, ctx: _WriteContext) -> Callable[[], WriteResult]:
        """Namechange 摄取 → instrument_name_history（带证据三元组）。"""
        return lambda: self._write_instrument_history(
            ctx.dataset,
            ctx.df,
            "save_name_history",
        )

    def _handler_st_change_history(
        self, ctx: _WriteContext
    ) -> Callable[[], WriteResult]:
        """st_history 摄取 → st_change_history（带证据三元组）。"""
        return lambda: self._write_instrument_history(
            ctx.dataset,
            ctx.df,
            "save_st_change_history",
        )

    def _write_instrument_history(
        self,
        dataset: str,
        df: pl.DataFrame,
        method_name: Literal["save_name_history", "save_st_change_history"],
    ) -> WriteResult:
        """
        历史事件写入：行携带 生效时间 + 可知时间 + 来源。

        缺真实生效日期的行在服务层被拒绝（计数日志），绝不以默认日期
        冒充真实历史；写入按 (生效键, 来源) 幂等。
        """
        method = getattr(self._metadata_service.instrument, method_name)
        rows_written = method(
            df,
            source=self._source_name,
            observed_at=datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
        )
        return _to_write_result(dataset, 0, df, rows_written)

    def _handler_etf_reference(self, ctx: _WriteContext) -> Callable[[], WriteResult]:
        """etf_basic 摄取：注册 + 扩展表接通 + 参考观察行产出。"""
        asset_class = ctx.registration.basic_asset_class
        if asset_class != "etf":
            raise AppProcessError(
                f"数据集 {ctx.dataset} 的 etf_reference 路由要求 etf basic",
                field="dataset",
                value=ctx.dataset,
            )
        return lambda: self._write_etf_basic_with_reference(
            ctx.df, ctx.trade_date, asset_class
        )

    def _handler_etf_reference_config(
        self, ctx: _WriteContext
    ) -> Callable[[], WriteResult]:
        """etf_reference 声明摄取：登记 config 身份映射，观察行在 post-ingest 落库。"""
        return lambda: self._write_etf_reference_config(ctx.df, ctx.trade_date)

    def _write_etf_reference_config(
        self, df: pl.DataFrame, trade_date: str
    ) -> WriteResult:
        """按声明登记 source='config' 映射；未解析身份的标的 fail closed。"""
        if df.is_empty() or "source_ticker" not in df.columns:
            raise AppProcessError(
                "etf_reference declaration is empty; refusing identity-free write"
            )
        evidence_dates: dict[str, str] = {}
        for row in df.to_dicts():
            ticker = str(row["source_ticker"])
            day = _normalize_iso_date(str(row["effective_from"]))
            # 身份锚定取该标的最早有证据日期（与映射登记合同一致），
            # 不随声明字段排序/增删漂移。
            if ticker not in evidence_dates or day < evidence_dates[ticker]:
                evidence_dates[ticker] = day
        resolved = (
            self._metadata_service.instrument.resolve_config_reference_instruments(
                sorted(evidence_dates),
                evidence_dates=evidence_dates,
                observed_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            )
        )
        unresolved = sorted(set(evidence_dates) - set(resolved))
        if unresolved:
            raise AppProcessError(
                "etf_reference declaration identity is unresolved: "
                + ", ".join(unresolved)
                + "; ingest etf_basic first",
                field="source_ticker",
                value=tuple(unresolved),
            )
        return _to_write_result("etf_reference", 0, df, len(df))

    def _write_etf_basic_with_reference(
        self,
        df: pl.DataFrame,
        trade_date: str,
        asset_class: Literal["stock", "etf", "index"],
    ) -> WriteResult:
        """Register ETF identities before projecting retained reference facts."""
        file_path, checksum = self._write_basic_impl(df, asset_class)
        return WriteResult(
            file_path=file_path,
            checksum=checksum,
            rows_written=len(df),
            rows_total=len(df),
            blocked=False,
        )

    def write_etf_reference(self, df: pl.DataFrame, snapshot: ProviderSnapshot) -> None:
        """Project only available basic facts, bound to the actual retained snapshot."""
        if (
            snapshot.dataset_id not in {"etf_basic", "etf_daily", "etf_reference"}
            or not snapshot.payload_retained
        ):
            raise AppProcessError(
                "ETF observations require retained basic or raw daily evidence"
            )
        if df.is_empty() or "source_ticker" not in df.columns:
            return
        if snapshot.dataset_id == "etf_reference":
            self._save_config_observations(df, snapshot)
            return
        observed_on = snapshot.request_end
        published_at = snapshot.created_at.astimezone(UTC).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        rows: list[dict[str, object]] = []
        for row in df.to_dicts():
            source_ticker = str(row["source_ticker"])
            fields: list[tuple[str, str, str]] = [
                (
                    "name",
                    str(row["name"]) if row.get("name") is not None else "",
                    "text",
                ),
                (
                    "exchange",
                    str(row["exchange"]) if row.get("exchange") is not None else "",
                    "text",
                ),
            ]
            if row.get("list_date") is not None:
                fields.append(
                    ("list_date", _normalize_iso_date(str(row["list_date"])), "date")
                )
            if snapshot.dataset_id == "etf_basic":
                fields.extend(
                    (field, str(row[field]), "text")
                    for field in (
                        "asset_class",
                        "tracking_index",
                        "list_status",
                        "etf_type",
                    )
                    if row.get(field) is not None
                )
            else:
                observed_on = _normalize_iso_date(str(row["trade_date"]))
                fields = (
                    [("price_close", str(row["close"]), "price")]
                    if row.get("close") is not None
                    else []
                )
            for field, value, unit in fields:
                if value == "":
                    continue  # 观察缺失不推断
                rows.append(
                    {
                        "source_ticker": source_ticker,
                        "field": field,
                        "value": value,
                        "unit": unit,
                        "observed_on": observed_on,
                        "published_at": published_at,
                        "effective_from": observed_on,
                        "effective_to": None,
                        "source": self._source_name,
                        "source_snapshot_id": snapshot.snapshot_id,
                    }
                )
        self._metadata_service.instrument.save_etf_reference_observations(rows)

    def _save_config_observations(
        self, df: pl.DataFrame, snapshot: ProviderSnapshot
    ) -> None:
        """声明式事实：观察日=本次摄取请求日，生效日=声明确认的生效日。"""
        observed_on = _normalize_iso_date(snapshot.request_end)
        published_at = snapshot.created_at.astimezone(UTC).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        observations: list[dict[str, object]] = []
        for row in df.to_dicts():
            value = row.get("value")
            if value is None or str(value) == "":
                continue  # 观察缺失不推断
            observations.append(
                {
                    "source_ticker": str(row["source_ticker"]),
                    "field": str(row["field"]),
                    "value": str(value),
                    "unit": str(row["unit"]),
                    "observed_on": observed_on,
                    "published_at": published_at,
                    "effective_from": _normalize_iso_date(str(row["effective_from"])),
                    "effective_to": None,
                    "source": self._source_name,
                    "source_snapshot_id": snapshot.snapshot_id,
                }
            )
        self._metadata_service.instrument.save_etf_reference_observations(observations)

    def _write_traded_bars(
        self,
        dataset: str,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate,
        source_ticker_col: str,
        bars_dataset: Literal[
            "stock_daily", "etf_daily", "index_daily", "fx_daily", "commodity_daily"
        ],
    ) -> WriteResult:
        """写入行情 K 线数据（stock/etf/index 共用）."""
        enriched_df = self._enrich_and_filter_fk_dataframe(
            df,
            dataset,
            year,
            source_ticker_col,
        )
        if enriched_df is None:
            return _to_write_result(dataset, year, df, 0)
        rows_written = self._market_write_service.save_bars(
            dataset=bars_dataset,
            df=enriched_df,
            year=year,
            on_duplicate=on_duplicate,
        )
        return _to_write_result(
            dataset, year, enriched_df, rows_written, on_duplicate=on_duplicate
        )

    def _write_global_index_bars(
        self,
        dataset: str,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate,
    ) -> WriteResult:
        """Persist global bars without inventing A-share instrument identities."""
        rows_written = self._market_write_service.save_global_index_bars(
            df=df,
            year=year,
            on_duplicate=on_duplicate,
        )
        return _to_write_result(
            dataset, year, df, rows_written, on_duplicate=on_duplicate
        )

    def _write_industry_read_model(
        self,
        dataset: str,
        df: pl.DataFrame,
        method_name: Literal[
            "save_industry_classification",
            "save_industry_mapping",
        ],
    ) -> WriteResult:
        """Persist the current SQLite read model; immutable PIT evidence is separate."""
        method = getattr(self._metadata_service.instrument, method_name)
        rows_written = method(df, source=self._source_name)
        return _to_write_result(dataset, 0, df, rows_written)

    def _write_instrument_code_bars(
        self,
        dataset: str,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate,
        bars_dataset: Literal["fx_daily", "commodity_daily"],
    ) -> WriteResult:
        """Write instrument code daily bars (FX or Commodity)."""
        rows_written = self._market_write_service.save_bars(
            dataset=bars_dataset,
            df=df,
            year=year,
            on_duplicate=on_duplicate,
        )
        return _to_write_result(
            dataset, year, df, rows_written, on_duplicate=on_duplicate
        )

    def _write_stock_status(
        self,
        dataset: str,
        df: pl.DataFrame,
        year: int,
        source_ticker_col: str,
    ) -> WriteResult:
        enriched_df = self._enrich_and_filter_fk_dataframe(
            df,
            dataset,
            year,
            source_ticker_col,
        )
        if enriched_df is None:
            return _to_write_result(dataset, year, df, 0)
        rows_written = self._market_write_service.save_stock_status(
            df=enriched_df,
            year=year,
        )
        return _to_write_result(
            dataset,
            year,
            enriched_df,
            rows_written,
        )

    def _write_adj_factor(
        self,
        dataset: str,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate,
        source_ticker_col: str,
    ) -> WriteResult:
        enriched_df = self._enrich_and_filter_fk_dataframe(
            df,
            dataset,
            year,
            source_ticker_col,
        )
        if enriched_df is None:
            return _to_write_result(dataset, year, df, 0)

        rows_written = self._market_write_service.save_adj_factor(
            df=enriched_df,
            year=year,
            on_duplicate=on_duplicate,
        )
        return _to_write_result(
            dataset,
            year,
            enriched_df,
            rows_written,
            on_duplicate=on_duplicate,
        )

    def _write_futures_bars(
        self,
        dataset: str,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate,
    ) -> WriteResult:
        """Write futures bars keyed by provider contract code (no FK enrichment)."""
        rows_written = self._market_write_service.save_futures_daily(
            df=df,
            year=year,
            on_duplicate=on_duplicate,
        )
        return _to_write_result(
            dataset, year, df, rows_written, on_duplicate=on_duplicate
        )

    def _write_futures_basic(
        self,
        dataset: str,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate,
    ) -> WriteResult:
        """Write the futures contract reference snapshot (knowledge-dated)."""
        rows_written = self._market_write_service.save_futures_basic(
            df=df,
            year=year,
            on_duplicate=on_duplicate,
        )
        return _to_write_result(
            dataset, year, df, rows_written, on_duplicate=on_duplicate
        )

    def _write_earnings_event(
        self,
        dataset: str,
        dataset_enum: Dataset,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate,
    ) -> WriteResult:
        """Write announcement-event rows keyed by provider ticker (no instrument FK)."""
        save_methods = {
            Dataset.EARNINGS_FORECAST: self._fundamental_store.save_earnings_forecast,
            Dataset.EARNINGS_EXPRESS: self._fundamental_store.save_earnings_express,
        }
        try:
            save_method = save_methods[dataset_enum]
        except KeyError:
            valid = ", ".join(str(member) for member in save_methods)
            raise AppProcessError(
                f"Unknown earnings dataset: {dataset}. Expected: {valid}",
                field="dataset",
                value=dataset,
            ) from None
        rows_written = save_method(df, year, on_duplicate=on_duplicate)
        return _to_write_result(
            dataset, year, df, rows_written, on_duplicate=on_duplicate
        )

    def _write_index_valuation(
        self,
        dataset: str,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate,
        source_ticker_col: str,
    ) -> WriteResult:
        """Write index daily valuation rows (instrument FK enriched)."""
        enriched_df = self._enrich_and_filter_fk_dataframe(
            df,
            dataset,
            year,
            source_ticker_col,
        )
        if enriched_df is None:
            return _to_write_result(dataset, year, df, 0)
        rows_written = self._capital_store.save_index_valuation(
            enriched_df,
            year,
            on_duplicate=on_duplicate,
        )
        return _to_write_result(
            dataset, year, enriched_df, rows_written, on_duplicate=on_duplicate
        )

    def _write_fund_adj(
        self,
        dataset: str,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate,
        source_ticker_col: str,
    ) -> WriteResult:
        """Write ETF adjustment factors through the dedicated ETF storage port."""
        enriched_df = self._enrich_and_filter_fk_dataframe(
            df,
            dataset,
            year,
            source_ticker_col,
        )
        if enriched_df is None:
            return _to_write_result(dataset, year, df, 0)
        rows_written = self._market_write_service.save_fund_adj(
            df=enriched_df,
            year=year,
            on_duplicate=on_duplicate,
        )
        return _to_write_result(
            dataset, year, enriched_df, rows_written, on_duplicate=on_duplicate
        )

    def _write_etf_nav(
        self,
        dataset: str,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate,
        source_ticker_col: str,
    ) -> WriteResult:
        """Write ETF NAV observations through the dedicated ETF storage port."""
        enriched_df = self._enrich_and_filter_fk_dataframe(
            df,
            dataset,
            year,
            source_ticker_col,
        )
        if enriched_df is None:
            return _to_write_result(dataset, year, df, 0)
        rows_written = self._market_write_service.save_fund_nav(
            df=enriched_df,
            year=year,
            on_duplicate=on_duplicate,
        )
        return _to_write_result(
            dataset, year, enriched_df, rows_written, on_duplicate=on_duplicate
        )

    def _write_stock_limit(
        self,
        dataset: str,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate,
        source_ticker_col: str,
    ) -> WriteResult:
        """Write up/down limit prices（元）through the stock-owned port（#517）."""
        enriched_df = self._enrich_and_filter_fk_dataframe(
            df,
            dataset,
            year,
            source_ticker_col,
        )
        if enriched_df is None:
            return _to_write_result(dataset, year, df, 0)
        rows_written = self._market_write_service.save_stock_limit(
            df=enriched_df,
            year=year,
            on_duplicate=on_duplicate,
        )
        return _to_write_result(
            dataset, year, enriched_df, rows_written, on_duplicate=on_duplicate
        )

    def _write_limit_list(
        self,
        dataset: str,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate,
        source_ticker_col: str,
    ) -> WriteResult:
        """Write limit-up/down list rows through the stock-owned port（#519）."""
        enriched_df = self._enrich_and_filter_fk_dataframe(
            df,
            dataset,
            year,
            source_ticker_col,
        )
        if enriched_df is None:
            return _to_write_result(dataset, year, df, 0)
        rows_written = self._market_write_service.save_limit_list(
            df=enriched_df,
            year=year,
            on_duplicate=on_duplicate,
        )
        return _to_write_result(
            dataset, year, enriched_df, rows_written, on_duplicate=on_duplicate
        )

    def _write_fund_share(
        self,
        dataset: str,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate,
        source_ticker_col: str,
    ) -> WriteResult:
        """Write fund share rows through the ETF-owned port（#522）."""
        enriched_df = self._enrich_and_filter_fk_dataframe(
            df,
            dataset,
            year,
            source_ticker_col,
        )
        if enriched_df is None:
            return _to_write_result(dataset, year, df, 0)
        rows_written = self._market_write_service.save_fund_share(
            df=enriched_df,
            year=year,
            on_duplicate=on_duplicate,
        )
        return _to_write_result(
            dataset, year, enriched_df, rows_written, on_duplicate=on_duplicate
        )

    def _write_index_weight(
        self,
        dataset: str,
        df: pl.DataFrame,
        year: int,
        source_ticker_col: str,
    ) -> WriteResult:
        """
        Write monthly weight observations as append-only facts (#452).

        trade_date 是月度权重观察日；公告/生效时刻官方未知，不伪造
        effective_from/effective_to 区间。总额校验作用于供应商原始帧
        （FK 过滤前）——注册表覆盖度（B股/北交所老码未注册）不是供应商
        完整性问题；上游偶发整月重复行先按源键去重（#196：899050.BJ
        2023-11 双份行，写侧 PK 本就是同键替换语义）。
        """
        if "index_code" in df.columns and "index_id" not in df.columns:
            df = df.rename({"index_code": "index_id"})
        if "index_id" not in df.columns:
            raise AppProcessError(
                "index_weight requires index_code",
                field="index_code",
                value=None,
            )
        if "trade_date" not in df.columns:
            raise AppProcessError(
                "index_weight requires trade_date",
                field="trade_date",
                value=None,
            )
        # 同源键不同值（上游修订同披露键）保留后见者，与写侧同键替换
        # last-wins 语义同向（correctness review #196：keep=first 依赖页序
        # 稳定，重试可落不同值）。
        deduped = df.unique(
            subset=["index_id", source_ticker_col, "trade_date"],
            keep="last",
            maintain_order=True,
        )
        if deduped.height != df.height:
            logger.warning(
                "index_weight dropped source-key duplicate rows before validation",
                event="index_weight_source_key_dedup",
                year=year,
                merged_rows=df.height,
                deduped_rows=deduped.height,
            )
        df = deduped
        df = _collapse_dual_regime_weight_month(df, source_ticker_col)
        _validate_index_weight_totals(df)
        enriched_df = self._enrich_and_filter_fk_dataframe(
            df,
            dataset,
            year,
            source_ticker_col,
        )
        if enriched_df is None:
            return _to_write_result(dataset, year, df, 0)
        # #592 correctness F2：互补形月里同一发行人可同时以新旧两码出现
        # （FK 富化后同 instrument_id 双行，命中写侧 PK 会被 ON CONFLICT
        # 静默吞行）。确定性收敛见 _settle_same_issuer_dual_code。
        enriched_df = _settle_same_issuer_dual_code(enriched_df, source_ticker_col)
        rows_written = self._capital_store.save_index_weight(enriched_df)
        return _to_write_result(dataset, year, enriched_df, rows_written)

    def _enrich_and_filter_fk_dataframe(
        self,
        df: pl.DataFrame,
        dataset: str,
        year: int,
        source_ticker_col: str = "source_ticker",
    ) -> pl.DataFrame | None:
        """
        解析 instrument_id 并过滤 null 外键记录。

        Args:
            df: 输入 DataFrame
            dataset: 数据集名称（用于日志）
            year: 年份（用于构造空结果）
            source_ticker_col: 源代码列名

        Returns:
            过滤后的 DataFrame，或 None 表示所有记录均被过滤。

        """
        if "instrument_id" not in df.columns:
            if self._source_name == Source.FUYAO.value and "trade_date" in df.columns:
                enriched_df = pl.concat(
                    [
                        _enrich_with_instrument_id(
                            part,
                            self._resolve_fuyao_ids_with_evidence(
                                part, source_ticker_col
                            ),
                            source_ticker_col,
                            self._source_name,
                        )
                        for part in df.sort("trade_date").partition_by(
                            "trade_date", maintain_order=True
                        )
                    ]
                )
            else:
                source_tickers = df[source_ticker_col].unique().to_list()
                instrument_id_mapping = (
                    self._metadata_service.instrument.resolve_instrument_ids_batch(
                        identifiers=source_tickers,
                        source=self._source_name,
                        asof=None,
                    )
                )
                enriched_df = _enrich_with_instrument_id(
                    df,
                    instrument_id_mapping,
                    source_ticker_col,
                    self._source_name,
                )
        else:
            enriched_df = df

        total_count = len(enriched_df)
        enriched_df = enriched_df.filter(pl.col("instrument_id").is_not_null())
        filtered_count = total_count - len(enriched_df)
        if filtered_count > 0:
            logger.warning(
                f"Filtered {filtered_count} records with null instrument_id",
                dataset=dataset,
            )

        if len(enriched_df) == 0:
            return None
        return enriched_df

    def _resolve_fuyao_ids_with_evidence(
        self,
        df: pl.DataFrame,
        source_ticker_col: str,
    ) -> dict[str, int]:
        """
        Fuyao 摄取路径的身份解析（#395）。

        既有 fuyao 映射优先；缺失但可经 ticker 前缀规则唯一匹配已注册
        instrument 的 thscode，按本批最早交易日（有证据日期）登记
        ``instrument_mapping(source='fuyao')`` 并复用；无法唯一匹配的键
        保持未解析 → 行被上层拒绝并计数。
        """
        evidence = (
            df.with_columns(pl.col("trade_date").cast(pl.Utf8).alias("_evidence_date"))
            .group_by(source_ticker_col)
            .agg(pl.col("_evidence_date").min().alias("earliest"))
        )
        evidence_dates = {
            str(row[source_ticker_col]): _normalize_iso_date(str(row["earliest"]))
            for row in evidence.to_dicts()
        }
        return self._metadata_service.instrument.resolve_fuyao_instrument_ids(
            list(evidence_dates.keys()),
            evidence_dates=evidence_dates,
            observed_at=datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
            register_missing=True,
        )

    def _write_fundamental(
        self,
        dataset: str,
        dataset_enum: Dataset,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate = OnDuplicate.ERROR,
    ) -> WriteResult:
        enriched_df = self._enrich_and_filter_fk_dataframe(df, dataset, year)
        if enriched_df is None:
            return _to_write_result(dataset, year, df, 0)

        # Map dataset enum to the appropriate save method
        save_methods = {
            Dataset.BALANCE_SHEET: self._fundamental_store.save_balance_sheet,
            Dataset.INCOME_STATEMENT: self._fundamental_store.save_income_statement,
            Dataset.CASH_FLOW: self._fundamental_store.save_cash_flow,
            Dataset.DIVIDEND: self._fundamental_store.save_dividend,
            Dataset.CORPORATE_ACTIONS: self._fundamental_store.save_corporate_actions,
        }
        # #521/#522：parquet 追加观察行，签名带 year/on_duplicate，分表分发
        parquet_save_methods = {
            Dataset.FINA_INDICATOR: self._fundamental_store.save_fina_indicator,
            Dataset.FUND_PORTFOLIO: self._fundamental_store.save_fund_portfolio,
        }
        parquet_method = parquet_save_methods.get(dataset_enum)
        if parquet_method is not None:
            if dataset_enum is Dataset.FINA_INDICATOR:
                # #599：BSE 新老双码同披露键收敛（fund_portfolio 见 #606）。
                enriched_df = _settle_fina_indicator_dual_code(enriched_df)
                # #613 G：fina_indicator 供应商以同披露键 update_flag='1' 行
                # 下发修正（#591），代理后端池同步进度不一使重拉值在两代
                # 快照间翻转——VERIFY_IDENTICAL 整批拒绝会把修正行永远挡在
                # 存量外并陪葬当日新披露。改走 KEEP_LAST_FLAGGED：修正行
                # （CORRECTION_FLAG_COLUMN=True）单调升级存量，非修正行只插
                # 新键（防未同步后端回写降级）。force 的 KEEP_LAST 语义更强，
                # 保持不变。
                if on_duplicate is OnDuplicate.VERIFY_IDENTICAL:
                    on_duplicate = OnDuplicate.KEEP_LAST_FLAGGED
            elif dataset_enum is Dataset.FUND_PORTFOLIO:
                # #606：键含 holding_symbol 原码，双码=不同键各存一行，
                # instrument 级聚合重复计数 → 持仓解析后收敛。
                enriched_df = self._settle_fund_portfolio_dual_code(enriched_df)
            records_written = parquet_method(
                enriched_df, year, on_duplicate=on_duplicate
            )
            if (
                dataset_enum is Dataset.FINA_INDICATOR
                and CORRECTION_FLAG_COLUMN in enriched_df.columns
            ):
                # 证据 checksum 按落库形状计算——瞬态标记列已在合并中消费。
                enriched_df = enriched_df.drop(CORRECTION_FLAG_COLUMN)
        else:
            save_method = save_methods[dataset_enum]
            records_written = save_method(enriched_df)
        return _to_write_result(
            dataset,
            year,
            enriched_df,
            records_written,
        )

    def _settle_fund_portfolio_dual_code(
        self, enriched_df: pl.DataFrame
    ) -> pl.DataFrame:
        """fund_portfolio 双码持仓收敛入口（#606）：BSE 形持仓码批量解析."""
        if "holding_symbol" not in enriched_df.columns:
            return enriched_df
        # 双码对只可能出现在 BSE 码形（6 位数字+.BJ——老码覆盖 43x/83x/
        # 87x 全段、新码 920 段，#592 别名按权威 bse_mapping 逐行登记
        # 不限前缀）；非 BSE 码不解析不收敛，省整批持仓解析开销。
        bse_codes = sorted(
            code
            for code in enriched_df["holding_symbol"].unique().to_list()
            if isinstance(code, str) and _BSE_CODE_PATTERN.fullmatch(code)
        )
        if not bse_codes:
            return enriched_df
        holding_id_map = self._metadata_service.instrument.resolve_instrument_ids_batch(
            identifiers=bse_codes,
            source=self._source_name,
            asof=None,
        )
        if not holding_id_map:
            # 全部未解析（别名未注册/被拒）：无可收敛对象，帧原样返回。
            return enriched_df
        return _settle_fund_portfolio_dual_code(enriched_df, holding_id_map)

    def _write_capital(
        self,
        dataset: str,
        dataset_enum: Dataset,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate = OnDuplicate.ERROR,
    ) -> WriteResult:
        enriched_df = self._enrich_and_filter_fk_dataframe(df, dataset, year)
        if enriched_df is None:
            return _to_write_result(dataset, year, df, 0)

        capital_dataset = cast(
            Literal[
                "valuation_metrics",
                "margin_trading",
                "pledge_ratio",
                "moneyflow",
                "cyq_perf",
                "hk_hold",
                "hsgt_top10",
                "top_list",
                "top_inst",
            ],
            dataset_enum.value,
        )
        capital_methods = {
            "valuation_metrics": self._capital_store.save_valuation_metrics,
            "margin_trading": self._capital_store.save_margin_trading,
            "pledge_ratio": self._capital_store.save_pledge_ratio,
        }
        capital_parquet_methods = {
            "moneyflow": self._capital_store.save_moneyflow,
            "cyq_perf": self._capital_store.save_cyq_perf,
            "hk_hold": self._capital_store.save_hk_hold,
            "hsgt_top10": self._capital_store.save_hsgt_top10,
            "top_list": self._capital_store.save_top_list,
            "top_inst": self._capital_store.save_top_inst,
        }
        # #518-#523 parquet 日频资金面帧：签名带 year
        parquet_method = capital_parquet_methods.get(capital_dataset)
        if parquet_method is not None:
            records_written = parquet_method(
                enriched_df, year, on_duplicate=on_duplicate
            )
            return _to_write_result(
                dataset,
                year,
                enriched_df,
                records_written,
            )
        # margin_trading 透传冲突策略（#625 correctness W1）：force→
        # KEEP_LAST 使重取的值修正在 SQLite 通路同样收敛；pledge/valuation
        # 的 spec 未声明冲突目标，维持既有冲突忽略语义。
        if capital_dataset == "margin_trading":
            records_written = self._capital_store.save_margin_trading(
                enriched_df, on_duplicate=on_duplicate
            )
            return _to_write_result(dataset, year, enriched_df, records_written)
        save_method = capital_methods.get(capital_dataset)
        if save_method is None:
            valid = ", ".join([*capital_methods, *capital_parquet_methods])
            raise AppProcessError(
                f"Unknown capital_dataset: {capital_dataset}. Expected: {valid}",
                field="dataset",
                value=capital_dataset,
                expected=(*capital_methods, *capital_parquet_methods),
            )
        records_written = save_method(enriched_df)
        return _to_write_result(
            dataset,
            year,
            enriched_df,
            records_written,
        )

    def _write_macro(
        self,
        dataset: str,
        df: pl.DataFrame,
        year: int,
    ) -> WriteResult:
        write_result = self._macro_service.save_indicators(df)
        return _to_write_result(
            dataset,
            year,
            df,
            write_result.records_written,
        )

    def _write_calendar(self, df: pl.DataFrame, trade_date: str) -> WriteResult:
        records = df.to_dicts()
        self._metadata_service.calendar.save_calendar(records=records)
        calendar_dates = tuple(str(record["trade_date"]) for record in records)
        if calendar_dates:
            self._metadata_service.calendar.enrich_calendar(
                min(calendar_dates),
                max(calendar_dates),
            )
        file_path = f"calendar_store:{trade_date}"
        checksum = ChecksumCompute.from_dataframe(df, dataset_sort_keys("calendar"))
        return WriteResult(
            file_path=file_path,
            checksum=checksum,
            rows_written=len(df),
            rows_total=len(df),
            blocked=False,
        )

    def _write_basic(
        self,
        df: pl.DataFrame,
        trade_date: str,
        asset_class: Literal["stock", "etf", "index"],
    ) -> WriteResult:
        file_path, checksum = self._write_basic_impl(df, asset_class)
        return WriteResult(
            file_path=file_path,
            checksum=checksum,
            rows_written=len(df),
            rows_total=len(df),
            blocked=False,
        )

    def _write_basic_impl(
        self,
        df: pl.DataFrame,
        asset_class: Literal["stock", "etf", "index"],
    ) -> tuple[str, str]:
        """
        使用 MetadataService 批量注册证券基础信息（幂等，依赖 PK 约束）。

        Args:
            df: 基础信息数据
            asset_class: 资产类别

        Returns:
            tuple[str, str]: (file_path, checksum)

        """
        return self._metadata_service.instrument.register_instruments_batch(
            df=df,
            source=self._source_name,
            asset_class=asset_class,
            source_ticker_col="source_ticker",
        )
