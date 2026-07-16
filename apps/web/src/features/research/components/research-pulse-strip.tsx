import { Metric } from "@/components/data/metric";
import { useResearchPulse } from "../hooks";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { DittoErrorBoundary } from "@/lib/error-boundary";

export function ResearchPulseStrip() {
	const { data, isLoading, refetch } = useResearchPulse();

	if (isLoading) {
		return (
			<div data-slot="session-strip" className="flex gap-3 px-4 py-2">
				{Array.from({ length: 4 }).map((_, i) => (
					<LoadingSkeleton key={i} variant="metric" className="flex-1" />
				))}
			</div>
		);
	}

	return (
		<DittoErrorBoundary fallbackProps={{ onRetry: () => void refetch() }}>
			<div data-slot="session-strip" className="flex gap-3 px-4 py-2">
				<Metric
					variant="strip"
					label="活跃因子"
					value={data?.activeFactors ?? "—"}
				/>
				<Metric
					variant="strip"
					label="衰减因子"
					value={data?.degradingFactors ?? "—"}
					trend={data && data.degradingFactors > 0 ? "down" : "up"}
				/>
				<Metric
					variant="strip"
					label="失败因子"
					value={data?.failedFactors ?? "—"}
					trend={data && data.failedFactors > 0 ? "down" : "up"}
				/>
				<Metric
					variant="strip"
					label="审核队列"
					value={data?.reviewQueueLength ?? "—"}
				/>
			</div>
		</DittoErrorBoundary>
	);
}
