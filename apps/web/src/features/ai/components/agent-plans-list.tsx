import { useAgentPlans } from "../hooks";
import { ContextSection } from "@/components/domain/context-section";
import { StatusBadge } from "@/components/status/status-badge/status-badge";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { DittoErrorBoundary } from "@/lib/error-boundary";

const STATUS_VARIANT_MAP: Record<string, "live" | "warning" | "default"> = {
	running: "live",
	pending: "warning",
	completed: "default",
	failed: "error",
};

const STATUS_LABEL_MAP: Record<string, string> = {
	running: "运行中",
	pending: "等待中",
	completed: "已完成",
	failed: "失败",
};

export function AgentPlansList() {
	const {
		data,
		isLoading,
		isError,
		refetch,
	} = useAgentPlans();

	return (
		<ContextSection title="Agent 计划" count={data?.total}>
			{isLoading && <LoadingSkeleton variant="table" rows={5} />}
			<DittoErrorBoundary
				fallbackProps={{
					title: "Agent 计划加载失败",
					onRetry: () => void refetch(),
				}}
			>
				{data && (
					<div className="space-y-1">
						{data.items.map((plan) => (
							<div
								key={plan.id}
								className="rounded-md px-3 py-2 text-sm transition-colors hover:bg-(--color-surface-hover)"
							>
								<div className="flex items-center justify-between">
									<span className="font-medium text-(--color-foreground-primary)">
										{plan.name}
									</span>
									<StatusBadge
										variant={STATUS_VARIANT_MAP[plan.status] ?? "default"}
										label={STATUS_LABEL_MAP[plan.status] ?? plan.status}
										size="sm"
									/>
								</div>
								<p className="mt-1 text-xs text-(--color-foreground-tertiary)">
									{plan.objective}
								</p>
								<div className="mt-1 flex flex-wrap gap-1">
									{plan.scope.map((item) => (
										<span
											key={item}
											className="rounded bg-(--color-surface-3) px-1.5 py-0.5 text-[10px] text-(--color-foreground-tertiary)"
										>
											{item}
										</span>
									))}
								</div>
							</div>
						))}
					</div>
				)}
			</DittoErrorBoundary>
		</ContextSection>
	);
}
