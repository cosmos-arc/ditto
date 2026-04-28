import { useTradingSession } from "../hooks";
import { Metric } from "@/components/data/metric";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { DittoErrorBoundary } from "@/lib/error-boundary";

export function TradingSessionStrip() {
	const { data, isLoading, refetch } = useTradingSession();

	if (isLoading) {
		return (
			<div className="flex gap-3 px-4 py-2">
				{Array.from({ length: 4 }).map((_, i) => (
					<LoadingSkeleton key={i} variant="metric" className="flex-1" />
				))}
			</div>
		);
	}

	return (
		<DittoErrorBoundary fallbackProps={{ onRetry: () => void refetch() }}>
			<div data-info-level="l2" data-info-unit="session-strip" className="flex gap-3 px-4 py-2">
				<Metric variant="strip" label="交易阶段" value={data?.phase ?? "—"} />
				<Metric
					variant="strip"
					label="现金余额"
					value={data?.cashBalance != null ? `¥${data.cashBalance.toLocaleString()}` : "—"}
				/>
				<Metric
					variant="strip"
					label="已用保证金"
					value={data?.margin.usedMargin != null ? `¥${data.margin.usedMargin.toLocaleString()}` : "—"}
				/>
				<Metric
					variant="strip"
					label="风控预算"
					value={data?.riskBudget != null ? `${(data.riskBudget * 100).toFixed(0)}%` : "—"}
					trend={data && data.riskBudget > 0.5 ? "down" : "up"}
				/>
			</div>
		</DittoErrorBoundary>
	);
}
