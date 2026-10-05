"""
fuyao 数据源门面 — 冗余源（ADR：Tushare 主源，fuyao 对账与故障日降级）.

能力（与 #199/#191 对齐）：
- ``fetch_stock_daily``：MarketFetcher 协议两模式 — trade_date 全市场单日
  （10 交易日 dump 一次下载 + 本地过滤，供 source=auto 摄取）；source_ticker
  + 起止日单标的 REST 历史（adjust=none）；
- ``fetch_stock_daily_bars``：对账协议帧（ticker 裸码，单日）；
- ``fetch_financial_statements``：财务三表对账协议帧（#473，ticker 保留
  完整 thscode；对账按标的隔离失败，报告显式未匹配）；
- 快照（A 股批量 / ETF 单只）：展示层用，不进管道；
- ``download_market_dump`` / ``daily_k_frame``：10 年日 K / 复权因子事件流
  Parquet 不可变快照与帧转换。

红线（#191）：只取原始价（adjust=none）与因子事件流，复权价快照不进因子
管道；fuyao 财务不作为披露锚（唯一锚 = Tushare f_ann_date）。ETF 历史为
前复权口径，不参与原始价摄取与对账。
"""

from __future__ import annotations

import tempfile
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Literal

import polars as pl
from ditto_platform.foundation import logger

from ditto_data.sources.base import SourceFetchError
from ditto_data.sources.fuyao.client import FuyaoClient, date_to_ms, ms_to_date

type DumpKind = Literal["daily-k", "daily-k-10d", "adjustment-factors"]

_DUMP_PATHS: dict[str, str] = {
    "daily-k": "/api/dump/market-dumps/daily-k/download-url",
    "daily-k-10d": "/api/dump/market-dumps/daily-k-10d/download-url",
    "adjustment-factors": "/api/dump/market-dumps/adjustment-factors/download-url",
}

# 裸码 → 交易所后缀（与 ts_code/thscode 同构；8/4 开头为北交所）
_TICKER_SUFFIX = {
    "6": ".SH",
    "5": ".SH",
    "0": ".SZ",
    "3": ".SZ",
    "1": ".SZ",
    "8": ".BJ",
    "4": ".BJ",
}

# 复权因子事件帧（#438 对账辅源）：事件字段保持公司行动原始口径，
# 不做股/元 → 手/千元的单位换算（量纲规则只适用于行情，不适用于事件）。
_ADJUSTMENT_EVENT_COLUMNS = (
    "ticker",
    "trade_date",
    "dividend_per_share",
    "per_share_bonus",
    "allotment_ratio",
    "allotment_price",
)

# 财务三表对账帧（#473）：fuyao 字段 → 内部存储列名（同口径字段才入映射；
# fuyao 无对应列的内部列不比较）。金额两侧均为元，无单位换算；
# disclosure_date 保留辅源披露日（vintage 判定用，非比较字段）。
_FINANCIAL_STATEMENT_PATHS: dict[str, str] = {
    "income_statement": "/api/a-share/financials/income-statements",
    "balance_sheet": "/api/a-share/financials/balance-sheets",
    "cash_flow": "/api/a-share/financials/cash-flow-statements",
}
_FINANCIAL_FIELD_RENAMES: dict[str, dict[str, str]] = {
    "income_statement": {
        "operating_income": "revenue",
        "operating_costs": "operate_cost",
        "sales_fee": "sale_exp",
        "manage_fee": "admin_exp",
        "research_and_development_expenses": "rd_exp",
        "operating_profit": "operating_profit",
        "profit_total": "total_profit",
        "income_tax_expense": "income_tax",
        "net_profit": "net_profit",
        "basic_eps": "eps",
    },
    "balance_sheet": {
        "assets_total": "total_assets",
        "total_current_assets": "current_assets",
        "cash": "money_cap",
        "accounts_receivable": "accounts_receivable",
        "total_debt": "total_liabilities",
        "holder_equity_total": "net_assets",
    },
    "cash_flow": {
        "act_cash_flow_net": "operating_cash_flow",
        "invest_cash_flow_net": "investing_cash_flow",
        "financing_cash_flow_net": "financing_cash_flow",
    },
}
_FINANCIAL_STATEMENT_COLUMNS = (
    "ticker",
    "report_date",
    "disclosure_date",
    "fiscal_year",
    "fiscal_period",
)

# ETF 净值对账帧（#475）：只取单位净值——fuyao adj_nav 是复权净值（官方明示
# 不等同于累计净值），与 Tushare acc_nav 口径不可等价比较（红线：不混列折算），
# 因此请求即不带 nav_type=adj。
_FUND_NAV_COLUMNS = ("ticker", "trade_date", "unit_nav")

_BAR_COLUMNS = (
    "source_ticker",
    "trade_date",
    "knowledge_date",
    "open",
    "high",
    "low",
    "close",
    "pre_close",
    "volume",
    "amount",
    "pct_change",
)

_BARS_RAW_SCHEMA: dict[str, type[pl.DataType]] = {
    "trade_date_ms": pl.Int64,
    "open": pl.Float64,
    "high": pl.Float64,
    "low": pl.Float64,
    "close": pl.Float64,
    "volume": pl.Float64,
    "amount": pl.Float64,
}


def to_thscode(ticker: str) -> str:
    """裸码 → thscode（与 ts_code 同构；对账反解按同一前缀规则）。"""
    return (
        ticker if "." in ticker else f"{ticker}{_TICKER_SUFFIX.get(ticker[0], '.SZ')}"
    )


_to_thscode = to_thscode  # 模块内旧名兼容


def _parse_date(value: str) -> date:
    return date.fromisoformat(value.replace("-", ""))


# 单位归一：fuyao 原始单位（股/元）→ 管道存储约定（Tushare 口径：手/千元），
# 跨源对账与同库混写均以此为准（2026-09-18 首跑对账实测 ×100/×1000 差异）。
_VOLUME_TO_LOTS = 100.0
_AMOUNT_TO_THOUSANDS = 1000.0

# REST 大窗口尾部静默截断防护（#433，#423 前轮实测）：A 股 10 年窗仅返回
# 最旧 ~2186 根、指数 ≥5 年窗返回空 item 且 code=0（未见于官方文档）。
# 保守分窗至 3 年（约 730 个交易日），远低于两个观测失败阈值；不把
# 2186/970 固化为行数上限，窗口内仍校验日期边界与重复键。
_REST_WINDOW_DAYS = 1095

# daily-k 常量列口径（#439：先验证再删列，不凭函数注释保证口径）
_DAILY_K_CONSTANTS = {"currency": "CNY", "interval": "1d", "adjusted": "none"}


def _validate_constant_column(
    raw: pl.DataFrame, column: str, expected: str, *, kind: str
) -> None:
    """校验 dump 常量列口径，缺列或非常量期望值时拒绝转换（fail-closed）."""
    if column not in raw.columns:
        raise SourceFetchError(
            source="fuyao",
            message=f"{kind} dump 缺常量列 {column}: 契约违约 拒绝转换",
        )
    unique = raw[column].unique().to_list()
    if unique != [expected]:
        raise SourceFetchError(
            source="fuyao",
            message=(
                f"{kind} dump {column} 期望常量 {expected}, 实际 {unique}: "
                "契约违约 拒绝转换"
            ),
        )


def _validate_daily_k_constants(raw: pl.DataFrame) -> None:
    """校验 daily-k dump 常量列口径（currency/interval/adjusted）."""
    for column, expected in _DAILY_K_CONSTANTS.items():
        _validate_constant_column(raw, column, expected, kind="daily-k")


def _bars_frame(rows: list[Any], source_ticker: str) -> pl.DataFrame:
    """原始 bar 行 → STOCK_DAILY SourceSchema 帧（knowledge_date = T+1）."""
    frame = pl.DataFrame(rows, schema=_BARS_RAW_SCHEMA, orient="row")
    return (
        frame.sort("trade_date_ms")
        .with_columns(
            source_ticker=pl.lit(source_ticker),
            trade_date=pl.col("trade_date_ms").map_elements(
                ms_to_date, return_dtype=pl.Date
            ),
            pre_close=pl.col("close").shift(1),
            volume=pl.col("volume") / _VOLUME_TO_LOTS,
            amount=pl.col("amount") / _AMOUNT_TO_THOUSANDS,
        )
        .with_columns(
            knowledge_date=pl.col("trade_date") + pl.duration(days=1),
            pct_change=(pl.col("close") / pl.col("pre_close") - 1) * 100,
        )
        .drop("trade_date_ms")
        .select(_BAR_COLUMNS)
    )


class FuyaoSource:
    """fuyao 数据源门面."""

    def __init__(self, *, client: FuyaoClient) -> None:
        self._client = client

    def close(self) -> None:
        """释放底层 HTTP 连接."""
        self._client.close()

    # ── 摄取路径（source=auto / 按标的）─────────────────────────

    def fetch_stock_daily(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """原始日 K（adjust=none）— MarketFetcher 协议两模式."""
        if trade_date and source_ticker:
            raise ValueError("trade_date 和 source_ticker 互斥, 不能同时指定")
        if not trade_date and not source_ticker:
            raise ValueError("必须指定 trade_date 或 source_ticker 之一")
        if trade_date:
            return self._fetch_market_daily(trade_date)
        if not source_ticker or not start_date or not end_date:
            raise ValueError("按标的查询必须指定 start_date 和 end_date")
        return self._fetch_ticker_daily(source_ticker, start_date, end_date)

    def _fetch_market_daily(self, trade_date: str) -> pl.DataFrame:
        target = _parse_date(trade_date)
        with tempfile.TemporaryDirectory(prefix="fuyao-dump-") as tmp:
            dump_path = Path(tmp) / "daily-k-10d.parquet"
            self.download_market_dump("daily-k-10d", dump_path)
            frame = self.daily_k_frame(dump_path)
        daily = frame.filter(pl.col("trade_date") == target)
        logger.info(
            "Fuyao daily-k-10d filtered",
            event="fuyao_stock_daily_fetch_complete",
            trade_date=str(target),
            row_count=len(daily),
        )
        return daily

    def _fetch_ticker_daily(
        self,
        source_ticker: str,
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        """
        单标的 REST 历史 — 按安全窗口分片并校验覆盖（#433）.

        每窗校验响应日期不越窗、跨窗无重复键；合并去重排序后统一推导
        pre_close/pct_change，分窗边界不丢失窗口首条的前收。空窗是合法
        状态（周末/停牌/上市前/退市后），仅记录可疑模式（中间窗空而邻窗
        有数据）供排障；无法证明完整时以日志暴露，不伪造成功。
        """
        thscode = _to_thscode(source_ticker)
        window_start = _parse_date(start_date)
        target_end = _parse_date(end_date)
        rows: list[tuple[Any, ...]] = []
        seen_dates: set[date] = set()
        window_counts: list[int] = []

        while window_start <= target_end:
            window_end = min(
                window_start + timedelta(days=_REST_WINDOW_DAYS - 1), target_end
            )
            data = self._client.get(
                "/api/a-share/prices/historical",
                params={
                    "thscode": thscode,
                    "interval": "1d",
                    "start": date_to_ms(window_start),
                    "end": date_to_ms(window_end),
                    "adjust": "none",
                },
            )
            items: list[dict[str, Any]] = data.get("item") or []
            window_counts.append(len(items))
            for item in items:
                item_date = ms_to_date(item["date_ms"])
                if not window_start <= item_date <= window_end:
                    raise SourceFetchError(
                        source="fuyao",
                        message=(
                            f"fuyao historical {thscode} window "
                            f"[{window_start},{window_end}] returned out-of-window "
                            f"bar {item_date}: 响应契约违约 拒绝静默截断"
                        ),
                    )
                if item_date in seen_dates:
                    raise SourceFetchError(
                        source="fuyao",
                        message=(
                            f"fuyao historical {thscode} returned duplicate "
                            f"trade_date {item_date} across windows: 不前进或重复页"
                        ),
                    )
                seen_dates.add(item_date)
                rows.append(
                    (
                        item["date_ms"],
                        item["open_price"],
                        item["high_price"],
                        item["low_price"],
                        item["close_price"],
                        item["volume"],
                        item["turnover"],
                    )
                )
            window_start = window_end + timedelta(days=1)

        if len(window_counts) > 1 and 0 in window_counts and any(window_counts):
            logger.warning(
                "Fuyao historical windows contain empty windows with data elsewhere",
                event="fuyao_rest_window_gap",
                thscode=thscode,
                window_row_counts=window_counts,
                hint="可能为长期停牌/上市前/退市后 也可能为源端静默截断 需核对",
            )
        else:
            logger.info(
                "Fuyao historical fetch complete",
                event="fuyao_ticker_daily_fetch_complete",
                thscode=thscode,
                windows=len(window_counts),
                rows=len(rows),
            )
        return _bars_frame(rows, thscode)

    @staticmethod
    def daily_k_frame(dump_path: Path) -> pl.DataFrame:
        """日 K dump Parquet → STOCK_DAILY 帧（pre_close 在 dump 窗口内推导）."""
        raw = pl.read_parquet(dump_path)
        _validate_daily_k_constants(raw)
        return (
            raw.rename(
                {
                    "thscode": "source_ticker",
                    "date_ms": "trade_date_ms",
                    "open_price": "open",
                    "high_price": "high",
                    "low_price": "low",
                    "close_price": "close",
                    "turnover": "amount",
                }
            )
            .sort(["source_ticker", "trade_date_ms"])
            .with_columns(
                trade_date=pl.col("trade_date_ms").map_elements(
                    ms_to_date, return_dtype=pl.Date
                ),
                pre_close=pl.col("close").shift(1).over("source_ticker"),
                volume=pl.col("volume") / _VOLUME_TO_LOTS,
                amount=pl.col("amount") / _AMOUNT_TO_THOUSANDS,
            )
            .with_columns(
                knowledge_date=pl.col("trade_date") + pl.duration(days=1),
                pct_change=(pl.col("close") / pl.col("pre_close") - 1) * 100,
            )
            .drop("trade_date_ms")
            .select(_BAR_COLUMNS)
        )

    # ── 对账协议（辅源）──────────────────────────────────────────

    @staticmethod
    def adjustment_factors_frame(dump_path: Path) -> pl.DataFrame:
        """
        复权因子事件流 dump Parquet → 事件帧（#438 adj_factor 对账辅源）.

        fuyao dump 是分红/送转/配股事件流（thscode + ex_date_ms 主键），
        不是每日累积因子；缺列或 currency 契约违约时拒绝转换。
        """
        raw = pl.read_parquet(dump_path)
        required = {
            "thscode",
            "ex_date_ms",
            "currency",
            *_ADJUSTMENT_EVENT_COLUMNS[2:],
        }
        missing = sorted(required - set(raw.columns))
        if missing:
            raise SourceFetchError(
                source="fuyao",
                message=(f"adjustment-factors dump 缺列 {missing}: 契约违约 拒绝转换"),
            )
        _validate_constant_column(raw, "currency", "CNY", kind="adjustment-factors")
        return raw.with_columns(
            ticker=pl.col("thscode").str.split(".").list.get(0),
            trade_date=pl.col("ex_date_ms").map_elements(
                ms_to_date, return_dtype=pl.Date
            ),
        ).select(_ADJUSTMENT_EVENT_COLUMNS)

    def fetch_stock_daily_bars(
        self,
        tickers: list[str],
        trade_date: str,
    ) -> pl.DataFrame:
        """对账协议帧：[ticker, trade_date, open, high, low, close, volume, amount]."""
        target = _parse_date(trade_date)
        frames: list[pl.DataFrame] = []
        for ticker in tickers:
            frame = self._fetch_ticker_daily(ticker, str(target), str(target))
            frame = frame.filter(pl.col("trade_date") == target)
            if not frame.is_empty():
                frames.append(
                    frame.with_columns(
                        ticker=pl.col("source_ticker").str.split(".").list.get(0)
                    ).select(
                        "ticker",
                        "trade_date",
                        "open",
                        "high",
                        "low",
                        "close",
                        "volume",
                        "amount",
                    )
                )
        if not frames:
            return pl.DataFrame(
                schema={
                    "ticker": pl.String,
                    "trade_date": pl.Date,
                    "open": pl.Float64,
                    "high": pl.Float64,
                    "low": pl.Float64,
                    "close": pl.Float64,
                    "volume": pl.Float64,
                    "amount": pl.Float64,
                }
            )
        return pl.concat(frames)

    def fetch_financial_statements(
        self,
        dataset: str,
        thscodes: list[str],
        *,
        period: str = "quarterly",
        limit: int = 20,
    ) -> pl.DataFrame:
        """
        财务三表对账协议帧（#473）.

        fuyao 财务接口单标的、period=quarterly 覆盖全部季度末报告期（含年报
        Q4），金额原币元。thscodes 接受裸码（按股票前缀规则补后缀，与身份
        反解同规则）或完整 thscode。返回 [ticker(thscode), report_date,
        disclosure_date, fiscal_year, fiscal_period, <内部列名数值字段>]；
        disclosure_date 为辅源披露日（vintage 判定，非比较字段）。契约违约
        （非 CNY/缺列）按标的跳过并记录，不中断其他标的。
        """
        path = _FINANCIAL_STATEMENT_PATHS[dataset]
        renames = _FINANCIAL_FIELD_RENAMES[dataset]
        rows: list[dict[str, Any]] = []
        for raw_code in thscodes:
            code = to_thscode(raw_code)
            try:
                data = self._client.get(
                    path,
                    params={
                        "thscode": code,
                        "period": period,
                        "limit": limit,
                    },
                )
                items: list[dict[str, Any]] = data.get("item") or []
                self._validate_financial_items(dataset, code, items, renames)
            except SourceFetchError as error:
                logger.warning(
                    "Fuyao financial statement skipped for reconciliation",
                    event="fuyao_financial_skip",
                    dataset=dataset,
                    thscode=code,
                    reason=str(error)[:200],
                )
                continue
            for item in items:
                rows.append(
                    {
                        "ticker": code,
                        "report_date": ms_to_date(item["period_end_ms"]),
                        "disclosure_date": ms_to_date(item["report_date_ms"]),
                        "fiscal_year": item["fiscal_year"],
                        "fiscal_period": item["fiscal_period"],
                        **{
                            internal: item[fuyao_name]
                            for fuyao_name, internal in renames.items()
                        },
                    }
                )
        schema: dict[str, type[pl.DataType]] = {
            "ticker": pl.String,
            "report_date": pl.Date,
            "disclosure_date": pl.Date,
            "fiscal_year": pl.Int64,
            "fiscal_period": pl.String,
            **dict.fromkeys(renames.values(), pl.Float64),
        }
        return pl.DataFrame(rows, schema=schema)

    @staticmethod
    def _validate_financial_items(
        dataset: str,
        thscode: str,
        items: list[dict[str, Any]],
        renames: dict[str, str],
    ) -> None:
        """校验辅源财务行契约（CNY 常量 + 关键列存在），违约拒绝该标的."""
        required = {"period_end_ms", "report_date_ms", "currency", *renames}
        for item in items:
            missing = sorted(required - set(item))
            if missing:
                raise SourceFetchError(
                    source="fuyao",
                    message=(
                        f"fuyao {dataset} {thscode} 缺列 {missing}: 契约违约 拒绝"
                    ),
                )
            if item["currency"] != "CNY":
                raise SourceFetchError(
                    source="fuyao",
                    message=(
                        f"fuyao {dataset} {thscode} currency={item['currency']}: "
                        "非 CNY 拒绝"
                    ),
                )

    # ── 快照（展示层，不进管道）──────────────────────────────────

    def fetch_a_share_snapshot(self, thscodes: list[str]) -> pl.DataFrame:
        """A 股 L1 快照（批量，展示层）."""
        data = self._client.get(
            "/api/a-share/prices/snapshot", params={"thscodes": ",".join(thscodes)}
        )
        return pl.DataFrame(data.get("item") or [])

    def fetch_fund_snapshot(self, thscode: str) -> pl.DataFrame:
        """ETF L1 快照（单只，展示层）."""
        data = self._client.get(
            "/api/fund/market/snapshot", params={"thscode": thscode}
        )
        return pl.DataFrame(data.get("item") or [])

    # ── 全市场 dump（不可变快照落盘）─────────────────────────────

    def download_market_dump(self, kind: DumpKind, dest: Path) -> Path:
        """获取预签名链接并流式下载 dump Parquet 到 dest."""
        data = self._client.get(_DUMP_PATHS[kind])
        presigned = data.get("presigned_url")
        if not presigned:
            raise ValueError(f"fuyao dump {kind} returned no presigned_url")
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("wb") as fh:
            self._client.download(presigned, fh)
        logger.info(
            "Fuyao market dump downloaded",
            event="fuyao_dump_download_complete",
            kind=kind,
            path=str(dest),
            size_bytes=dest.stat().st_size,
        )
        return dest


class FuyaoDailyKDumpFetcher:
    """
    daily-k 本地 dump 回填 fetcher（#439 手动回填专用）.

    仅实现 stock_daily 日期级取数（MarketFetcher 协议子集，与 FuyaoSource
    注册同口径：数据集级白名单负责精确门禁）。主键重复或常量列违约拒绝
    回填；身份登记、DQ、VERIFY_IDENTICAL 重叠保护与 ProviderSnapshot 证据
    均由正常摄取链路（source=fuyao 协调器）承担。不自动降级：只有被显式
    注入组合根（market_fetcher_override）时才生效。
    """

    def __init__(self, dump_path: Path) -> None:
        raw = pl.read_parquet(dump_path)
        missing = [c for c in ("thscode", "date_ms") if c not in raw.columns]
        if missing:
            raise SourceFetchError(
                source="fuyao",
                message=f"daily-k dump 缺主键列 {missing}: 契约违约 拒绝回填",
            )
        duplicates = raw.height - raw.unique(subset=["thscode", "date_ms"]).height
        if duplicates:
            raise SourceFetchError(
                source="fuyao",
                message=(
                    f"daily-k dump 主键(thscode,date_ms)重复 {duplicates} 行: "
                    "拒绝回填(重新下载 dump)"
                ),
            )
        self._frame = FuyaoSource.daily_k_frame(dump_path)
        self._empty = self._frame.clear()
        # 按日分区一次，逐日取数 O(1)（10 年全量约 2400 个交易日）
        self._by_date: dict[date, pl.DataFrame] = {
            part["trade_date"][0]: part
            for part in self._frame.partition_by("trade_date", maintain_order=True)
        }

    @property
    def coverage(self) -> tuple[date, date] | None:
        """Dump 实际日期覆盖（请求区间与之取交，不要求末根等于请求 end）."""
        if not self._by_date:
            return None
        dates = sorted(self._by_date)
        return (dates[0], dates[-1])

    @property
    def frame(self) -> pl.DataFrame:
        """已验证的完整 STOCK_DAILY 帧（dry-run 冲突分析用）."""
        return self._frame

    def fetch_stock_daily(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """Dump 单日切片（正常摄取链路的 fetch 钩子）."""
        if not trade_date or source_ticker or start_date or end_date:
            raise SourceFetchError(
                source="fuyao",
                message="daily-k dump 回填仅支持 trade_date 单日取数",
            )
        return self._by_date.get(_parse_date(trade_date), self._empty)
