import { useMemo, useState } from "react";
import { ApiError } from "@/api/errors";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { OverlayFactList, PageActionOverlay } from "@/components/domain/page-action-overlay";
import { StatusBadge } from "@/components/status/status-badge/status-badge";
import { Button } from "@/components/ui/button";
import { useBacktestAudit, useBacktestRun, useBacktestTrades } from "../hooks";
import type { BacktestAuditRecord, BacktestTradeRecord } from "../types";

interface BacktestTradesProps {
	readonly jobId: string;
}

const SIDE_VARIANT: Record<string, "trade" | "risk"> = {
	buy: "trade",
	long: "trade",
	sell: "risk",
	short: "risk",
};

export function BacktestTrades({ jobId }: BacktestTradesProps) {
	const query = useBacktestTrades(jobId);
	const runQuery = useBacktestRun(jobId);
	const auditQuery = useBacktestAudit(jobId);
	const [selected, setSelected] = useState<BacktestTradeRecord | null>(null);

	const evidenceRows = useMemo(() => {
		if (!selected) return [];
		const rows = auditQuery.data ?? [];
		const dates = new Set([selected.entryDate, selected.exitDate, selected.tradeDate]);
		return rows.filter((row) => row.instrumentId === selected.instrumentId && dates.has(row.tradeDate));
	}, [auditQuery.data, selected]);

	if (query.isLoading) return <LoadingSkeleton variant="table" rows={8} />;
	if (query.error) {
		const message =
			query.error instanceof ApiError
				? `${query.error.status} ${query.error.errorCode ?? "BACKTEST_TRADES_ERROR"}: ${query.error.message}`
				: query.error.message;
		return (
			<div className="rounded-(--radius-md) border border-(--color-led-danger) bg-(--color-surface-1) p-4 text-xs">
				<p role="alert" className="text-(--color-led-danger)">
					{message}
				</p>
				<Button size="sm" variant="outline" className="mt-3" onClick={() => void query.refetch()}>
					重试成交记录
				</Button>
			</div>
		);
	}
	const trades = query.data ?? [];

	return (
		<section className="overflow-hidden rounded-(--radius-md) border border-(--color-border-subtle) bg-(--color-surface-1)">
			<div className="grid grid-cols-[minmax(12rem,1.2fr)_6rem_minmax(12rem,1.4fr)_7rem_8rem_7rem] border-b border-(--color-border-subtle) bg-(--color-surface-strip) px-3 py-2 text-xs uppercase tracking-[0.08em] text-(--color-foreground-tertiary)">
				<span>Instrument</span>
				<span>Direction</span>
				<span>Entry → Exit</span>
				<span>Quantity</span>
				<span className="text-right">PnL</span>
				<span className="text-right">证据</span>
			</div>
			{trades.length === 0 ? (
				<p className="p-4 text-xs text-(--color-foreground-tertiary)">当前运行没有成交记录。</p>
			) : (
				<div className="divide-y divide-(--color-border-subtle)">
					{trades.map((trade) => (
						<div
							key={`${trade.instrumentId}:${trade.tradeDate}:${trade.entryDate}:${trade.exitDate}:${trade.quantity}`}
							data-info-level="l2"
							data-info-unit="trade-record"
							className="grid grid-cols-[minmax(12rem,1.2fr)_6rem_minmax(12rem,1.4fr)_7rem_8rem_7rem] items-center px-3 py-3 text-xs hover:bg-(--color-interaction-hover-subtle-bg)"
						>
							<div>
								<p className="font-medium text-(--color-foreground)">Instrument #{trade.instrumentId}</p>
								<p className="font-data text-xs text-(--color-foreground-tertiary)">{trade.tradeDate}</p>
							</div>
							<StatusBadge
								variant={SIDE_VARIANT[trade.direction.toLowerCase()] ?? "default"}
								label={trade.direction}
								size="sm"
							/>
							<div className="font-data text-(--color-foreground-secondary)">
								<p>
									{trade.entryDate} @ {trade.entryPrice.toFixed(2)}
								</p>
								<p>
									{trade.exitDate} @ {trade.exitPrice.toFixed(2)}
								</p>
							</div>
							<span className="font-data">{trade.quantity.toLocaleString("en-US")}</span>
							<span
								className={`text-right font-data ${trade.pnl >= 0 ? "text-(--color-system-healthy)" : "text-(--color-system-down)"}`}
							>
								{trade.pnl >= 0 ? "+" : ""}
								{trade.pnl.toLocaleString("en-US")}
							</span>
							<span className="text-right">
								<button
									type="button"
									data-testid={`trade-evidence-${trade.instrumentId}-${trade.entryDate}`}
									onClick={() => setSelected(trade)}
									className="rounded-md border border-(--color-border-primary) px-2 py-1 text-xs text-(--color-foreground-secondary) hover:bg-(--color-interaction-hover-subtle-bg)"
								>
									查证据
								</button>
							</span>
						</div>
					))}
				</div>
			)}
			<TradeEvidenceDrawer
				asOf={runQuery.data?.completedAt || runQuery.data?.startedAt || ""}
				evidenceLoading={auditQuery.isLoading}
				evidenceRows={evidenceRows}
				onClose={() => setSelected(null)}
				runId={jobId}
				trade={selected}
			/>
		</section>
	);
}

function TradeEvidenceDrawer({
	asOf,
	evidenceLoading,
	evidenceRows,
	onClose,
	runId,
	trade,
}: {
	readonly asOf: string;
	readonly evidenceLoading: boolean;
	readonly evidenceRows: readonly BacktestAuditRecord[];
	readonly onClose: () => void;
	readonly runId: string;
	readonly trade: BacktestTradeRecord | null;
}) {
	if (!trade) return null;
	// 跨域跳转上下文合同：对象（标的+定位日）、原因（来源 run）、知识时间（as_of），
	// 与 /instruments/$id 的 validateSearch 参数一一对应。
	const drillHref = (date: string, direction: "buy" | "sell"): string => {
		const params = new URLSearchParams({
			tab: "chart",
			focusDate: date,
			drillRunId: runId,
			drillAsOf: asOf,
			drillDirection: direction,
		});
		return `/instruments/${trade.instrumentId}?${params.toString()}`;
	};
	return (
		<PageActionOverlay
			open
			kind="drawer"
			title="成交证据下钻"
			description="该笔成交的精确身份、执行前审计证据与 K 线定位入口。"
			onClose={onClose}
		>
			<OverlayFactList
				facts={[
					["Instrument", `#${trade.instrumentId}`],
					["Direction", trade.direction],
					["Entry", `${trade.entryDate} @ ${trade.entryPrice.toFixed(4)}`],
					["Exit", `${trade.exitDate} @ ${trade.exitPrice.toFixed(4)}`],
					["Quantity", trade.quantity.toLocaleString("en-US")],
					["PnL", `${trade.pnl >= 0 ? "+" : ""}${trade.pnl.toLocaleString("en-US")}`],
					["as_of", asOf || "未报告"],
				]}
			/>
			<section className="rounded-(--radius-md) border border-(--color-border-subtle) p-3">
				<h4 className="text-xs font-semibold uppercase tracking-[0.06em] text-(--color-foreground-tertiary)">
					Pre-trade 审计证据
				</h4>
				<p className="mt-1 text-xs text-(--color-foreground-muted)">按标的 + 成交/进出场日期过滤运行审计记录。</p>
				{evidenceLoading ? (
					<p className="mt-2 text-xs text-(--color-foreground-tertiary)">正在加载审计…</p>
				) : evidenceRows.length === 0 ? (
					<p className="mt-2 text-xs text-(--color-foreground-tertiary)">该成交时点无 pre-trade 审计记录。</p>
				) : (
					<ul className="mt-2 space-y-2" data-testid="trade-evidence-rows">
						{evidenceRows.map((row) => (
							<li
								key={row.id}
								className="rounded-(--radius-sm) bg-(--color-surface-strip) p-2 font-data text-xs leading-5"
							>
								#{row.id} · {row.tradeDate} · {String(row.payload["direction"] ?? "—")} ×{" "}
								{String(row.payload["final_quantity"] ?? "—")}（{String(row.payload["decision"] ?? "—")}）
							</li>
						))}
					</ul>
				)}
			</section>
			<div className="flex flex-wrap gap-2">
				<a
					href={drillHref(trade.entryDate, "buy")}
					data-testid={`drill-link-buy-${trade.instrumentId}-${trade.entryDate}`}
					className="rounded-(--radius-sm) bg-(--brand-accent) px-3 py-2 text-xs font-medium text-(--brand-accent-fg)"
				>
					K 线定位 · 买入（{trade.entryDate}）
				</a>
				<a
					href={drillHref(trade.exitDate, "sell")}
					data-testid={`drill-link-sell-${trade.instrumentId}-${trade.entryDate}`}
					className="rounded-(--radius-sm) border border-(--color-border-primary) px-3 py-2 text-xs font-medium text-(--color-foreground-secondary)"
				>
					K 线定位 · 卖出（{trade.exitDate}）
				</a>
			</div>
		</PageActionOverlay>
	);
}
