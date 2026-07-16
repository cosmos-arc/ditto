import { Metric } from "@/components/data/metric";
import { usePlatformHealth } from "../hooks";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { DittoErrorBoundary } from "@/lib/error-boundary";

export function HealthStrip() {
	const { data, isLoading, refetch } = usePlatformHealth();

	if (isLoading) {
		return (
			<div className="flex h-9 items-center gap-3 px-4 py-1.5">
				{Array.from({ length: 4 }).map((_, i) => (
					<LoadingSkeleton key={i} variant="metric" className="flex-1" />
				))}
			</div>
		);
	}

	return (
		<DittoErrorBoundary
			fallbackProps={{
				title: "健康数据加载失败",
				onRetry: () => void refetch(),
			}}
		>
			<div className="flex h-9 items-center gap-3 px-4 py-1.5">
				<Metric
					variant="strip"
					label="数据新鲜度"
					value={`${data?.freshness ?? "—"}%`}
					trend={(data?.freshness ?? 0) >= 95 ? "up" : "down"}
				/>
				<Metric
					variant="strip"
					label="数据完整性"
					value={`${data?.completeness ?? "—"}%`}
					trend={(data?.completeness ?? 0) >= 98 ? "up" : "down"}
				/>
				<Metric
					variant="strip"
					label="数据准确性"
					value={`${data?.accuracy ?? "—"}%`}
					trend={(data?.accuracy ?? 0) >= 95 ? "up" : "down"}
				/>
				<Metric
					variant="strip"
					label="运行任务"
					value={data?.jobsStatus.running ?? "—"}
					sub={`失败 ${data?.jobsStatus.failed ?? 0}`}
				/>
			</div>
		</DittoErrorBoundary>
	);
}
