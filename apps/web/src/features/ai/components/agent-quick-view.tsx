import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { ContextSection } from "@/components/domain/context-section";
import { StatusBadge } from "@/components/status/status-badge/status-badge";
import { DittoErrorBoundary } from "@/lib/error-boundary";
import { useAgentQuickView } from "../hooks";

const STATUS_VARIANT_MAP: Record<string, "live" | "warning" | "default"> = {
	running: "live",
	pending: "warning",
	completed: "default",
};

const STATUS_LABEL_MAP: Record<string, string> = {
	running: "运行中",
	pending: "等待中",
	completed: "已完成",
};

export function AgentQuickView() {
	const { data, isLoading, refetch } = useAgentQuickView();

	return (
		<div className="grid grid-cols-2 gap-4">
			<ContextSection title="Agent 计划" count={data?.plans.length}>
				{isLoading && <LoadingSkeleton variant="table" rows={3} />}
				<DittoErrorBoundary
					fallbackProps={{
						title: "Agent 计划加载失败",
						onRetry: () => void refetch(),
					}}
				>
					{data && (
						<div className="space-y-1">
							{data.plans.map((plan) => (
								<div
									key={plan.id}
									className="rounded-md px-3 py-2 text-sm transition-colors hover:bg-(--color-interaction-hover-subtle-bg)"
								>
									<div className="flex items-center justify-between">
										<span className="text-(--color-foreground)">{plan.name}</span>
										<StatusBadge
											variant={STATUS_VARIANT_MAP[plan.status] ?? "default"}
											label={STATUS_LABEL_MAP[plan.status] ?? plan.status}
											size="sm"
										/>
									</div>
									{plan.progress > 0 && (
										<div className="mt-1 text-xs text-(--color-foreground-tertiary)">{plan.progress}%</div>
									)}
								</div>
							))}
						</div>
					)}
				</DittoErrorBoundary>
			</ContextSection>

			<ContextSection title="近期发现" count={data?.recentFindings.length}>
				{isLoading && <LoadingSkeleton variant="table" rows={3} />}
				{data && (
					<div className="space-y-1">
						{data.recentFindings.map((finding) => (
							<div
								key={finding.id}
								className="rounded-md px-3 py-2 text-sm transition-colors hover:bg-(--color-interaction-hover-subtle-bg)"
							>
								<p className="text-(--color-foreground)">{finding.text}</p>
								<div className="mt-1 text-xs text-(--color-foreground-tertiary)">
									置信度 {Math.round(finding.confidence * 100)}%
								</div>
							</div>
						))}
					</div>
				)}
			</ContextSection>
		</div>
	);
}
