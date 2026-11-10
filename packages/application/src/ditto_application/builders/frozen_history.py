"""Ordinary reconstruction from retained provider facts, never receipt backdating."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta

import polars as pl
from ditto_backtest.provenance import aggregate_source_snapshot_id
from ditto_data.catalog.snapshot_reader import SnapshotReadService
from ditto_data.catalog.source_snapshot import ProviderSnapshot
from ditto_data.provider import BarQuery, InstrumentQuery
from ditto_data.services.cash_dividends import (
    cash_adjusted_suspension_marks,
    implemented_cash_dividends,
)
from ditto_data.services.market_adjustment import adjust_retained_bars
from ditto_data.services.market_status import stock_execution_bars
from ditto_data.services.market_types import AdjType
from ditto_data.sources.etf_share_conversions import (
    ETF_SHARE_CONVERSION_FRAME_COLUMNS,
)
from ditto_kernel.identity import InstrumentId
from ditto_portfolio.accounting.conversions import (
    ShareConversion,
    validate_share_conversions,
)
from ditto_portfolio.accounting.dividends import Distribution

from ditto_application.builders.data_provider import resolve_frozen_snapshot_rows
from ditto_application.catalog_freshness import observed_at
from ditto_application.exceptions import AppBuilderError

# 财务披露数据集：披露锚（公告日）与快照拉取窗是两个时间轴，冻结按披露键
# 直接归并全部可见 payload（#765 F1），不随其余数据集走拉取窗格子 lineage。
_FINANCIAL_DATASETS = frozenset({"income_statement", "balance_sheet"})


class FrozenHistoryProvider:
    """
    One request's verified bytes and source anchors, held fixed for the engine.

    Raw ``knowledge_date`` is the provider-normalized fact/publication anchor.
    It is NOT a local receipt. Receipts remain in ``sources.received_at``; this
    path cannot certify that the local system held the data in the past.
    """

    def __init__(
        self,
        reader: SnapshotReadService,
        *,
        frozen_at: datetime,
        source: str = "tushare",
    ) -> None:
        if frozen_at.tzinfo is None:
            raise AppBuilderError("history freeze requires an aware receipt cutoff")
        self._reader = reader
        self.members: tuple[str, ...] = ()
        self.instrument_ids: tuple[int, ...] = ()
        self.frozen_at, self._source = frozen_at, source
        self.sources: list[dict[str, object]] = []
        self.roster: list[dict[str, object]] = []
        self.membership_intervals: list[dict[str, object]] = []
        self.participation: list[dict[str, object]] = []
        self._frames: dict[str, pl.DataFrame] = {}
        self._ticker_ids: dict[str, InstrumentId] = {}
        self._asset_class = ""
        self._etf_reference: pl.DataFrame | None = None
        self.cash_dividends: tuple[Distribution, ...] = ()
        self.share_conversions: tuple[ShareConversion, ...] = ()

    def freeze_cash_dividends(self, *, start: str, end: str) -> None:
        """Pin implementation facts selected by the raw announcement date."""
        dataset = "etf_dividend" if self._asset_class == "etf" else "dividend"
        if not self._reader.list_snapshots(dataset_id=dataset, source=self._source):
            raise AppBuilderError(f"missing retained {dataset} coverage")
        listed = {
            str(row["source_ticker"]): str(row["list_date"]) for row in self.roster
        }
        if any(not listed.get(ticker) for ticker in self.members):
            raise AppBuilderError("dividend coverage requires retained listing dates")
        # Announcements may precede the run by arbitrarily many sessions. Require
        # their complete declared history rather than inventing a lookback window.
        coverage_start = min(listed[ticker] for ticker in self.members)
        frame = self._freeze_dataset(
            dataset,
            {ticker: self._ticker_ids[ticker] for ticker in self.members},
            start=None,
            end=end,
            date_column="knowledge_date",
            coverage_start=coverage_start,
        )
        try:
            selected = implemented_cash_dividends(frame, start=start, end=end)
            etf = self._asset_class == "etf"
            self.cash_dividends = tuple(
                Distribution(
                    instrument_id=InstrumentId(row["instrument_id"]),
                    record_date=row["record_date"],
                    ex_date=row["ex_dividend_date"],
                    pay_date=row["pay_date"],
                    gross_per_share=row["gross_dividend_per_share"],
                    # ETF facts know implementation from max(ann, imp) upstream;
                    # stock events keep their established #759/#760 announcement
                    # semantics untouched.
                    announcement_date=max(
                        row["knowledge_date"], row["implementation_date"]
                    )
                    if etf
                    else (
                        max(
                            row["implementation_date"],
                            row["share_tax_knowledge_date"],
                        )
                        if row["stock_dividend_ratio"]
                        else row["implementation_date"]
                    ),
                    asset_class="etf" if etf else "stock",
                    source_snapshot_id=row["source_snapshot_id"],
                    source_ticker=row["source_ticker"],
                    share_ratio=row["stock_dividend_ratio"],
                    listing_date=row["share_listing_date"]
                    if row["stock_dividend_ratio"]
                    else None,
                    taxable_share_income=row["taxable_share_income"]
                    if row["stock_dividend_ratio"]
                    else 0,
                    share_tax_basis=row["share_tax_basis"]
                    if row["stock_dividend_ratio"]
                    else "",
                )
                for row in selected.to_dicts()
            )
        except ValueError as exc:
            raise AppBuilderError(str(exc)) from exc

    def _latest_config_snapshots(
        self, dataset_id: str
    ) -> dict[str, tuple[ProviderSnapshot, list[str]]]:
        """Per member, the latest config snapshot receipt at or before frozen_at."""
        candidates = [
            replace(
                s, observations=tuple(t for t in s.observations if t <= self.frozen_at)
            )
            for s in self._reader.list_snapshots(dataset_id=dataset_id, source="config")
            if s.created_at <= self.frozen_at
        ]
        selected: dict[str, list[str]] = {}
        snapshots = {s.snapshot_id: s for s in candidates}
        for ticker in self.members:
            latest = max(
                (
                    s
                    for s in candidates
                    if not s.source_ticker_scope or ticker in s.source_ticker_scope
                ),
                key=lambda s: (observed_at(s), s.snapshot_id),
                default=None,
            )
            if latest is not None:
                selected.setdefault(latest.snapshot_id, []).append(ticker)
        return {
            identity: (snapshots[identity], tickers)
            for identity, tickers in selected.items()
        }

    def freeze_share_conversions(self, *, start: str, end: str) -> None:
        """
        Pin maintainer-declared conversions effective inside the run window.

        The declaration file is not a completeness claim: runs without any
        retained declaration snapshot simply see no conversions, and any real
        factor jump stays fail-closed in execution validation.
        """
        selected = self._latest_config_snapshots("etf_share_conversions")
        if not selected:
            self.share_conversions = ()
            return
        conversions: list[ShareConversion] = []
        for identity, (snapshot, tickers) in selected.items():
            frame = self._read_verified_snapshot(snapshot)
            required = set(ETF_SHARE_CONVERSION_FRAME_COLUMNS)
            if not required.issubset(frame.columns):
                raise AppBuilderError(
                    "etf_share_conversions retained payload lacks "
                    + str(sorted(required - set(frame.columns)))
                )
            frame = (
                frame.filter(pl.col("source_ticker").is_in(tickers))
                .with_columns(
                    pl.col("effective_date").cast(pl.String),
                    pl.col("announcement_date").cast(pl.String),
                    pl.col("ratio").cast(pl.Float64),
                )
                .filter(
                    pl.col("effective_date").is_between(pl.lit(start), pl.lit(end))
                    & pl.col("source_ticker").is_in(self._ticker_ids)
                )
            )
            for row in frame.to_dicts():
                try:
                    conversions.append(
                        ShareConversion(
                            instrument_id=self._ticker_ids[row["source_ticker"]],
                            effective_date=date.fromisoformat(
                                str(row["effective_date"])
                            ),
                            ratio=float(row["ratio"]),
                            announcement_date=date.fromisoformat(
                                str(row["announcement_date"])
                            ),
                            source_snapshot_id=identity,
                            source_ticker=str(row["source_ticker"]),
                            rounding_note=str(row["rounding_note"]),
                        )
                    )
                except ValueError as exc:
                    raise AppBuilderError(str(exc)) from exc
        try:
            self.share_conversions = tuple(
                sorted(conversions, key=lambda c: c.identity)
            )
            validate_share_conversions(self.share_conversions)
        except ValueError as exc:
            raise AppBuilderError(str(exc)) from exc

    def freeze_etf_reference(self) -> pl.DataFrame:
        """Freeze dated declarations by receipt, not by the historical bar window."""
        if self._etf_reference is not None:
            return self._etf_reference
        selected = self._latest_config_snapshots("etf_reference")
        covered = {ticker for _, tickers in selected.values() for ticker in tickers}
        missing = set(self.members) - covered
        if missing:
            raise AppBuilderError(f"missing retained etf_reference: {sorted(missing)}")
        frames: list[pl.DataFrame] = []
        for identity, (snapshot, tickers) in selected.items():
            frame = self._read_verified_snapshot(snapshot)
            required = {
                "source_ticker",
                "field",
                "value",
                "unit",
                "effective_from",
                "effective_to",
                "basis",
            }
            if not required.issubset(frame.columns):
                raise AppBuilderError(
                    "etf_reference retained payload lacks "
                    + str(sorted(required - set(frame.columns)))
                )
            frame = frame.filter(pl.col("source_ticker").is_in(tickers))
            missing = set(tickers) - set(frame["source_ticker"])
            if missing:
                raise AppBuilderError(
                    f"latest etf_reference lacks declarations: {sorted(missing)}"
                )
            frames.append(
                frame.with_columns(
                    pl.col("source_ticker")
                    .replace_strict(
                        {ticker: int(self._ticker_ids[ticker]) for ticker in tickers},
                        return_dtype=pl.Int64,
                    )
                    .alias("instrument_id"),
                    pl.lit(identity).alias("source_snapshot_id"),
                )
            )
        self._etf_reference = pl.concat(frames, how="diagonal_relaxed")
        return self._etf_reference

    def freeze(
        self,
        *,
        ticker_ids: dict[str, InstrumentId],
        asset_class: str,
        start: str,
        end: str,
        benchmark: dict[str, InstrumentId] | None = None,
        calendar_end: str | None = None,
        include_fundamentals: bool = False,
    ) -> None:
        """Resolve catalog windows once, then verify and retain their exact bytes."""
        if set(self._frames) - {"calendar"}:
            raise AppBuilderError("historical inputs are already frozen")
        if self._source != "tushare" or asset_class not in {"stock", "etf"}:
            raise AppBuilderError("unverified historical source/asset time semantics")
        self._asset_class = asset_class
        self.members = tuple(ticker_ids)
        self.instrument_ids = tuple(int(iid) for iid in ticker_ids.values())
        self._ticker_ids = {**ticker_ids, **(benchmark or {})}
        datasets = {
            f"{asset_class}_daily": ticker_ids,
            "fund_adj" if asset_class == "etf" else "adj_factor": ticker_ids,
            "calendar": {"": InstrumentId(0)},
        }
        if asset_class == "stock":
            datasets.update(stock_status=ticker_ids, stock_limit=ticker_ids)
        if benchmark:
            datasets["index_daily"] = benchmark
        if include_fundamentals:
            datasets.update(income_statement=ticker_ids, balance_sheet=ticker_ids)
        for dataset, scope in datasets.items():
            if dataset == "calendar" and dataset in self._frames:
                continue
            financial = dataset in {"income_statement", "balance_sheet"}
            self._frames[dataset] = self._freeze_dataset(
                dataset,
                scope,
                start=None if financial else start,
                end=(calendar_end or end) if dataset == "calendar" else end,
                date_column="knowledge_date" if financial else "trade_date",
            )
            # #765：股票多因子普通运行实际消费财务输入；运行范围内一份披露
            # 都冻不到属于缺证，必须显式阻断并走补证恢复（#751 机制），
            # 不得静默空帧变成全现金运行（缩池关闭目标）。
            if financial and self._frames[dataset].is_empty():
                raise AppBuilderError(
                    f"missing retained {dataset}: no disclosures frozen for "
                    + f"{sorted(scope)} ..{end}"
                )
        if asset_class == "stock":
            self._freeze_suspension_anchors(start)

    def _freeze_suspension_anchors(self, start: str) -> None:
        """Retain a past quote for halts already in progress at the warmup start."""
        bars = self._frames["stock_daily"]
        missing = (
            self._frames["stock_status"]
            .filter(pl.col("is_suspended"))
            .join(
                bars.group_by("instrument_id").agg(
                    pl.col("trade_date").min().alias("_first_quote")
                ),
                on="instrument_id",
                how="left",
            )
            .filter(
                pl.col("_first_quote").is_null()
                | (pl.col("trade_date") < pl.col("_first_quote"))
            )
        )
        scope = {
            ticker: self._ticker_ids[ticker]
            for ticker in missing["source_ticker"].unique().to_list()
        }
        if not scope:
            return
        candidates = [
            s
            for s in self._reader.list_snapshots(
                dataset_id="stock_daily", source=self._source
            )
            if s.created_at <= self.frozen_at and s.request_start < start
        ]
        if not candidates:
            return
        earliest = min(s.request_start for s in candidates)
        end = (date.fromisoformat(start) - timedelta(days=1)).isoformat()
        span = 31
        while scope:
            first = max(
                earliest, (date.fromisoformat(start) - timedelta(days=span)).isoformat()
            )
            if any(
                s.request_end >= first
                and (
                    not s.source_ticker_scope
                    or s.source_ticker_scope.intersection(scope)
                )
                for s in candidates
            ):
                quotes = self._freeze_dataset(
                    "stock_daily", scope, start=first, end=end, date_column="trade_date"
                )
                anchors = quotes.sort("trade_date").group_by("source_ticker").tail(1)
                self._frames["stock_daily"] = pl.concat(
                    [self._frames["stock_daily"], anchors], how="diagonal_relaxed"
                )
                found = set(anchors["source_ticker"])
                scope = {
                    ticker: iid for ticker, iid in scope.items() if ticker not in found
                }
            if first == earliest:
                break
            span *= 2

    def prepare_calendar(self, *, start: str, end: str, warmup: int, lag: int) -> str:
        """Expand verified calendar coverage until the required sessions exist."""
        candidates = [
            s
            for s in self._reader.list_snapshots(
                dataset_id="calendar", source=self._source
            )
            if s.created_at <= self.frozen_at and s.request_start <= start
        ]
        if not candidates:
            raise AppBuilderError("missing retained calendar")
        earliest = min(s.request_start for s in candidates)
        cutoff = (date.fromisoformat(start) - timedelta(days=lag)).isoformat()
        span = max(31, warmup * 2 + lag)
        while True:
            first = max(
                earliest, (date.fromisoformat(start) - timedelta(days=span)).isoformat()
            )
            self._frames["calendar"] = self._freeze_dataset(
                "calendar",
                {"": InstrumentId(0)},
                start=first,
                end=end,
                date_column="trade_date",
            )
            days = self.get_schedule(first, end)["trade_date"].to_list()
            prior = [day for day in days if day < cutoff]
            if len(prior) >= warmup:
                return prior[-warmup] if warmup else start
            if first == earliest:
                raise AppBuilderError(
                    f"insufficient retained trading calendar: {len(prior)} < {warmup}"
                )
            span *= 2

    def _freeze_dataset(
        self,
        dataset: str,
        scope: dict[str, InstrumentId],
        *,
        start: str | None,
        end: str,
        date_column: str,
        coverage_start: str | None = None,
    ) -> pl.DataFrame:
        candidates = tuple(
            replace(
                s, observations=tuple(t for t in s.observations if t <= self.frozen_at)
            )
            for s in self._reader.list_snapshots(
                dataset_id=dataset, source=self._source
            )
            if s.created_at <= self.frozen_at
            and s.request_start <= end
            and (start is None or s.request_end >= start)
            and (not s.source_ticker_scope or s.source_ticker_scope.intersection(scope))
        )
        if not candidates:
            if date_column == "knowledge_date":
                return pl.DataFrame()
            raise AppBuilderError(
                f"missing retained {dataset}: {sorted(scope)} {start}..{end}"
            )
        if dataset in _FINANCIAL_DATASETS:
            return self._merge_financial_payloads(dataset, candidates, scope, end)
        first = date.fromisoformat(start or min(s.request_start for s in candidates))
        if coverage_start is not None:
            first = min(first, date.fromisoformat(coverage_start))
        dates = pl.date_range(first, date.fromisoformat(end), eager=True)
        # ponytail: daily scope grid; replace with interval joins if large pools
        # make this measured cost material. No date/member is silently omitted.
        grid = (
            pl.DataFrame({"trade_date": dates})
            .join(pl.DataFrame({"source_ticker": sorted(scope)}), how="cross")
            .with_columns(pl.lit(self._source).alias("source"))
        )
        selected = resolve_frozen_snapshot_rows(grid, candidates)
        if (
            coverage_start is not None
            and selected.filter(
                (pl.col("trade_date") >= date.fromisoformat(coverage_start))
                & pl.col("source_snapshot_id").is_null()
            ).height
        ):
            raise AppBuilderError(
                f"incomplete retained {dataset} coverage: {coverage_start}..{end}"
            )
        frames: list[pl.DataFrame] = []
        for snapshot in candidates:
            covered = selected.filter(
                pl.col("source_snapshot_id") == snapshot.snapshot_id
            )
            if covered.is_empty():
                continue
            frames.append(
                self._read_selected_snapshot(snapshot, covered, scope, date_column)
            )
        if not frames:
            raise AppBuilderError(f"no consumable retained {dataset}: {start}..{end}")
        return pl.concat(frames, how="diagonal_relaxed")

    def _merge_financial_payloads(
        self,
        dataset: str,
        candidates: tuple[ProviderSnapshot, ...],
        scope: dict[str, InstrumentId],
        end: str,
    ) -> pl.DataFrame:
        """
        Merge every visible financial payload by its disclosure key (#765 F1).

        Financial snapshots mix window shapes: quarter backfills carry wide
        announcement-date windows while daily pulls carry single pull-day
        windows whose payloads still hold disclosures announced on other days
        (weekend earnings included). Row lineage therefore cannot resolve
        through "a window contains the announcement day" — cells outside every
        window would silently drop those disclosures. Instead each visible
        payload contributes its in-scope rows directly; the same disclosure
        key re-observed by a later snapshot wins (aligning with the live
        lane's #628 convergence, where the freshest visible version decides).
        Rows announced after the run end never enter (future sentinel).
        """
        disclosed = date.fromisoformat(end)
        frames: list[pl.DataFrame] = []
        for snapshot in sorted(
            candidates, key=lambda item: (observed_at(item), item.snapshot_id)
        ):
            frame = self._read_verified_snapshot(snapshot)
            missing = {"source_ticker", "knowledge_date", "report_date"} - set(
                frame.columns
            )
            if missing:
                raise AppBuilderError(
                    f"{dataset} retained payload lacks {sorted(missing)}"
                )
            frame = (
                frame.with_columns(
                    pl.col("knowledge_date").cast(pl.Date),
                    pl.col("report_date").cast(pl.Date),
                    pl.lit(snapshot.source).alias("source"),
                    pl.lit(snapshot.snapshot_id).alias("source_snapshot_id"),
                )
                .filter(
                    pl.col("source_ticker").is_in(sorted(scope))
                    & (pl.col("knowledge_date") <= pl.lit(disclosed))
                )
                .with_columns(
                    pl.col("source_ticker")
                    .replace_strict(
                        {ticker: int(iid) for ticker, iid in scope.items()},
                        return_dtype=pl.Int64,
                    )
                    .alias("instrument_id"),
                )
            )
            frames.append(frame)
        if not frames:
            raise AppBuilderError(
                f"missing retained {dataset}: {sorted(scope)} ..{end}"
            )
        merged = pl.concat(frames, how="diagonal_relaxed").unique(
            subset=["source_ticker", "report_date", "knowledge_date"],
            keep="last",
            maintain_order=True,
        )
        return merged.sort(["source_ticker", "report_date", "knowledge_date"])

    def _read_selected_snapshot(
        self,
        snapshot: ProviderSnapshot,
        covered: pl.DataFrame,
        scope: dict[str, InstrumentId],
        date_column: str,
    ) -> pl.DataFrame:
        frame = self._read_verified_snapshot(snapshot)
        dataset = snapshot.dataset_id
        if date_column not in frame.columns:
            raise AppBuilderError(f"{dataset} retained payload lacks {date_column}")
        if dataset == "calendar":
            frame = frame.with_columns(pl.lit("").alias("source_ticker"))
        if "source_ticker" not in frame.columns:
            raise AppBuilderError(f"{dataset} retained payload lacks provider identity")
        frame = (
            frame.with_columns(
                pl.col(date_column).cast(pl.Date).alias("_selection_date"),
            )
            .join(
                covered.select(
                    "source_ticker",
                    pl.col("trade_date").alias("_selection_date"),
                    "source_snapshot_id",
                ),
                on=["source_ticker", "_selection_date"],
                how="inner",
                validate="m:1",
            )
            .drop("_selection_date")
            .with_columns(pl.lit(snapshot.source).alias("source"))
        )
        if dataset != "calendar":
            frame = frame.with_columns(
                pl.col("source_ticker")
                .replace_strict(
                    {ticker: int(iid) for ticker, iid in scope.items()},
                    return_dtype=pl.Int64,
                )
                .alias("instrument_id"),
            )
            if "knowledge_date" in frame.columns:
                frame = frame.with_columns(pl.col("knowledge_date").cast(pl.Date))
            elif dataset not in {"stock_status", "stock_limit"}:
                raise AppBuilderError(
                    f"{dataset} retained payload lacks knowledge_date"
                )
            # Daily status/limits are realized execution facts only. Do not invent
            # a publication/receipt timestamp for provider rows that lack one.
        return frame

    def _read_verified_snapshot(self, snapshot: ProviderSnapshot) -> pl.DataFrame:
        """Share the completion/checksum gate and source record for retained inputs."""
        dataset = snapshot.dataset_id
        evidence: dict[str, object] = {
            "dataset": dataset,
            "source": snapshot.source,
            "snapshot_id": snapshot.snapshot_id,
            "checksum": snapshot.checksum,
            "request_start": snapshot.request_start,
            "request_end": snapshot.request_end,
            "received_at": snapshot.created_at.isoformat(),
            "observed_at": observed_at(snapshot).isoformat(),
            "rows": snapshot.row_count,
            "verified": False,
        }
        previous = next(
            (
                item
                for item in self.sources
                if item["snapshot_id"] == snapshot.snapshot_id
            ),
            None,
        )
        if previous is None:
            self.sources.append(evidence)
        else:
            evidence = previous
        try:
            frame = self._reader.read(
                snapshot.snapshot_id, completed_before=self.frozen_at
            ).frame
        except ValueError as exc:
            raise AppBuilderError(f"{dataset} {snapshot.snapshot_id}: {exc}") from exc
        evidence["verified"] = True
        return frame

    def get_bars(self, query: BarQuery) -> pl.DataFrame:
        """Use source availability anchors with the unchanged causal history gate."""
        if query.frequency != "daily" or query.adj not in {"none", "qfq", "hfq"}:
            raise AppBuilderError("unsupported frozen historical bar query")
        dataset = query.dataset_id or f"{self._asset_class}_daily"
        bars = self._range(dataset, query)
        if dataset == "index_daily":
            return bars
        if dataset == "stock_daily":
            self._reject_post_exit_quotes(bars)
        factors = self._range(
            "fund_adj" if self._asset_class == "etf" else "adj_factor", query
        )
        if query.adj != "none":
            cutoff = date.fromisoformat(query.asof) if query.asof else None
            if cutoff is None:
                raise AppBuilderError(
                    "historical adjusted prices require a decision cutoff"
                )
            bars = bars.filter(pl.col("knowledge_date") <= cutoff)
            adjusted = adjust_retained_bars(
                bars, factors, adj=AdjType(query.adj), asof=cutoff
            )
            return adjusted.with_columns(
                pl.struct(
                    "adjustment_source_snapshot_id",
                    "adjustment_baseline_source_snapshot_id",
                )
                .map_elements(
                    lambda row: aggregate_source_snapshot_id(row.values()),
                    return_dtype=pl.String,
                )
                .alias("adjustment_source_snapshot_id")
            )
        return (
            self._execution_bars(bars, factors, query)
            if query.with_execution_state
            else bars
        )

    def _execution_bars(
        self, bars: pl.DataFrame, factors: pl.DataFrame, query: BarQuery
    ) -> pl.DataFrame:
        """Require exact daily execution factors, status and price limits."""
        if self._asset_class == "stock":
            try:
                # The pre-start slice feeds suspension anchoring; a conflicting
                # post-exit quote must fail closed here too, not only inside
                # the queried window (get_bars runs the same guard).
                valuation_history = self._frames["stock_daily"].filter(
                    pl.col("source_ticker").is_in(query.instruments)
                    & (pl.col("trade_date") < date.fromisoformat(query.start))
                )
                self._reject_post_exit_quotes(valuation_history)
                bars = stock_execution_bars(
                    bars,
                    self._range("stock_status", query),
                    self._range("stock_limit", query),
                    valuation_history=valuation_history,
                )
                bars = cash_adjusted_suspension_marks(
                    bars,
                    tuple(
                        (
                            int(event.instrument_id),
                            event.ex_date,
                            event.gross_per_share,
                            event.share_ratio,
                        )
                        for event in self.cash_dividends
                    ),
                )
            except ValueError as error:
                raise AppBuilderError(str(error)) from error
        keys = ["instrument_id", "trade_date"]
        bars = bars.join(
            factors.select(
                *keys,
                "adj_factor",
                pl.col("source_snapshot_id").alias("adjustment_source_snapshot_id"),
            ),
            on=keys,
            how="left",
            validate="1:1",
        )
        if bars["adj_factor"].null_count():
            raise AppBuilderError("missing frozen execution adjustment factors")
        return bars

    def _reject_post_exit_quotes(self, bars: pl.DataFrame) -> None:
        """
        Fail closed when retained quotes contradict a frozen exit fact.

        The roster's delist_date is the request's frozen exit fact. A quote on
        or after that day is a conflict between two retained sources, not an
        executable price; it must not silently enter the execution or signal
        channels under the exit-day participation gate.
        """
        exits = pl.DataFrame(
            [
                {
                    "source_ticker": str(row["source_ticker"]),
                    "delist_date": str(row["delist_date"]),
                }
                for row in self.roster
                if row.get("delist_date")
                and str(row.get("asset_class", self._asset_class)) == "stock"
            ],
            schema={"source_ticker": pl.String, "delist_date": pl.String},
        )
        if exits.is_empty() or bars.is_empty():
            return
        offenders = bars.join(exits, on="source_ticker", how="inner").filter(
            pl.col("trade_date").cast(pl.String) >= pl.col("delist_date")
        )
        if not offenders.is_empty():
            sample = offenders.select("source_ticker", "trade_date").head(5).rows()
            raise AppBuilderError(
                "delisted instrument quoted after exit: "
                + ", ".join(f"{ticker} {day}" for ticker, day in sample)
            )

    def _range(self, dataset: str, query: BarQuery) -> pl.DataFrame:
        frame = self._frames.get(dataset)
        if frame is None:
            raise AppBuilderError(f"dataset not frozen: {dataset}")
        return frame.filter(
            pl.col("source_ticker").is_in(query.instruments)
            & pl.col("trade_date")
            .cast(pl.Date)
            .is_between(date.fromisoformat(query.start), date.fromisoformat(query.end))
        ).sort(
            [
                "instrument_id",
                "trade_date",
                *(["knowledge_date"] if "knowledge_date" in frame.columns else []),
            ]
        )

    def get_schedule(self, start: str, end: str) -> pl.DataFrame:
        """Require every calendar day to be represented before selecting sessions."""
        frame = self._frames["calendar"].filter(
            pl.col("trade_date").is_between(
                date.fromisoformat(start), date.fromisoformat(end)
            )
        )
        if (
            frame["trade_date"].n_unique()
            != (date.fromisoformat(end) - date.fromisoformat(start)).days + 1
        ):
            raise AppBuilderError(f"incomplete frozen calendar: {start}..{end}")
        return (
            frame.filter(pl.col("is_open"))
            .select(pl.col("trade_date").cast(pl.String))
            .sort("trade_date")
        )

    def _financial(
        self, dataset: str, instrument_id: int, asof: date
    ) -> pl.DataFrame | None:
        frame = self._frames.get(dataset)
        if frame is None or frame.is_empty():
            return None
        if "effective_from" in frame.columns:
            frame = frame.filter(pl.col("effective_from").cast(pl.Date) <= asof)
        if "effective_to" in frame.columns:
            frame = frame.filter(
                pl.col("effective_to").is_null()
                | (pl.col("effective_to").cast(pl.Date) > asof)
            )
        return (
            frame.filter(
                (pl.col("instrument_id") == instrument_id)
                & (pl.col("knowledge_date") <= asof)
                & (pl.col("report_date").cast(pl.Date) <= asof)
            )
            .sort(["report_date", "knowledge_date"], descending=True)
            .head(1)
        )

    def get_income_statement(
        self,
        instrument_id: int,
        as_of_date: date,
        *,
        allow_experimental_data: bool = False,
    ) -> pl.DataFrame | None:
        """Read the latest report published by the decision cutoff."""
        return self._financial("income_statement", instrument_id, as_of_date)

    def get_balance_sheet(
        self,
        instrument_id: int,
        as_of_date: date,
        *,
        allow_experimental_data: bool = False,
    ) -> pl.DataFrame | None:
        """Read balance-sheet facts under the same publication/version gate."""
        return self._financial("balance_sheet", instrument_id, as_of_date)

    def get_instruments(self, query: InstrumentQuery) -> pl.DataFrame:
        """Reject identities outside the already resolved request scope."""
        raise AppBuilderError(
            "historical identity scope must be resolved before freeze"
        )

    def get_factor(
        self,
        name: str,
        instruments: tuple[str, ...],
        start: str,
        end: str,
        asof: str | None = None,
    ) -> pl.DataFrame:
        """Reject a mutable factor store as a frozen historical source."""
        raise AppBuilderError(
            "mutable derived factors cannot enter a frozen history request"
        )
