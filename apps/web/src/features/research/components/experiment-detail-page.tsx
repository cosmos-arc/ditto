import { type ReactNode, useState } from "react";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { StatusBadge } from "@/components/status/status-badge/status-badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { AgentContextActions } from "@/features/agent";
import { ObjectHubLayout, ShellHeaderExtension } from "@/features/shell";
import { ApiError } from "@/lib/api-client";
import {
	useExperiment,
	useExperimentArtifacts,
	useExperimentCandidates,
	useExperimentComparison,
	useExperimentGates,
	useExperimentSelectionEvidence,
} from "../hooks";
import { CandidateComparison } from "./candidate-comparison";
import { CandidateEvidenceDrilldown } from "./candidate-evidence-drilldown";
import { ExperimentEvidenceView } from "./experiment-evidence-view";
import { ExperimentRunControls } from "./experiment-run-controls";
import { ExperimentValidationView } from "./experiment-validation-view";

interface ExperimentDetailPageProps {
	readonly experimentId: string;
}

type WorkbenchTab = "candidates" | "validation" | "evidence" | "candidate-evidence";

function errorText(error: Error | null): string | null {
	if (!error) return null;
	return error instanceof ApiError
		? `${error.status} ${error.errorCode ?? "EXPERIMENT_RESOURCE_ERROR"}: ${error.message}`
		: error.message;
}

function ResourceError({ error }: { readonly error: Error | null }) {
	const text = errorText(error);
	return text ? (
		<p role="alert" className="text-xs text-(--color-led-danger)">
			{text}
		</p>
	) : null;
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
		<section className="mx-auto flex w-full max-w-[1500px] flex-col gap-3 p-(--density-panel-padding)">
			<header className="flex items-end justify-between gap-3 border-b border-(--color-border-subtle) pb-2">
				<div>
					<h2 className="text-sm font-semibold text-(--color-foreground)">{title}</h2>
					<p className="mt-0.5 text-xs text-(--color-foreground-tertiary)">{description}</p>
				</div>
			</header>
			{children}
		</section>
	);
}

export function ExperimentDetailPage({ experimentId }: ExperimentDetailPageProps) {
	const detail = useExperiment(experimentId);
	const candidates = useExperimentCandidates(experimentId);
	const gates = useExperimentGates(experimentId);
	const comparison = useExperimentComparison(experimentId, detail.data?.stage, detail.data?.revision);
	const artifacts = useExperimentArtifacts(experimentId);
	const selection = useExperimentSelectionEvidence(experimentId, detail.data?.stage);
	const [tab, setTab] = useState<WorkbenchTab>("candidates");
	const [inspectedCandidate, setInspectedCandidate] = useState<string | null>(null);

	if (detail.isLoading) {
		return (
			<section aria-label="实验运行工作台" className="h-full min-h-0 p-4">
				<LoadingSkeleton variant="panel" />
			</section>
		);
	}
	if (!detail.data) {
		return (
			<section aria-label="实验运行工作台" className="flex h-full min-h-0 items-center justify-center p-4">
				<div className="w-full max-w-xl rounded-(--radius-md) border border-(--color-led-danger) bg-(--color-surface-1) p-4">
					<ResourceError error={detail.error} />
					<p className="mt-2 text-xs text-(--color-foreground-tertiary)">未加载详情前不会渲染候选、门禁或证据数据。</p>
					<Button size="sm" variant="outline" className="mt-3" onClick={() => void detail.refetch()}>
						重试实验详情
					</Button>
				</div>
			</section>
		);
	}

	const server = detail.data;
	const statusVariant = server.status.toLowerCase() === "failed" ? "critical" : "healthy";

	function inspectCandidate(candidateId: string): void {
		setInspectedCandidate(candidateId);
		setTab("candidate-evidence");
	}

	return (
		<section aria-label="实验运行工作台" className="h-full min-h-0">
			<ShellHeaderExtension>
				<div
					className="ml-auto flex min-w-0 items-center gap-1.5"
					data-info-level="l1"
					data-info-unit="experiment-actions"
				>
					<AgentContextActions
						className="flex items-center gap-1.5"
						contextType="experiment-revision"
						contextId={`${experimentId}@${server.revision}`}
						evidenceObjective="复核当前实验 revision 的候选、门禁、产物与选择证据"
						authorObjective="提出当前实验的结构化变更草案，并保留 frozen identity"
					/>
					<ExperimentRunControls detail={server} />
				</div>
			</ShellHeaderExtension>
			<Tabs value={tab} onValueChange={(value) => setTab(value as WorkbenchTab)} className="h-full min-h-0 gap-0">
				<ObjectHubLayout
					className="grid-rows-[36px_45px_minmax(0,1fr)_36px]"
					meta={
						<div
							data-testid="experiment-detail-meta"
							data-info-level="l1"
							data-info-unit="experiment-meta"
							className="flex h-9 min-w-0 items-center gap-3 overflow-hidden border-b border-(--color-border-subtle) bg-(--color-surface-strip) px-4"
						>
							<h1 className="shrink-0 text-sm font-semibold">Experiment {server.experiment_id}</h1>
							<StatusBadge variant={statusVariant} label={server.status} size="sm" />
							<span className="shrink-0 font-data text-xs text-(--color-foreground-secondary)">
								{server.status} · {server.stage} · revision {server.revision}
							</span>
							<span aria-hidden="true" className="h-4 w-px shrink-0 bg-(--color-border-subtle)" />
							<span className="shrink-0 font-data text-xs">{server.strategy_version}</span>
							<span className="hidden min-w-0 truncate font-data text-xs text-(--color-foreground-tertiary) xl:inline">
								snapshot {server.snapshot_id}
							</span>
							{server.failure_code && (
								<span className="ml-auto truncate font-data text-xs text-(--color-led-danger)">
									{server.failure_code}
								</span>
							)}
						</div>
					}
					tabs={
						<nav
							aria-label="实验详情导航"
							data-testid="experiment-detail-tabs"
							data-info-level="l1"
							data-info-unit="experiment-tabs"
							className="h-[45px] border-b border-(--color-border-subtle) bg-(--color-surface-strip) px-4"
						>
							<TabsList variant="line" className="h-full" aria-label="实验工作台视图">
								<TabsTrigger value="candidates">候选与选择</TabsTrigger>
								<TabsTrigger value="validation">验证与门禁</TabsTrigger>
								<TabsTrigger value="evidence">产物与证据</TabsTrigger>
								<TabsTrigger value="candidate-evidence" disabled={!inspectedCandidate}>
									候选证据{inspectedCandidate ? ` · ${inspectedCandidate}` : ""}
								</TabsTrigger>
							</TabsList>
						</nav>
					}
					main={
						<>
							<TabsContent value="candidates" className="m-0 h-full min-h-0 overflow-y-auto">
								<WorkbenchPanel
									title="Candidate comparison"
									description="最多固定四个候选；只有当前 revision 的发布证据可用于晋级。"
								>
									<ResourceError error={candidates.error} />
									<ResourceError error={comparison.error} />
									<CandidateComparison
										experimentId={experimentId}
										revision={server.revision}
										candidates={candidates.data ?? server.candidates}
										comparison={comparison.data ?? null}
										selectionEvidenceReady={selection.data !== undefined}
										selectionState={server.selection_state}
										onInspect={inspectCandidate}
									/>
								</WorkbenchPanel>
							</TabsContent>
							<TabsContent value="validation" className="m-0 h-full min-h-0 overflow-y-auto">
								<WorkbenchPanel
									title="Validation and gates"
									description="服务端 fold 窗口、隔离参数与规则判定；部分失败保持可见。"
								>
									<ResourceError error={gates.error} />
									<ExperimentValidationView folds={server.folds} gates={gates.data ?? []} />
								</WorkbenchPanel>
							</TabsContent>
							<TabsContent value="evidence" className="m-0 h-full min-h-0 overflow-y-auto">
								<WorkbenchPanel
									title="Artifacts and selection evidence"
									description="固定的产物 hash 与已发布 selection ledger；缺失时不构造替代值。"
								>
									<ResourceError error={artifacts.error} />
									<ResourceError error={selection.error} />
									<ExperimentEvidenceView artifacts={artifacts.data ?? []} selectionEvidence={selection.data ?? null} />
								</WorkbenchPanel>
							</TabsContent>
							<TabsContent value="candidate-evidence" className="m-0 h-full min-h-0 overflow-y-auto">
								<WorkbenchPanel
									title="Candidate evidence"
									description="选择、排除与因子贡献均绑定当前 experiment/candidate identity。"
								>
									{inspectedCandidate ? (
										<CandidateEvidenceDrilldown experimentId={experimentId} candidateId={inspectedCandidate} />
									) : (
										<p className="text-sm text-(--color-foreground-tertiary)">尚未选择候选证据。</p>
									)}
								</WorkbenchPanel>
							</TabsContent>
						</>
					}
					bottom={
						<div
							data-testid="experiment-detail-bottom"
							data-info-level="l2"
							data-info-unit="experiment-frozen-identity"
							className="flex h-9 min-w-0 items-center gap-5 overflow-hidden border-t border-(--color-border-subtle) bg-(--color-surface-strip) px-4 text-[11px] text-(--color-foreground-tertiary)"
						>
							<span className="shrink-0">
								Candidates{" "}
								<strong className="font-data font-medium text-(--color-foreground-secondary)">
									{server.candidate_count}
								</strong>
							</span>
							<span className="shrink-0">
								Folds{" "}
								<strong className="font-data font-medium text-(--color-foreground-secondary)">
									{server.fold_count}
								</strong>
							</span>
							<span className="shrink-0">
								Protocol{" "}
								<strong className="font-data font-medium text-(--color-foreground-secondary)">
									{server.fold_protocol_id}@{server.fold_protocol_version}
								</strong>
							</span>
							<span className="min-w-0 truncate font-data" title={server.strategy_spec_hash}>
								SPEC {server.strategy_spec_hash}
							</span>
							<span className="hidden min-w-0 truncate font-data 2xl:inline" title={server.research_cycle_hash}>
								CYCLE {server.research_cycle_hash}
							</span>
							<span className="ml-auto shrink-0 font-data">updated {server.updated_at}</span>
						</div>
					}
				/>
			</Tabs>
		</section>
	);
}
