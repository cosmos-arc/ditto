import { Metric } from "@/components/data/metric/metric";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { DittoErrorBoundary } from "@/lib/error-boundary";
import { useOrdersSummary } from "../hooks/use-orders-summary";

export function OrdersHealthStrip() {
	const { data, isLoading, isError, refetch } = useOrdersSummary();

	if (isLoading) {
		return (
			<div className="flex gap-3 px-4 py-2">
				{Array.from({ length: 5 }).map((_, i) => (
					<LoadingSkeleton key={i} variant="metric" className="flex-1" />
				))}
			</div>
		);
	}

	if (isError) {
		return (
			<DittoErrorBoundary
				fallbackProps={{
					title: "订单汇总数据加载失败",
					onRetry: () => void refetch(),
				}}
			>
				<div />
			</DittoErrorBoundary>
		);
	}

	return (
		<DittoErrorBoundary fallbackProps={{ onRetry: () => void refetch() }}>
			<div className="flex gap-3 px-4 py-2">
				<div data-info-level="l1" data-info-unit="order-metric-pending">
					<Metric variant="strip" label="待提交" value={data?.pending ?? "—"} />
				</div>
				<div data-info-level="l1" data-info-unit="order-metric-submitted">
					<Metric variant="strip" label="已提交" value={data?.submitted ?? "—"} />
				</div>
				<Metric variant="strip" label="部分成交" value={data?.partial ?? "—"} />
				<div data-info-level="l2" data-info-unit="order-metric-filled">
					<Metric variant="strip" label="已成交" value={data?.filled ?? "—"} />
				</div>
				<div data-info-level="l2" data-info-unit="order-metric-failed">
					<Metric variant="strip" label="失败" value={data?.failed ?? "—"} />
				</div>
			</div>
		</DittoErrorBoundary>
	);
}
