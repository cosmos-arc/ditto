import { useAgentFindings } from "../hooks";
import { ContextSection } from "@/components/domain/context-section";
import { StatusBadge } from "@/components/status/status-badge/status-badge";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { DittoErrorBoundary } from "@/lib/error-boundary";

const IMPACT_VARIANT_MAP: Record<string, "critical" | "warning" | "default"> = {
	high: "critical",
	medium: "warning",
	low: "default",
};

const IMPACT_LABEL_MAP: Record<string, string> = {
	high: "高",
	medium: "中",
	low: "低",
};

const FINDING_STATUS_VARIANT_MAP: Record<
	string,
	"warning" | "healthy" | "error"
> = {
	pending: "warning",
	approved: "healthy",
	rejected: "error",
};

const FINDING_STATUS_LABEL_MAP: Record<string, string> = {
	pending: "待审批",
	approved: "已批准",
	rejected: "已拒绝",
};

export function AgentFindingsList() {
	const {
		data,
		isLoading,
		isError,
		refetch,
	} = useAgentFindings();

	return (
		<ContextSection title="Agent 发现" count={data?.total}>
			{isLoading && <LoadingSkeleton variant="table" rows={5} />}
			<DittoErrorBoundary
				fallbackProps={{
					title: "Agent 发现加载失败",
					onRetry: () => void refetch(),
				}}
			>
				{data && (
					<div className="space-y-1">
						{data.items.map((finding) => (
							<div
								key={finding.id}
								className="rounded-md px-3 py-2 text-sm transition-colors hover:bg-(--color-interaction-hover-subtle-bg)"
							>
								<div className="flex items-start justify-between gap-2">
									<p className="text-(--color-foreground)">
										{finding.text}
									</p>
								</div>
								<div className="mt-2 flex items-center gap-2 text-xs text-(--color-foreground-tertiary)">
									<span>
										置信度 {Math.round(finding.confidence * 100)}%
									</span>
									<StatusBadge
										variant={IMPACT_VARIANT_MAP[finding.impact] ?? "default"}
										label={IMPACT_LABEL_MAP[finding.impact] ?? finding.impact}
										size="sm"
									/>
									<StatusBadge
										variant={
											FINDING_STATUS_VARIANT_MAP[finding.status] ?? "default"
										}
										label={
											FINDING_STATUS_LABEL_MAP[finding.status] ?? finding.status
										}
										size="sm"
									/>
								</div>
								{finding.evidence.length > 0 && (
									<ul className="mt-1 list-inside list-disc space-y-0.5 text-xs text-(--color-foreground-tertiary)">
										{finding.evidence.map((item) => (
											<li key={item}>{item}</li>
										))}
									</ul>
								)}
							</div>
						))}
					</div>
				)}
			</DittoErrorBoundary>
		</ContextSection>
	);
}
