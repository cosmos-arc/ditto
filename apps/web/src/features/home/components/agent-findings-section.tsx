import { useAgentFindings } from "../hooks";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { DittoErrorBoundary } from "@/lib/error-boundary";

const FINDING_ICON_CLASS: Record<string, string> = {
	insight: "text-(--color-brand-500)",
	warning: "text-(--color-risk-warning)",
	info: "text-(--color-foreground-tertiary)",
};

/**
 * AgentFindingsSection — "Agent 洞察" findings feed.
 * Matches prototype .findings-feed with .finding-item rows.
 */
export function AgentFindingsSection() {
	const { data, isLoading, refetch } = useAgentFindings();

	return (
		<div className="flex min-h-0 flex-col overflow-hidden" data-info-level="l2" data-info-unit="agent-findings">
			<div className="flex items-center justify-between border-b border-(--color-border-subtle) px-3 py-2">
				<span className="text-sm font-medium text-(--color-foreground)">
					Agent 洞察
					<span className="ml-2 font-normal text-(--color-foreground-tertiary)">关联分析</span>
				</span>
			</div>
			<div className="flex-1 overflow-y-auto px-3 py-2">
				{isLoading && <LoadingSkeleton variant="table" rows={3} />}
				<DittoErrorBoundary
					fallbackProps={{
						title: "Agent 洞察加载失败",
						onRetry: () => void refetch(),
					}}
				>
					{data && (
						<div className="flex flex-col gap-1">
							{data.findings.map((finding, i) => (
								<div
									key={`${finding.source}-${i}`}
									className="rounded-[4px] p-1 transition-colors hover:bg-(--color-interaction-hover-subtle-bg)"
								>
									<div className="flex items-center gap-1.5">
										<span className={`shrink-0 text-xs ${FINDING_ICON_CLASS[finding.icon] ?? "text-(--color-foreground-tertiary)"}`}>
											{finding.icon === "insight" ? "💡" : finding.icon === "warning" ? "⚠" : "ℹ"}
										</span>
										<span className="text-xs text-(--color-foreground)">
											{finding.summary ?? finding.source}
										</span>
									</div>
									<p className="mt-0.5 text-xs text-(--color-foreground-tertiary)">
										{finding.text}
									</p>
								</div>
							))}
							<div className="pt-1">
								<button
									type="button"
									className="text-xs text-(--color-foreground-secondary) transition-colors hover:bg-(--color-interaction-hover-subtle-bg) rounded-[var(--radius-sm)] px-1.5 py-0.5"
								>
									展开全部 Agent 分析 →
								</button>
							</div>
						</div>
					)}
				</DittoErrorBoundary>
			</div>
		</div>
	);
}
