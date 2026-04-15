import { Metric } from "@/components/data/metric/metric";
import { useSignalsQueue } from "../hooks/use-signals-queue";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { DittoErrorBoundary } from "@/lib/error-boundary";

export function SignalsHealthStrip() {
	const { data, isLoading, isError, refetch } = useSignalsQueue();

	if (isLoading) {
		return (
			<div className="flex gap-3 px-4 py-2">
				{Array.from({ length: 4 }).map((_, i) => (
					<LoadingSkeleton key={i} variant="metric" className="flex-1" />
				))}
			</div>
		);
	}

	if (isError) {
		return (
			<DittoErrorBoundary
				fallbackProps={{
					title: "信号队列数据加载失败",
					onRetry: () => void refetch(),
				}}
			>
				<div />
			</DittoErrorBoundary>
		);
	}

	return (
		<DittoErrorBoundary
			fallbackProps={{ onRetry: () => void refetch() }}
		>
			<div className="flex gap-3 px-4 py-2">
				<div data-info-level="l1" data-info-unit="signal-metric-pending">
					<Metric
						variant="strip"
						label="待处理"
						value={data?.pending ?? "—"}
					/>
				</div>
				<div data-info-level="l1" data-info-unit="signal-metric-confirmed">
					<Metric
						variant="strip"
						label="已确认"
						value={data?.confirmed ?? "—"}
					/>
				</div>
				<div data-info-level="l1" data-info-unit="signal-metric-ignored">
					<Metric
						variant="strip"
						label="已忽略"
						value={data?.ignored ?? "—"}
					/>
				</div>
				<div data-info-level="l1" data-info-unit="signal-metric-ordered">
					<Metric
						variant="strip"
						label="已下单"
						value={data?.ordered ?? "—"}
					/>
				</div>
			</div>
		</DittoErrorBoundary>
	);
}
