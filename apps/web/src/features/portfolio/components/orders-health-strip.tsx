import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { DittoErrorBoundary } from "@/lib/error-boundary";
import { useOrdersSummary } from "../hooks/use-orders-summary";

const LOADING_METRIC_IDS = ["pending", "submitted", "partial", "filled", "failed"] as const;

const ORDER_METRICS = [
	["pending", "待提交", "bg-(--color-risk-medium-fg)"],
	["submitted", "已提交", "bg-(--color-accent)"],
	["partial", "部分成交", "bg-(--color-risk-warning-fg)"],
	["filled", "已成交", "bg-(--color-status-healthy-fg)"],
	["failed", "失败", "bg-(--color-risk-critical-fg)"],
] as const;

export function OrdersHealthStrip() {
	const { data, isLoading, isError, refetch } = useOrdersSummary();

	if (isLoading) {
		return (
			<div className="flex h-9 items-center gap-3 border-b border-(--color-border-subtle) bg-(--color-surface-strip) px-4">
				{LOADING_METRIC_IDS.map((metricId) => (
					<LoadingSkeleton key={metricId} variant="metric" className="flex-1" />
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
				<div className="h-9 border-b border-(--color-border-subtle) bg-(--color-surface-strip)" />
			</DittoErrorBoundary>
		);
	}

	return (
		<DittoErrorBoundary fallbackProps={{ onRetry: () => void refetch() }}>
			<div className="flex h-9 items-center overflow-hidden border-b border-(--color-border-subtle) bg-(--color-surface-strip) px-4">
				{ORDER_METRICS.map(([key, label, dotClass]) => (
					<div
						key={key}
						data-info-level={key === "pending" || key === "submitted" ? "l1" : "l2"}
						data-info-unit={`order-metric-${key}`}
						className="flex h-[35px] shrink-0 items-center gap-1.5 px-3 text-[12px] leading-[16.2px] font-medium text-(--color-foreground-tertiary)"
					>
						<i aria-hidden="true" className={`size-1.5 rounded-full ${dotClass}`} />
						<span>{label}</span>
						<span className="flex h-4 items-center rounded-sm bg-[oklch(1_0_0/.04)] px-1 font-data text-xs leading-[13.5px] font-medium">
							{data?.[key] ?? "—"}
						</span>
					</div>
				))}
			</div>
		</DittoErrorBoundary>
	);
}
