import { StatusBadge } from "@/components/status";
import { Button } from "@/components/ui/button";
import { type AgentDecisionOpinionIdentity, useDecisionOpinion } from "@/features/agent";
import { Panel, PanelBody, PanelHeader } from "@/features/shell";
import type { DailyDecisionV3ViewModel } from "../types/daily-decision-v3";

function exactValue(value: string | null): string | null {
	const normalized = value?.trim();
	return normalized ? normalized : null;
}

function utcValue(value: string | null): string | null {
	const exact = exactValue(value);
	if (!exact) return null;
	if (!/(?:Z|[+-]\d{2}:\d{2})$/.test(exact)) return null;
	const instant = new Date(exact);
	if (Number.isNaN(instant.getTime())) return null;
	return /(?:Z|[+-]00:00)$/.test(exact) ? exact : instant.toISOString();
}

function identityIssues(decision: DailyDecisionV3ViewModel): readonly string[] {
	const issues: string[] = [];
	if (!exactValue(decision.identity.strategyId)) issues.push("strategy_id");
	if (!exactValue(decision.identity.strategyVersion)) issues.push("strategy_version");
	if (!exactValue(decision.identity.tradeDate)) issues.push("trade_date");
	if (!exactValue(decision.identity.accountId)) issues.push("account_id");
	if (!exactValue(decision.identity.sleeveId)) issues.push("sleeve_id");
	if (!utcValue(decision.provenance.decisionTime)) issues.push("decision_time");
	if (!utcValue(decision.provenance.knowledgeCutoff)) issues.push("knowledge_cutoff");
	if (!utcValue(decision.provenance.publicationCutoff)) issues.push("publication_cutoff");
	if (
		decision.provenance.sourceSnapshotIds.length !== 1 ||
		!exactValue(decision.provenance.sourceSnapshotIds[0] ?? null)
	) {
		issues.push("source_snapshot_id");
	}
	return issues;
}

export function buildDecisionOpinionIdentity(decision: DailyDecisionV3ViewModel): AgentDecisionOpinionIdentity | null {
	if (identityIssues(decision).length > 0) return null;
	const strategyId = decision.identity.strategyId;
	const strategyVersion = decision.identity.strategyVersion as string;
	const tradeDate = decision.identity.tradeDate as string;
	const accountId = decision.identity.accountId as string;
	const sleeveId = decision.identity.sleeveId as string;
	return {
		strategyId,
		strategyVersion,
		tradeDate,
		accountId,
		sleeveId,
		v3ArtifactId: `daily-decision-v3:${strategyId}:${tradeDate}:${accountId}:${sleeveId}`,
		decisionTime: utcValue(decision.provenance.decisionTime) as string,
		knowledgeCutoff: utcValue(decision.provenance.knowledgeCutoff) as string,
		publicationCutoff: utcValue(decision.provenance.publicationCutoff) as string,
		sourceSnapshotId: decision.provenance.sourceSnapshotIds[0] as string,
	};
}

function EvidenceAnalysisLink({ decision }: { readonly decision: DailyDecisionV3ViewModel }) {
	const contextId = [
		decision.identity.strategyId,
		decision.identity.strategyVersion,
		decision.identity.tradeDate,
		decision.identity.accountId,
		decision.identity.sleeveId,
	]
		.map((part) => part ?? "missing")
		.join(":");
	const search = new URLSearchParams({
		tab: "runs",
		contextType: "daily-decision-v3",
		contextId,
		objective: "复核当前 Daily Decision V3 的风险证据、分歧与不确定性",
	});
	return (
		<Button asChild size="sm" variant="outline">
			<a href={`/research/agent?${search.toString()}`}>请求证据分析</a>
		</Button>
	);
}

export function DecisionBriefing({ decision }: { readonly decision: DailyDecisionV3ViewModel }) {
	const identity = buildDecisionOpinionIdentity(decision);
	const issues = identityIssues(decision);
	const opinion = useDecisionOpinion(identity);
	const unavailable = opinion.data?.status === "unavailable" || opinion.isError;

	return (
		<Panel data-slot="decision-briefing" aria-label="Decision Briefing">
			<PanelHeader
				title="Decision Briefing"
				subtitle="独立的 Agent shadow opinion；不会修改 V3 readiness。"
				actions={
					<div className="flex items-center gap-2">
						<StatusBadge label="SHADOW ONLY" variant="warning" />
						<EvidenceAnalysisLink decision={decision} />
					</div>
				}
			/>
			<PanelBody className="p-3">
				{!identity && (
					<div
						role="status"
						className="rounded-(--radius-sm) border border-(--color-border-warning) bg-(--color-risk-warning-bg) p-3"
					>
						<p className="text-sm font-medium text-(--color-risk-warning-fg)">
							exact identity 不完整，shadow opinion 未查询。
						</p>
						<p className="mt-1 font-data text-xs text-(--color-foreground-secondary)">{issues.join(" · ")}</p>
					</div>
				)}
				{identity && opinion.isLoading && (
					<p role="status" className="text-xs text-(--color-foreground-tertiary)">
						正在读取 shadow opinion…
					</p>
				)}
				{identity && unavailable && (
					<div role="status" className="flex flex-wrap items-center justify-between gap-3">
						<p className="text-xs text-(--color-foreground-secondary)">
							shadow opinion unavailable · {opinion.data?.unavailableReason ?? opinion.error?.message ?? "query failed"}
						</p>
						{opinion.isError && (
							<Button type="button" size="xs" variant="outline" onClick={() => void opinion.refetch()}>
								重试 shadow 查询
							</Button>
						)}
					</div>
				)}
				{identity && opinion.data && opinion.data.status !== "unavailable" && (
					<div className="grid gap-4 lg:grid-cols-[minmax(0,1.4fr)_minmax(14rem,0.6fr)]">
						<div>
							<div className="flex items-center gap-2">
								<StatusBadge
									label={opinion.data.status}
									variant={opinion.data.status === "completed" ? "healthy" : "critical"}
								/>
								<StatusBadge
									label={opinion.data.provenanceMatch ? "provenance matched" : "provenance mismatch"}
									variant={opinion.data.provenanceMatch ? "healthy" : "critical"}
								/>
							</div>
							<p className="mt-3 text-sm leading-relaxed text-(--color-foreground-secondary)">
								{opinion.data.summary ?? "内容未在展示契约中提供"}
							</p>
							{opinion.data.disagreements.length > 0 && (
								<section className="mt-4">
									<h3 className="text-xs font-medium text-(--color-foreground)">Disagreement</h3>
									<ul className="mt-2 space-y-1 text-xs text-(--color-risk-warning-fg)">
										{opinion.data.disagreements.map((item) => (
											<li key={item}>• {item}</li>
										))}
									</ul>
								</section>
							)}
							{opinion.data.uncertainties.length > 0 && (
								<section className="mt-4">
									<h3 className="text-xs font-medium text-(--color-foreground)">Uncertainty</h3>
									<ul className="mt-2 space-y-1 text-xs text-(--color-foreground-secondary)">
										{opinion.data.uncertainties.map((item) => (
											<li key={item}>• {item}</li>
										))}
									</ul>
								</section>
							)}
						</div>
						<div className="space-y-2 border-l border-(--color-border-subtle) pl-4 text-xs">
							<p className="text-(--color-foreground-tertiary)">
								model profile{" "}
								<span className="font-data text-(--color-foreground-secondary)">
									{opinion.data.modelProfile ?? "not provided"}
								</span>
							</p>
							<p className="text-(--color-foreground-tertiary)">
								generated{" "}
								<span className="font-data text-(--color-foreground-secondary)">
									{opinion.data.generatedAt ?? "not provided"}
								</span>
							</p>
							<p className="text-(--color-foreground-tertiary)">
								shadow outcome{" "}
								<span className="break-all font-data text-(--color-foreground-secondary)">
									{opinion.data.shadowOutcomeIdentity ?? "not provided"}
								</span>
							</p>
							<div>
								<p className="text-(--color-foreground-tertiary)">evidence refs</p>
								{opinion.data.evidenceRefs.length > 0 ? (
									<ul className="mt-1 space-y-1">
										{opinion.data.evidenceRefs.map((ref) => (
											<li key={ref} className="break-all font-data text-(--color-accent)">
												{ref}
											</li>
										))}
									</ul>
								) : (
									<p className="mt-1 text-(--color-risk-warning-fg)">none · fail closed</p>
								)}
							</div>
						</div>
					</div>
				)}
			</PanelBody>
		</Panel>
	);
}
