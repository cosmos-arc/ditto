import { useMarketCalendar } from "../hooks";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { DittoErrorBoundary } from "@/lib/error-boundary";

const IMPORTANCE_VARIANT: Record<string, "warning" | "default"> = {
	high: "warning",
	medium: "default",
	low: "default",
};

export function MarketCalendarList() {
	const { data, isLoading, refetch } = useMarketCalendar();

	if (isLoading) {
		return (
			<div data-info-level="l1" data-info-unit="calendar-content" className="flex flex-col gap-1 p-4">
				<h2 data-info-level="l1" data-info-unit="calendar-title" className="text-lg font-medium text-(--color-foreground) mb-3">市场日历</h2>
				<LoadingSkeleton variant="table" rows={8} columns={4} />
			</div>
		);
	}

	return (
		<DittoErrorBoundary fallbackProps={{ onRetry: () => void refetch() }}>
			<div data-info-level="l1" data-info-unit="calendar-content" className="flex flex-col gap-1 p-4">
				<h2 className="text-lg font-medium text-(--color-foreground) mb-3">市场日历</h2>
				{data?.items.map((item, i) => (
					<div
						key={`${item.date}-${item.title}-${i}`}
						className="flex items-center justify-between gap-3 py-2 border-b border-(--color-border) last:border-b-0"
					>
						<div className="flex flex-col gap-0.5 min-w-0">
							<span className="text-sm text-(--color-foreground) truncate">
								{item.title}
							</span>
							<span className="text-xs text-(--color-foreground-tertiary)">
								{item.date} {item.time} · {item.country} · {item.type}
							</span>
						</div>
						<span
							className={`text-xs font-medium shrink-0 px-2 py-0.5 rounded-full ${
								item.importance === "high"
									? "bg-(--color-risk-warning)/10 text-(--color-risk-warning)"
									: "bg-(--color-surface-2) text-(--color-foreground-tertiary)"
							}`}
						>
							{item.importance === "high" ? "重要" : "一般"}
						</span>
					</div>
				))}
			</div>
		</DittoErrorBoundary>
	);
}
