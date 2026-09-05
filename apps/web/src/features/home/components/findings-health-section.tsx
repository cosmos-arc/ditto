import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { ContextSection } from "@/components/domain/context-section";
import { StatusBadge } from "@/components/status/status-badge/status-badge";
import { DittoErrorBoundary } from "@/lib/error-boundary";
import { useAgentFindings, useDataHealth } from "../hooks";

export function FindingsAndHealthSection() {
	const { data: findingsData, isLoading: findingsLoading, refetch: refetchFindings } = useAgentFindings();

	const { data: healthData, isLoading: healthLoading } = useDataHealth();

	return (
		<div className="grid grid-cols-2 gap-4">
			<ContextSection title="Agent 发现" count={findingsData?.findings.length}>
				{findingsLoading && <LoadingSkeleton variant="table" rows={3} />}
				<DittoErrorBoundary
					fallbackProps={{
						title: "Agent 发现加载失败",
						onRetry: () => void refetchFindings(),
					}}
				>
					{findingsData && (
						<div className="space-y-1">
							{findingsData.findings.map((finding) => (
								<div
									key={`${finding.source}-${finding.text}`}
									className="rounded-md px-3 py-2 text-sm transition-colors hover:bg-(--color-interaction-hover-subtle-bg)"
								>
									<p className="text-(--color-foreground)">{finding.text}</p>
									<div className="mt-1 flex items-center gap-2 text-xs text-(--color-foreground-tertiary)">
										<span>{finding.source}</span>
										<StatusBadge
											variant={finding.icon === "warning" ? "warning" : "default"}
											label={finding.icon}
											size="sm"
										/>
									</div>
								</div>
							))}
						</div>
					)}
				</DittoErrorBoundary>
			</ContextSection>

			<ContextSection title="数据健康">
				{healthLoading && <LoadingSkeleton variant="table" rows={4} />}
				{healthData && (
					<div className="space-y-1">
						{healthData.providers.map((provider) => (
							<div
								key={provider.label}
								className="flex items-center justify-between rounded-md px-3 py-2 text-sm transition-colors hover:bg-(--color-interaction-hover-subtle-bg)"
							>
								<div className="flex items-center gap-2">
									<span className="font-medium">{provider.label}</span>
									<StatusBadge
										variant={
											provider.status === "healthy" ? "healthy" : provider.status === "degraded" ? "degraded" : "error"
										}
										label={provider.statusText}
										size="sm"
									/>
								</div>
							</div>
						))}
					</div>
				)}
			</ContextSection>
		</div>
	);
}
