import { Metric } from "@/components/data/metric/metric";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { DittoErrorBoundary } from "@/lib/error-boundary";
import { useRiskSummary } from "../hooks";

const LOADING_METRIC_IDS = [
	"value-at-risk",
	"max-drawdown",
	"beta",
	"gross-exposure",
	"net-exposure",
	"near-limit",
	"breach-count",
] as const;

export function RiskScopeStrip() {
	const { data, isLoading, refetch } = useRiskSummary();

	if (isLoading) {
		return (
			<div className="flex h-9 items-center gap-3 px-4 py-1.5">
				{LOADING_METRIC_IDS.map((metricId) => (
					<LoadingSkeleton key={metricId} variant="metric" className="flex-1" />
				))}
			</div>
		);
	}

	return (
		<DittoErrorBoundary
			fallbackProps={{
				title: "风控数据加载失败",
				onRetry: () => void refetch(),
			}}
		>
			<div data-info-level="l1" data-info-unit="risk-scope-strip" className="flex h-9 items-center gap-3 px-4 py-1.5">
				<Metric
					variant="strip"
					label="VaR(95%)"
					value={`${data?.var ?? "—"}%`}
					trend={(data?.var ?? 0) <= 5 ? "up" : "down"}
				/>
				<Metric variant="strip" label="最大回撤" value={`${data?.maxDD ?? "—"}%`} trend="down" />
				<Metric variant="strip" label="Beta" value={data?.beta?.toFixed(2) ?? "—"} />
				<Metric
					variant="strip"
					label="总敞口"
					value={`${data?.grossExposure ?? "—"}%`}
					trend={(data?.grossExposure ?? 0) <= 150 ? "up" : "down"}
				/>
				<Metric variant="strip" label="净敞口" value={`${data?.netExposure ?? "—"}%`} />
				<Metric variant="strip" label="逼近限额" value={data?.nearLimit ? "是" : "否"} />
				<Metric
					variant="strip"
					label="违规次数"
					value={data?.breachCount ?? "—"}
					trend={(data?.breachCount ?? 0) === 0 ? "up" : "down"}
				/>
			</div>
		</DittoErrorBoundary>
	);
}
