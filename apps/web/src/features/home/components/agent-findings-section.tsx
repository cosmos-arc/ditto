import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { Button } from "@/components/ui/button";
import { useAgentCapability, useAgentRuns, useCreateAgentRun } from "@/features/agent/hooks";
import { DittoErrorBoundary } from "@/lib/error-boundary";
import { useAgentFindings, useMarketPulseMetrics } from "../hooks";

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
	const findings = useAgentFindings();
	const market = useMarketPulseMetrics();
	const capability = useAgentCapability();
	const brief = market.data?.brief;
	const contextId = brief ? `${brief.featureSetId}:${brief.sourceSnapshotSetId}` : "";
	const runs = useAgentRuns(
		{ contextId, contextType: "market_context", limit: 1 },
		Boolean(brief && capability.data?.enabled && capability.data.runtimeState === "available"),
	);
	const createBrief = useCreateAgentRun();
	const agentRun = createBrief.data ?? runs.data?.items[0];
	const agentAvailable = Boolean(
		brief && capability.data?.enabled && capability.data.runtimeState === "available" && capability.data.defaultProfile,
	);

	function generateBrief() {
		if (!brief || !capability.data?.defaultProfile) return;
		createBrief.mutate({
			context: { contextId, contextType: "market_context" },
			executeImmediately: true,
			executionScope: {
				allowedUniverse: ["market-context"],
				decisionTime: brief.asOf,
				knowledgeCutoff: brief.knowledgeCutoff,
				maxOutputTokens: 1024,
				publicationCutoff: brief.publicationCutoff,
				sourceSnapshotId: brief.sourceSnapshotSetId,
			},
			idempotencyKey: `market-context-evidence-brief-v1:${brief.sourceSnapshotSetId}`,
			maxModelSpendUsd: "0.25",
			maxModelTokens: 2048,
			modelProfile: capability.data.defaultProfile,
			objective:
				"生成当前 MarketContext EvidenceBrief：说明状态、主要驱动、变化、风险与待复核事项；每个数值结论必须引用 market_context_evidence 返回的精确 evidence_ref，缺失证据时明确拒答。",
			retentionClass: "standard",
			sessionId: "",
		});
	}

	const mutationError = createBrief.error instanceof Error ? createBrief.error.message : null;

	return (
		<div className="flex min-h-0 flex-col overflow-hidden" data-info-level="l2" data-info-unit="agent-findings">
			<div className="flex items-center justify-between border-b border-(--color-border-subtle) px-3 py-2">
				<span className="text-sm font-medium text-(--color-foreground)">
					Agent Brief
					<span className="ml-2 font-normal text-(--color-foreground-tertiary)">MarketContext · 关联分析</span>
				</span>
			</div>
			<div className="flex-1 overflow-y-auto px-3 py-2">
				{(findings.isLoading || market.isLoading || capability.isLoading) && (
					<LoadingSkeleton variant="table" rows={3} />
				)}
				<DittoErrorBoundary
					fallbackProps={{
						title: "Agent 洞察加载失败",
						onRetry: () => void findings.refetch(),
					}}
				>
					<div className="flex flex-col gap-3">
						<section
							aria-label="MarketContext Agent Brief"
							className="rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-strip) p-3"
						>
							<div className="flex items-start justify-between gap-3">
								<div>
									<p className="text-xs font-medium text-(--color-foreground)">MarketContext EvidenceBrief</p>
									<p className="mt-1 text-xs text-(--color-foreground-tertiary)">
										只读、精确 PIT、数值需绑定宿主认证证据。
									</p>
								</div>
								{agentAvailable && !agentRun && (
									<Button type="button" size="sm" onClick={generateBrief} disabled={createBrief.isPending}>
										{createBrief.isPending ? "生成中…" : "生成 MarketContext Agent Brief"}
									</Button>
								)}
							</div>
							{market.isError && (
								<p className="mt-3 text-xs text-(--color-risk-danger)">MarketContext 不可用，Agent Brief 已阻断。</p>
							)}
							{!capability.isLoading && !agentAvailable && !market.isError && (
								<p className="mt-3 text-xs text-(--color-foreground-tertiary)">
									Agent 运行时未启用；不会生成伪 Brief。
								</p>
							)}
							{createBrief.isPending && <p className="mt-3 text-xs">正在读取认证 MarketContext 并生成引用…</p>}
							{mutationError && <p className="mt-3 text-xs text-(--color-risk-danger)">{mutationError}</p>}
							{agentRun && (
								<div className="mt-3 space-y-2">
									<p className="text-xs leading-relaxed text-(--color-foreground-secondary)">
										{agentRun.outputSummary ?? `Agent run ${agentRun.status}`}
									</p>
									<div className="flex flex-wrap gap-1.5 text-[11px] text-(--color-foreground-tertiary)">
										{agentRun.toolRecords.map((record) => (
											<span key={record.callId} className="rounded border border-(--color-border-subtle) px-1.5 py-0.5">
												{record.toolName}
											</span>
										))}
									</div>
									{agentRun.evidenceRefs.map((reference) => (
										<p key={reference} className="break-all font-mono text-xs text-(--color-foreground-tertiary)">
											{reference}
										</p>
									))}
								</div>
							)}
						</section>
						{findings.data && (
							<div className="flex flex-col gap-1 border-t border-(--color-border-subtle) pt-2">
								{findings.data.findings.length === 0 && (
									<p className="py-3 text-xs text-(--color-foreground-tertiary)">
										Agent 投影不可用；Daily Decision V3 未提供 Agent findings。
									</p>
								)}
								{findings.data.findings.map((finding) => (
									<div
										key={`${finding.source}-${finding.text}`}
										className="rounded-[4px] p-1 transition-colors hover:bg-(--color-interaction-hover-subtle-bg)"
									>
										<div className="flex items-center gap-1.5">
											<span
												className={`shrink-0 text-xs ${FINDING_ICON_CLASS[finding.icon] ?? "text-(--color-foreground-tertiary)"}`}
											>
												{finding.icon === "insight" ? "💡" : finding.icon === "warning" ? "⚠" : "ℹ"}
											</span>
											<span className="text-xs text-(--color-foreground)">{finding.summary ?? finding.source}</span>
										</div>
										<p className="mt-0.5 text-xs text-(--color-foreground-tertiary)">{finding.text}</p>
									</div>
								))}
								{findings.data.findings.length > 0 && (
									<div className="pt-1">
										<button
											type="button"
											className="text-xs text-(--color-foreground-secondary) transition-colors hover:bg-(--color-interaction-hover-subtle-bg) rounded-[var(--radius-sm)] px-1.5 py-0.5"
										>
											展开全部 Agent 分析 →
										</button>
									</div>
								)}
							</div>
						)}
					</div>
				</DittoErrorBoundary>
			</div>
		</div>
	);
}
