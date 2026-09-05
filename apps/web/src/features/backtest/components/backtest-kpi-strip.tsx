import { ApiError } from "@/api";
import { Metric } from "@/components/data/metric";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { Button } from "@/components/ui/button";
import { useBacktestReport } from "../hooks";

const LOADING_METRIC_IDS = [
	"sharpe",
	"max-drawdown",
	"win-rate",
	"annual-return",
	"profit-loss-ratio",
	"turnover",
] as const;

interface BacktestKpiStripProps {
	readonly jobId: string;
}

export function BacktestKpiStrip({ jobId }: BacktestKpiStripProps) {
	const query = useBacktestReport(jobId);

	if (query.isLoading) {
		return (
			<div className="flex h-14 gap-3 px-4 py-2.5">
				{LOADING_METRIC_IDS.map((metricId) => (
					<LoadingSkeleton key={metricId} variant="metric" className="flex-1" />
				))}
			</div>
		);
	}
	const alpha = query.data?.alphaStats;
	const trades = query.data?.tradeStats;

	if (query.error || !alpha) {
		const message = query.error
			? query.error instanceof ApiError
				? `${query.error.status} ${query.error.errorCode ?? "BACKTEST_REPORT_ERROR"}: ${query.error.message}`
				: query.error.message
			: "绩效统计尚未发布";
		return (
			<div className="flex h-14 items-center gap-3 border-b border-(--color-border-subtle) px-4">
				<div>
					<p className="text-xs font-medium text-(--color-foreground-secondary)">绩效证据 · 未评估</p>
					<p role={query.error ? "alert" : undefined} className="mt-0.5 text-xs text-(--color-foreground-tertiary)">
						{message}
					</p>
				</div>
				<Button size="sm" variant="outline" className="ml-auto" onClick={() => void query.refetch()}>
					重试绩效报告
				</Button>
			</div>
		);
	}

	return (
		<div className="flex h-14 min-w-max items-center gap-5 overflow-x-auto border-b border-(--color-border-subtle) px-4">
			<Metric variant="strip" label="Sharpe" value={alpha.sharpeRatio.toFixed(2)} />
			<Metric variant="strip" label="最大回撤" value={`${Math.abs(alpha.maxDrawdown * 100).toFixed(1)}%`} />
			<Metric variant="strip" label="年化收益" value={`${(alpha.annualizedReturn * 100).toFixed(1)}%`} />
			<Metric variant="strip" label="Sortino" value={alpha.sortinoRatio.toFixed(2)} />
			<Metric variant="strip" label="总换手" value={`${alpha.totalTurnover.toFixed(1)}x`} />
			<Metric variant="strip" label="胜率" value={trades ? `${(trades.winRate * 100).toFixed(1)}%` : "未评估"} />
		</div>
	);
}
