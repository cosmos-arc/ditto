import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { ContextSection } from "@/components/domain/context-section";
import { StatusBadge } from "@/components/status/status-badge/status-badge";
import { useExperiments, useReviewQueue } from "../hooks";

const STATUS_VARIANT: Record<string, "healthy" | "warning" | "error" | "default"> = {
	completed: "healthy",
	running: "healthy",
	pending: "warning",
	failed: "error",
	approved: "healthy",
	rejected: "error",
};

const TYPE_LABEL: Record<string, string> = {
	factor: "因子",
	strategy: "策略",
	experiment: "实验",
};

export function ExperimentQueue() {
	const { data: experimentsData, isLoading: expLoading } = useExperiments();

	const { data: reviewData, isLoading: reviewLoading } = useReviewQueue();

	return (
		<div className="flex flex-col gap-4">
			<ContextSection title="实验" count={experimentsData?.total}>
				{expLoading && <LoadingSkeleton variant="table" rows={2} />}
				{experimentsData && (
					<div className="space-y-1">
						{experimentsData.items.map((exp) => (
							<div
								key={exp.id}
								className="flex items-center justify-between rounded-md px-3 py-2 text-sm transition-colors hover:bg-(--color-interaction-hover-subtle-bg)"
							>
								<div className="flex items-center gap-2">
									<StatusBadge variant={STATUS_VARIANT[exp.status] ?? "default"} label={exp.status} size="sm" />
									<span className="font-medium">{exp.name}</span>
								</div>
								<div className="flex gap-2 text-xs text-(--color-foreground-tertiary)">
									{exp.factors.map((f) => (
										<span key={f}>{f}</span>
									))}
								</div>
							</div>
						))}
					</div>
				)}
			</ContextSection>

			<ContextSection title="审核队列" count={reviewData?.total}>
				{reviewLoading && <LoadingSkeleton variant="table" rows={2} />}
				{reviewData && (
					<div className="space-y-1">
						{reviewData.items.map((item) => (
							<div
								key={item.id}
								className="flex items-center justify-between rounded-md px-3 py-2 text-sm transition-colors hover:bg-(--color-interaction-hover-subtle-bg)"
							>
								<div className="flex items-center gap-2">
									<StatusBadge variant={STATUS_VARIANT[item.status] ?? "default"} label={item.status} size="sm" />
									<span className="font-medium">{item.name}</span>
									<span className="text-xs text-(--color-foreground-tertiary)">
										{TYPE_LABEL[item.type] ?? item.type}
									</span>
								</div>
							</div>
						))}
					</div>
				)}
			</ContextSection>
		</div>
	);
}
