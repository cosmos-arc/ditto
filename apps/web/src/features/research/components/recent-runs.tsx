import { useResearchRuns } from "../hooks";
import { ContextSection } from "@/components/domain/context-section";
import { StatusBadge } from "@/components/status/status-badge/status-badge";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { DittoErrorBoundary } from "@/lib/error-boundary";

const RUN_VARIANT: Record<string, "healthy" | "degraded" | "warning" | "error"> = {
	completed: "healthy",
	running: "healthy",
	pending: "default",
	failed: "error",
	warning: "warning",
	cancelled: "degraded",
};

const TYPE_LABEL: Record<string, string> = {
	backtest: "回测",
	factor_analysis: "因子分析",
	experiment: "实验",
};

export function RecentRuns() {
	const { data, isLoading, isError, refetch } = useResearchRuns();

	return (
		<ContextSection title="近期运行" count={data?.total}>
			{isLoading && <LoadingSkeleton variant="table" rows={3} />}
			<DittoErrorBoundary fallbackProps={{ onRetry: () => void refetch() }}>
				{data && (
					<div className="space-y-1">
						{data.items.map((run) => (
							<div
								key={run.id}
								className="flex items-center justify-between rounded-md px-3 py-2 text-sm transition-colors hover:bg-(--color-interaction-hover-subtle-bg)"
							>
								<div className="flex items-center gap-3">
									<StatusBadge
										variant={RUN_VARIANT[run.status] ?? "default"}
										label={run.status}
										size="sm"
									/>
									<span className="font-medium">{run.name}</span>
								</div>
								<div className="flex items-center gap-3 text-(--color-foreground-tertiary)">
									<span>{TYPE_LABEL[run.type] ?? run.type}</span>
									{run.keyMetric && <span>{run.keyMetric}</span>}
								</div>
							</div>
						))}
					</div>
				)}
			</DittoErrorBoundary>
		</ContextSection>
	);
}
