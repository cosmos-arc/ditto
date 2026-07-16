import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { ContextSection } from "@/components/domain/context-section";
import { DittoErrorBoundary } from "@/lib/error-boundary";
import { useRegimeHistory } from "../hooks";

export function RegimeHistoryList() {
	const { data, isLoading, refetch } = useRegimeHistory();

	if (isLoading) {
		return (
			<ContextSection title="状态切换历史">
				<LoadingSkeleton variant="table" rows={5} columns={4} />
			</ContextSection>
		);
	}

	return (
		<DittoErrorBoundary fallbackProps={{ onRetry: () => void refetch() }}>
			<ContextSection title="状态切换历史" count={data?.total}>
				{data?.items.map((item) => (
					<div
						key={`${item.date}-${item.fromState}`}
						className="flex items-start justify-between gap-2 border-b border-(--color-border) py-2 last:border-b-0"
					>
						<div className="flex flex-col gap-0.5 min-w-0">
							<span className="text-xs text-(--color-foreground-tertiary) font-data">{item.date}</span>
							<span className="text-sm text-(--color-foreground) truncate">{item.trigger}</span>
						</div>
						<div className="flex items-center gap-1 shrink-0">
							<span className="text-xs text-(--color-foreground-tertiary)">{item.fromState}</span>
							<span className="text-(--color-foreground-tertiary)">→</span>
							<span className="text-xs text-(--color-foreground-secondary) font-medium">{item.toState}</span>
						</div>
					</div>
				))}
			</ContextSection>
		</DittoErrorBoundary>
	);
}
