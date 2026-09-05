import { ApiError } from "@/api";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { StatusBadge } from "@/components/status/status-badge/status-badge";
import { Button } from "@/components/ui/button";
import { useBacktestTrades } from "../hooks";

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
			<div className="grid grid-cols-[minmax(12rem,1.2fr)_6rem_minmax(12rem,1.4fr)_7rem_8rem] border-b border-(--color-border-subtle) bg-(--color-surface-strip) px-3 py-2 text-xs uppercase tracking-[0.08em] text-(--color-foreground-tertiary)">
				<span>Instrument</span>
				<span>Direction</span>
				<span>Entry → Exit</span>
				<span>Quantity</span>
				<span className="text-right">PnL</span>
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
							className="grid grid-cols-[minmax(12rem,1.2fr)_6rem_minmax(12rem,1.4fr)_7rem_8rem] items-center px-3 py-3 text-xs hover:bg-(--color-interaction-hover-subtle-bg)"
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
						</div>
					))}
				</div>
			)}
		</section>
	);
}
