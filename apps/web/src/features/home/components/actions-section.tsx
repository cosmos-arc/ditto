import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { ContextSection } from "@/components/domain/context-section";
import { StatusBadge } from "@/components/status/status-badge/status-badge";
import { DittoErrorBoundary } from "@/lib/error-boundary";
import { usePendingActions } from "../hooks";

const PRIORITY_VARIANT: Record<string, "critical" | "warning" | "default"> = {
	critical: "critical",
	high: "warning",
	medium: "default",
	low: "default",
};

export function ActionsSection() {
	const { data, isLoading, refetch } = usePendingActions();

	return (
		<ContextSection title="待处理事项" count={data?.actions.length}>
			{isLoading && <LoadingSkeleton variant="table" rows={4} />}
			<DittoErrorBoundary
				fallbackProps={{
					title: "待处理事项加载失败",
					onRetry: () => void refetch(),
				}}
			>
				{data && (
					<div className="space-y-1">
						{data.actions.map((action) => (
							<div
								key={action.id}
								className="flex items-center justify-between rounded-md px-3 py-2 text-sm transition-colors hover:bg-(--color-interaction-hover-subtle-bg)"
							>
								<div className="flex items-center gap-3">
									{action.badges.map((b) => (
										<StatusBadge
											key={b.label}
											variant={PRIORITY_VARIANT[action.priority] ?? "default"}
											label={b.label}
											size="sm"
										/>
									))}
									<span className="font-medium">{action.title}</span>
								</div>
								<div className="flex items-center gap-3 text-(--color-foreground-tertiary)">
									<span className="max-w-48 truncate">{action.meta}</span>
									<span>{action.time}</span>
								</div>
							</div>
						))}
					</div>
				)}
			</DittoErrorBoundary>
		</ContextSection>
	);
}
