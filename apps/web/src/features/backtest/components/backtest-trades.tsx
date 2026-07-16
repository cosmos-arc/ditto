import { useBacktestResult } from "../hooks";
import { ContextSection } from "@/components/domain/context-section";
import { StatusBadge } from "@/components/status/status-badge/status-badge";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { DittoErrorBoundary } from "@/lib/error-boundary";

interface BacktestTradesProps {
	readonly jobId: string;
}

const SIDE_VARIANT: Record<string, "trade" | "risk"> = {
	BUY: "trade",
	SELL: "risk",
};

export function BacktestTrades({ jobId }: BacktestTradesProps) {
	const { data, isLoading, refetch } = useBacktestResult(jobId);

	return (
		<ContextSection title="交易记录" count={data?.trades.length}>
			{isLoading && <LoadingSkeleton variant="table" rows={8} />}
			<DittoErrorBoundary fallbackProps={{ onRetry: () => void refetch() }}>
				{data && (
					<div className="space-y-1">
						{data.trades.map((trade) => (
							<div
								key={trade.id}
								className="flex items-center justify-between rounded-md px-3 py-2 text-sm transition-colors hover:bg-(--color-interaction-hover-subtle-bg)"
							>
								<div className="flex items-center gap-3">
									<StatusBadge
										variant={SIDE_VARIANT[trade.side] ?? "default"}
										label={trade.side}
										size="sm"
									/>
									<span className="font-medium">{trade.name}</span>
									<span className="text-xs text-(--color-foreground-tertiary)">{trade.code}</span>
								</div>
								<div className="flex items-center gap-4 text-(--color-foreground-tertiary)">
									<span>{trade.price.toFixed(2)}</span>
									<span>{trade.shares} 股</span>
									<span
										className={
											trade.pnl >= 0
												? "text-(--color-system-healthy)"
												: "text-(--color-system-down)"
										}
									>
										{trade.pnl >= 0 ? "+" : ""}
										{trade.pnl.toLocaleString()}
									</span>
								</div>
							</div>
						))}
					</div>
				)}
			</DittoErrorBoundary>
		</ContextSection>
	);
}
