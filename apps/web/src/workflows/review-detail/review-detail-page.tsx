/** Governed review packet workbench for one exact experiment and strategy version. */
import type { ReactElement, ReactNode } from "react";
import { useState } from "react";
import { ApiError } from "@/api";
import { ContextSection } from "@/components/domain/context-section";
import { StatusBadge } from "@/components/status/status-badge/status-badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { AgentContextActions } from "@/features/agent";
import {
	CandidateRationale,
	EvidenceHashes,
	HardGateList,
	LineagePanel,
	R1ImpactEvidence,
	ReviewDecisionBanner,
	SelectionExposureEvidence,
	SpecDiffView,
	useReviewPacket,
} from "@/features/research";
import { ObjectHubLayout, ShellHeaderExtension } from "@/features/shell";
import { ReviewDecisionPanel, StrategyGovernanceAudit, useStrategyVersions, useVersionDiff } from "@/features/strategy";

interface ReviewDetailPageProps {
	readonly experimentId: string;
	readonly strategyId: string;
	readonly version: number;
}

type ReviewTab = "decision" | "evidence" | "lineage" | "audit";

function typedError(error: Error): string {
	return error instanceof ApiError
		? `${error.status} ${error.errorCode ?? "REVIEW_RESOURCE_ERROR"}: ${error.message}`
		: error.message;
}

function reviewVariant(outcome: string): "healthy" | "warning" | "critical" | "idle" {
	switch (outcome.toLowerCase()) {
		case "approved":
		case "published":
			return "healthy";
		case "pending":
			return "warning";
		case "rejected":
			return "critical";
		default:
			return "idle";
	}
}

function WorkbenchPanel({
	children,
	description,
	title,
}: {
	readonly children: ReactNode;
	readonly description: string;
	readonly title: string;
}) {
	return (
		<section className="mx-auto flex w-full max-w-[1500px] flex-col gap-3 p-4">
			<header className="border-b border-(--color-border-subtle) pb-2">
				<h2 className="text-sm font-semibold text-(--color-foreground)">{title}</h2>
				<p className="mt-0.5 text-xs text-(--color-foreground-tertiary)">{description}</p>
			</header>
			{children}
		</section>
	);
}

function EvidenceGroup({ children }: { readonly children: ReactNode }) {
	return (
		<div className="min-w-0 rounded-(--radius-md) border border-(--color-border-subtle) bg-(--color-surface-1) py-1">
			{children}
		</div>
	);
}

export function ReviewDetailPage({ experimentId, strategyId, version }: ReviewDetailPageProps): ReactElement {
	const packetQuery = useReviewPacket(experimentId);
	const versionsQuery = useStrategyVersions(strategyId);
	const diffQuery = useVersionDiff(strategyId, version, packetQuery.isSuccess);
	const [tab, setTab] = useState<ReviewTab>("decision");

	const versionInfo = versionsQuery.data?.find((entry) => entry.version === version);
	const state = versionInfo?.state ?? "unknown";
	const reviewOutcome = versionInfo?.reviewOutcome ?? "unknown";

	if (packetQuery.isLoading) {
		return (
			<section aria-label="审查决策工作台" className="h-full min-h-0 p-4 text-sm text-(--color-foreground-tertiary)">
				加载审查包…
			</section>
		);
	}
	if (packetQuery.isError || packetQuery.data === undefined) {
		const error = packetQuery.error;
		const message =
			error instanceof ApiError
				? `${error.status} ${error.errorCode ?? "REVIEW_PACKET_ERROR"}: ${error.message}`
				: (error?.message ?? "Review packet unavailable");
		return (
			<section
				aria-label="审查决策工作台"
				className="flex h-full min-h-0 items-center justify-center p-(--density-panel-padding)"
			>
				<div className="flex w-full max-w-xl flex-col gap-2 rounded-(--radius-md) border border-(--color-led-danger) bg-(--color-surface-1) p-4 text-sm text-(--color-led-danger)">
					<p role="alert">{message}</p>
					<p className="text-xs text-(--color-foreground-tertiary)">未加载 packet 前不会展示门禁、证据或治理动作。</p>
					<Button size="sm" variant="outline" className="self-start" onClick={() => void packetQuery.refetch()}>
						重试审查包
					</Button>
				</div>
			</section>
		);
	}

	const packet = packetQuery.data;

	return (
		<section aria-label="审查决策工作台" className="h-full min-h-0">
			<ShellHeaderExtension>
				<AgentContextActions
					className="ml-auto flex items-center gap-1.5"
					contextType="review-packet"
					contextId={`${experimentId}:${strategyId}@${version}:${packet.bundleHash}`}
					evidenceObjective="复核当前 review packet 的 hard gates、统计证据、spec diff、血统与影响证据"
				/>
			</ShellHeaderExtension>
			<Tabs value={tab} onValueChange={(value) => setTab(value as ReviewTab)} className="h-full min-h-0 gap-0">
				<ObjectHubLayout
					className="grid-rows-[36px_45px_minmax(0,1fr)_36px]"
					meta={
						<div
							data-testid="review-detail-meta"
							data-info-level="l1"
							data-info-unit="review-meta"
							className="flex h-9 min-w-0 items-center gap-3 overflow-hidden border-b border-(--color-border-subtle) bg-(--color-surface-strip) px-4"
						>
							<h1 className="shrink-0 text-sm font-semibold">
								Review {strategyId} · v{version}
							</h1>
							<StatusBadge label={reviewOutcome} variant={reviewVariant(reviewOutcome)} size="sm" />
							<StatusBadge
								label={packet.hardReviewBlocked ? "hard-gate blocked" : "hard-gate passed"}
								variant={packet.hardReviewBlocked ? "critical" : "healthy"}
								size="sm"
							/>
							<span className="shrink-0 font-data text-xs text-(--color-foreground-secondary)">state {state}</span>
							<span aria-hidden="true" className="h-4 w-px shrink-0 bg-(--color-border-subtle)" />
							<span className="min-w-0 truncate font-data text-xs text-(--color-foreground-tertiary)">
								experiment {experimentId}
							</span>
						</div>
					}
					tabs={
						<nav
							aria-label="审查工作台导航"
							data-testid="review-detail-tabs"
							data-info-level="l1"
							data-info-unit="review-tabs"
							className="h-[45px] border-b border-(--color-border-subtle) bg-(--color-surface-strip) px-4"
						>
							<TabsList variant="line" className="h-full" aria-label="审查工作台视图">
								<TabsTrigger value="decision">裁决与门禁</TabsTrigger>
								<TabsTrigger value="evidence">证据与差异</TabsTrigger>
								<TabsTrigger value="lineage">血统与影响</TabsTrigger>
								<TabsTrigger value="audit">治理审计</TabsTrigger>
							</TabsList>
						</nav>
					}
					main={
						<>
							{versionsQuery.error && (
								<p
									role="alert"
									className="border-b border-(--color-border-subtle) px-4 py-2 text-xs text-(--color-led-danger)"
								>
									{typedError(versionsQuery.error)}
								</p>
							)}
							<TabsContent value="decision" className="m-0 h-full min-h-0 overflow-y-auto">
								<WorkbenchPanel
									title="Decision and hard gates"
									description="裁决只绑定当前 strategy version 与 packet bundle；hard gate 阻断时批准和发布 fail closed。"
								>
									<div className="grid min-w-0 gap-3 xl:grid-cols-[minmax(0,1fr)_22rem]">
										<EvidenceGroup>
											<ReviewDecisionBanner
												strategyId={strategyId}
												version={version}
												experimentId={experimentId}
												state={state}
												reviewOutcome={reviewOutcome}
												hardReviewBlocked={packet.hardReviewBlocked}
											/>
											<div className="border-t border-(--color-border-subtle)">
												<HardGateList packet={packet} />
											</div>
										</EvidenceGroup>
										<EvidenceGroup>
											<div data-contract-slot="review-actions">
												<ReviewDecisionPanel
													strategyId={strategyId}
													version={version}
													reviewOutcome={reviewOutcome}
													hardReviewBlocked={packet.hardReviewBlocked}
													bundleHash={packet.bundleHash}
													experimentId={experimentId}
												/>
											</div>
											<p className="border-t border-(--color-border-subtle) px-4 py-3 text-xs text-(--color-foreground-tertiary)">
												所有动作要求执行者与原因；发布还需精确 bundle hash 与确认句。
											</p>
										</EvidenceGroup>
									</div>
								</WorkbenchPanel>
							</TabsContent>
							<TabsContent value="evidence" className="m-0 h-full min-h-0 overflow-y-auto">
								<WorkbenchPanel
									title="Evidence and canonical diff"
									description="统计 payload 仅作为证据身份展示，不把软统计结果伪装成自动 PASS。"
								>
									<div className="grid min-w-0 gap-3 xl:grid-cols-2">
										<EvidenceGroup>
											<EvidenceHashes packet={packet} />
											<div className="border-t border-(--color-border-subtle)">
												{diffQuery.error ? (
													<ContextSection title="Spec Diff">
														<div className="flex flex-col gap-1 p-(--density-panel-padding) text-xs text-(--color-led-danger)">
															<p role="alert">{typedError(diffQuery.error)}</p>
															<button
																type="button"
																className="self-start underline"
																onClick={() => void diffQuery.refetch()}
															>
																重试 Spec Diff
															</button>
														</div>
													</ContextSection>
												) : (
													<SpecDiffView changes={diffQuery.data?.changes ?? []} />
												)}
											</div>
										</EvidenceGroup>
										<EvidenceGroup>
											<CandidateRationale rationale={packet.candidateRationale} />
											<div className="border-t border-(--color-border-subtle)">
												<SelectionExposureEvidence packet={packet} />
											</div>
										</EvidenceGroup>
									</div>
								</WorkbenchPanel>
							</TabsContent>
							<TabsContent value="lineage" className="m-0 h-full min-h-0 overflow-y-auto">
								<WorkbenchPanel
									title="Lineage and downstream impact"
									description="spec、参数、snapshot、registry 与产物引用均保持可寻址；R1 缺失不会生成替代证据。"
								>
									<div className="grid min-w-0 gap-3 xl:grid-cols-2">
										<EvidenceGroup>
											<LineagePanel packet={packet} />
										</EvidenceGroup>
										<EvidenceGroup>
											<R1ImpactEvidence packet={packet} />
										</EvidenceGroup>
									</div>
								</WorkbenchPanel>
							</TabsContent>
							<TabsContent value="audit" className="m-0 h-full min-h-0 overflow-y-auto">
								<WorkbenchPanel
									title="Append-only governance audit"
									description="事件记录与当前 packet hash 相邻展示；不推断历史事件与 packet 的持久化关联。"
								>
									<EvidenceGroup>
										<div className="p-4">
											<StrategyGovernanceAudit strategyId={strategyId} currentPacketBundleHash={packet.bundleHash} />
										</div>
									</EvidenceGroup>
								</WorkbenchPanel>
							</TabsContent>
						</>
					}
					bottom={
						<div
							data-testid="review-detail-bottom"
							data-info-level="l2"
							data-info-unit="review-frozen-identity"
							className="flex h-9 min-w-0 items-center gap-5 overflow-hidden border-t border-(--color-border-subtle) bg-(--color-surface-strip) px-4 text-[11px] text-(--color-foreground-tertiary)"
						>
							<span className="min-w-0 truncate font-data" title={packet.bundleHash}>
								bundle {packet.bundleHash}
							</span>
							<span className="hidden min-w-0 truncate font-data lg:inline" title={packet.specHash}>
								spec {packet.specHash}
							</span>
							<span className="hidden min-w-0 truncate font-data xl:inline" title={packet.snapshotHash}>
								snapshot {packet.snapshotHash}
							</span>
							<span className="ml-auto shrink-0 font-data">candidate {packet.candidateId}</span>
						</div>
					}
				/>
			</Tabs>
		</section>
	);
}
