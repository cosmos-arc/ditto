import { Metric } from "@/components/data/metric";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { DittoErrorBoundary } from "@/lib/error-boundary";
import { useBacktestResult } from "../hooks";

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
	const { data, isLoading, refetch } = useBacktestResult(jobId);

	if (isLoading) {
		return (
			<div className="flex gap-3 px-4 py-3">
				{LOADING_METRIC_IDS.map((metricId) => (
					<LoadingSkeleton key={metricId} variant="metric" className="flex-1" />
				))}
			</div>
		);
	}

	return (
		<DittoErrorBoundary fallbackProps={{ onRetry: () => void refetch() }}>
			{data && (
				<div className="flex gap-3 px-4 py-3">
					<Metric variant="strip" label="Sharpe" value={data.statistics.sharpe.toFixed(2)} />
					<Metric variant="strip" label="最大回撤" value={`${data.statistics.mdd}%`} trend="down" />
					<Metric variant="strip" label="胜率" value={`${data.statistics.winRate.toFixed(1)}%`} />
					<Metric
						variant="strip"
						label="年化收益"
						value={`${data.statistics.annualizedReturn}%`}
						trend={data.statistics.annualizedReturn >= 0 ? "up" : "down"}
					/>
					<Metric variant="strip" label="盈亏比" value={data.statistics.plRatio.toFixed(2)} />
					<Metric variant="strip" label="换手率" value={`${data.statistics.turnover.toFixed(1)}x`} />
				</div>
			)}
		</DittoErrorBoundary>
	);
}
