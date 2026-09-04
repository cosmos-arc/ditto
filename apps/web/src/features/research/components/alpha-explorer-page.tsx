import { useEffect, useMemo, useState } from "react";
import { Drawer } from "@/components/indicator/overlay";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { AgentCampaignStatus, AgentCampaignView, AgentCapabilityView, AgentStreamState } from "@/features/agent";
import { AgentCampaignApprovalDialog, AgentCampaignDraftSheet } from "@/features/agent/components";
import {
	useAgentCampaign,
	useAgentCampaigns,
	useAgentCapability,
	useAgentEventNotifications,
} from "@/features/agent/hooks";
import { ShellHeaderExtension, StatusBar } from "@/features/shell";
import { cn } from "@/lib/utils";

export type AlphaExplorerMode = "copilot" | "autoresearch" | "factor-lab";

export interface AlphaExplorerSearch {
	readonly mode?: AlphaExplorerMode;
	readonly selected?: string;
}

interface AlphaExplorerPageProps {
	readonly search?: AlphaExplorerSearch;
	readonly onSearchChange?: (search: AlphaExplorerSearch) => void;
}

interface AlphaExplorerPageViewProps {
	readonly campaigns: readonly AgentCampaignView[];
	readonly selectedCampaign: AgentCampaignView | undefined;
	readonly state: "loading" | "error" | "empty" | "ready";
	readonly errorMessage?: string;
	readonly onSelectCampaign: (campaignId: string) => void;
	readonly onOpenApproval: () => void;
}

interface AlphaExplorerHeaderProps {
	readonly capability: AgentCapabilityView | undefined;
	readonly selectedCampaign: AgentCampaignView | undefined;
	readonly isStale: boolean;
	readonly mode: AlphaExplorerMode;
	readonly streamState?: AgentStreamState;
	readonly onModeChange: (mode: AlphaExplorerMode) => void;
	readonly onOpenCreate: () => void;
}

type OverlayState =
	| { readonly kind: "deep-dive" }
	| { readonly kind: "artifact"; readonly ref: string }
	| { readonly kind: "guardrail" }
	| { readonly kind: "copilot" }
	| null;

const MODES: readonly { readonly id: AlphaExplorerMode; readonly label: string }[] = [
	{ id: "copilot", label: "Copilot Explore" },
	{ id: "autoresearch", label: "AutoResearch Review" },
	{ id: "factor-lab", label: "Factor Lab" },
];

const TERMINAL_STATUSES = new Set<AgentCampaignStatus>(["completed", "completed_with_failures", "failed", "cancelled"]);

function displayError(error: unknown): string {
	return error instanceof Error && error.message.trim() ? error.message : "Alpha 数据暂时不可用，请重试。";
}

function campaignState(campaign: AgentCampaignView): "running" | "partial" | "blocked" | "waiting" | "ready" {
	if (campaign.guardrail?.status === "blocked" || campaign.status === "failed") return "blocked";
	if (campaign.status === "draft") return "waiting";
	if (campaign.projectionState === "partial") return "partial";
	if (!TERMINAL_STATUSES.has(campaign.status)) return "running";
	return "ready";
}

function stateLabel(campaign: AgentCampaignView): string {
	const state = campaignState(campaign);
	if (state === "waiting") return "等待审批";
	if (state === "partial") return "部分可用";
	if (state === "blocked") return "已阻断";
	if (state === "running") return "探索中";
	return "可复核";
}

function statusClass(campaign: AgentCampaignView): string {
	const state = campaignState(campaign);
	if (state === "blocked") return "border-(--color-risk-critical-fg) text-(--color-risk-critical-fg)";
	if (state === "partial" || state === "waiting") {
		return "border-(--color-risk-medium-fg) text-(--color-risk-medium-fg)";
	}
	if (state === "running") return "border-(--color-agent-running-fg) text-(--color-agent-running-fg)";
	return "border-(--color-system-healthy-fg) text-(--color-system-healthy-fg)";
}

function formatMetric(value: number | null): string {
	return value === null ? "未提供" : value.toFixed(3);
}

function PanelHeading({ title, meta }: { readonly title: string; readonly meta?: string }) {
	return (
		<div className="flex min-h-(--density-header-height) items-center justify-between border-b border-(--color-border-subtle) bg-(--color-surface-panel-elevated) px-(--density-panel-padding)">
			<h2 className="text-sm font-semibold text-(--color-foreground)">{title}</h2>
			{meta && <span className="font-data text-xs tabular-nums text-(--color-foreground-tertiary)">{meta}</span>}
		</div>
	);
}

function Meta({
	label,
	value,
	mono = false,
}: {
	readonly label: string;
	readonly value: string;
	readonly mono?: boolean;
}) {
	return (
		<div className="min-w-0">
			<div className="text-xs text-(--color-foreground-tertiary)">{label}</div>
			<div
				className={cn("mt-1 break-words text-xs text-(--color-foreground-secondary)", mono && "font-data tabular-nums")}
			>
				{value}
			</div>
		</div>
	);
}

function AlphaWorkspaceToolbar({
	capability,
	selectedCampaign,
	mode,
	isStale,
	streamState,
	onModeChange,
	onOpenCreate,
}: AlphaExplorerHeaderProps) {
	return (
		<div className="flex min-w-0 flex-1 items-center gap-2 overflow-hidden pl-2">
			<div className="flex shrink-0 rounded-(--radius-md) border border-(--color-border-subtle) bg-(--color-surface-panel-base) p-0.5">
				{MODES.map((item) => (
					<button
						key={item.id}
						type="button"
						aria-pressed={mode === item.id}
						className={cn(
							"rounded-(--radius-sm) px-2 py-1 text-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-(--color-focus-ring)",
							mode === item.id
								? "bg-(--color-interaction-selected-bg) text-(--color-foreground)"
								: "text-(--color-foreground-tertiary) hover:bg-(--color-interaction-hover-subtle-bg)",
						)}
						onClick={() => onModeChange(item.id)}
					>
						{item.label}
					</button>
				))}
			</div>
			<div className="ml-auto flex shrink-0 items-center gap-2">
				<span className="hidden max-w-40 truncate font-data text-xs text-(--color-foreground-tertiary) 2xl:inline">
					{selectedCampaign?.campaignId ?? "未选择 Campaign"}
				</span>
				<Badge variant="outline" className={capability?.enabled ? "" : "text-(--color-risk-medium-fg)"}>
					Agent {capability?.runtimeState ?? "checking"}
				</Badge>
				{streamState && streamState !== "stopped" && <Badge variant="secondary">SSE {streamState}</Badge>}
				{isStale && <Badge variant="destructive">数据 stale</Badge>}
				<Button size="sm" onClick={onOpenCreate} disabled={!capability?.enabled}>
					启动探索
				</Button>
			</div>
		</div>
	);
}

function SearchSpacePanel({ campaign }: { readonly campaign: AgentCampaignView | undefined }) {
	return (
		<aside
			data-slot="source"
			aria-label="搜索空间与约束"
			className="min-h-0 overflow-y-auto border-r border-b border-(--color-border-subtle) bg-(--color-surface-panel-base) [grid-area:source]"
		>
			<PanelHeading title="搜索空间与约束" meta={campaign?.searchAxis ?? "未选择"} />
			<div className="space-y-4 p-(--density-panel-padding)">
				<Meta label="目标" value={campaign?.objective ?? "Campaign projection 未提供目标"} />
				<Meta label="搜索轴" value={campaign?.searchAxis ?? "未提供"} mono />
				<Meta label="Source snapshot" value={campaign?.sourceSnapshotId ?? "未提供"} mono />
				<div className="rounded-(--radius-md) border border-(--color-risk-medium-fg) bg-(--color-risk-medium-bg) p-2 text-xs text-(--color-risk-medium-fg)">
					knowledge cutoff 未提供；当前 projection 只能用于研究复核，不能解释为可交易时点证据。
				</div>
				<div className="grid grid-cols-2 gap-3">
					<Meta label="候选预算" value={campaign ? String(campaign.budget.candidateLimit) : "—"} mono />
					<Meta label="Fold 预算" value={campaign ? String(campaign.budget.foldRunLimit) : "—"} mono />
					<Meta label="代数上限" value={campaign ? String(campaign.budget.generationLimit) : "—"} mono />
					<Meta
						label="模型预算"
						value={campaign ? `${campaign.budget.modelSpendLimitUsdMicros.toLocaleString()} µUSD` : "—"}
						mono
					/>
				</div>
				<div>
					<div className="mb-2 text-xs text-(--color-foreground-tertiary)">允许工具</div>
					<div className="flex flex-wrap gap-1.5">
						{campaign?.allowedTools.length ? (
							campaign.allowedTools.map((tool) => (
								<Badge key={tool} variant="secondary" className="font-data">
									{tool}
								</Badge>
							))
						) : (
							<span className="text-xs text-(--color-foreground-tertiary)">未提供工具授权</span>
						)}
					</div>
				</div>
			</div>
		</aside>
	);
}

function CampaignCard({
	campaign,
	selected,
	onSelect,
	onDeepDive,
}: {
	readonly campaign: AgentCampaignView;
	readonly selected: boolean;
	readonly onSelect: () => void;
	readonly onDeepDive: () => void;
}) {
	return (
		<article
			className={cn(
				"rounded-(--radius-md) border bg-(--color-surface-panel-base) p-3 transition-colors",
				selected
					? "border-(--color-interaction-selected-border) bg-(--color-interaction-selected-bg)"
					: "border-(--color-border-subtle) hover:border-(--color-border)",
			)}
		>
			<div className="flex items-start justify-between gap-2">
				<button type="button" className="min-w-0 flex-1 text-left focus-visible:outline-none" onClick={onSelect}>
					<div className="truncate text-sm font-semibold text-(--color-foreground)">
						{campaign.objective ?? campaign.campaignId}
					</div>
					<div className="mt-1 font-data text-xs text-(--color-foreground-tertiary)">{campaign.campaignId}</div>
				</button>
				<Badge variant="outline" className={statusClass(campaign)}>
					{stateLabel(campaign)}
				</Badge>
			</div>
			<div className="mt-3 rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-panel-elevated) p-2 font-code text-xs text-(--color-foreground-secondary)">
				候选公式未由 Campaign projection 提供
			</div>
			<div className="mt-3 grid grid-cols-4 gap-2">
				<Meta label="Trials" value={`${campaign.statisticalTrialCount}/${campaign.budget.candidateLimit}`} mono />
				<Meta label="Primary" value={formatMetric(campaign.bestPrimaryMetricValue)} mono />
				<Meta label="Evidence" value={String(campaign.evidenceRefs.length)} mono />
				<Meta label="Artifacts" value={String(campaign.artifactRefs.length)} mono />
			</div>
			<div className="mt-3 flex items-center justify-between gap-2">
				<p className="line-clamp-2 text-xs leading-relaxed text-(--color-foreground-tertiary)">
					{campaign.outputSummary ?? campaign.projectionReason ?? "输出摘要未由 projection 提供"}
				</p>
				<Button size="xs" variant="outline" aria-label={`深入 ${campaign.campaignId}`} onClick={onDeepDive}>
					深入
				</Button>
			</div>
		</article>
	);
}

function ExplorationMain({
	campaigns,
	selectedCampaign,
	state,
	errorMessage,
	onSelectCampaign,
	onDeepDive,
}: Pick<
	AlphaExplorerPageViewProps,
	"campaigns" | "selectedCampaign" | "state" | "errorMessage" | "onSelectCampaign"
> & { readonly onDeepDive: () => void }) {
	return (
		<main
			data-slot="main"
			className="min-h-0 overflow-hidden border-b border-(--color-border-subtle) bg-(--color-surface-panel-base) [grid-area:main]"
		>
			<PanelHeading title="Exploration Stream" meta={`${campaigns.length} campaigns`} />
			<section
				className="border-b border-(--color-border-subtle) bg-(--color-surface-strip) p-3"
				aria-label="Current page summary"
			>
				<div className="text-xs font-medium uppercase tracking-wide text-(--color-foreground-tertiary)">当前判断</div>
				<p className="mt-1 text-sm text-(--color-foreground)">
					{selectedCampaign
						? `${stateLabel(selectedCampaign)} · ${selectedCampaign.outputSummary ?? "等待可验证产物"}`
						: "选择或启动一个 Campaign 后查看证据链。"}
				</p>
				<p className="mt-1 text-xs text-(--color-foreground-tertiary)">
					证据来源：{selectedCampaign?.evidenceRefs.length ?? 0} 项 · 影响：仅研究草案 · 下一步：复核 snapshot 与
					guardrail
				</p>
			</section>
			<div className="h-full min-h-0 overflow-y-auto p-(--density-panel-padding)">
				{state === "loading" && (
					<div className="text-sm text-(--color-foreground-tertiary)">正在读取 Campaign projection…</div>
				)}
				{state === "error" && <div className="text-sm text-(--color-risk-critical-fg)">{errorMessage}</div>}
				{state === "empty" && (
					<div className="rounded-(--radius-md) border border-dashed border-(--color-border) p-6 text-center text-sm text-(--color-foreground-tertiary)">
						暂无探索记录。使用“启动探索”创建受预算约束的 Campaign。
					</div>
				)}
				{state === "ready" && (
					<div className="grid grid-cols-2 gap-(--density-section-gap) max-xl:grid-cols-1">
						{campaigns.map((campaign) => (
							<CampaignCard
								key={campaign.campaignId}
								campaign={campaign}
								selected={campaign.campaignId === selectedCampaign?.campaignId}
								onSelect={() => onSelectCampaign(campaign.campaignId)}
								onDeepDive={() => {
									onSelectCampaign(campaign.campaignId);
									onDeepDive();
								}}
							/>
						))}
					</div>
				)}
			</div>
		</main>
	);
}

function CandidateInspector({
	campaign,
	onArtifact,
	onGuardrail,
	onCopilot,
	onApproval,
}: {
	readonly campaign: AgentCampaignView | undefined;
	readonly onArtifact: (ref: string) => void;
	readonly onGuardrail: () => void;
	readonly onCopilot: () => void;
	readonly onApproval: () => void;
}) {
	return (
		<aside
			data-slot="inspector"
			aria-label="候选详情"
			className="min-h-0 overflow-y-auto border-l border-(--color-border-subtle) bg-(--color-surface-panel-base) [grid-area:inspector]"
		>
			<PanelHeading title="Candidate Inspector" meta={campaign?.campaignId ?? "未选择"} />
			<div className="space-y-4 p-(--density-panel-padding)">
				{campaign ? (
					<>
						<div className="grid grid-cols-2 gap-3">
							<Meta label="状态" value={stateLabel(campaign)} />
							<Meta label="Projection" value={campaign.projectionState} mono />
							<Meta label="Revision" value={String(campaign.revision)} mono />
							<Meta label="Cursor" value={String(campaign.eventCursor)} mono />
						</div>
						<div>
							<div className="mb-2 text-xs font-semibold text-(--color-foreground)">Evidence chain</div>
							<div className="space-y-1.5">
								{campaign.evidenceRefs.length ? (
									campaign.evidenceRefs.map((ref) => (
										<div
											key={ref}
											className="rounded-(--radius-sm) border border-(--color-border-subtle) p-2 font-data text-xs"
										>
											{ref}
										</div>
									))
								) : (
									<span className="text-xs text-(--color-foreground-tertiary)">无 evidence refs</span>
								)}
							</div>
						</div>
						<div>
							<div className="mb-2 text-xs font-semibold text-(--color-foreground)">Artifacts</div>
							<div className="flex flex-col gap-1.5">
								{campaign.artifactRefs.length ? (
									campaign.artifactRefs.map((ref) => (
										<Button
											key={ref}
											size="xs"
											variant="outline"
											aria-label={`预览 ${ref}`}
											onClick={() => onArtifact(ref)}
										>
											{ref}
										</Button>
									))
								) : (
									<span className="text-xs text-(--color-foreground-tertiary)">尚无可验证产物</span>
								)}
							</div>
						</div>
						{campaign.guardrail && (
							<Button variant="destructive" size="sm" className="w-full" onClick={onGuardrail}>
								查看阻断原因
							</Button>
						)}
						{campaign.status === "draft" && (
							<Button size="sm" className="w-full" onClick={onApproval}>
								审查并批准 Campaign
							</Button>
						)}
						<Button variant="outline" size="sm" className="w-full" onClick={onCopilot}>
							打开 Copilot 上下文
						</Button>
					</>
				) : (
					<p className="text-sm text-(--color-foreground-tertiary)">选择一个 Campaign 查看完整证据。</p>
				)}
			</div>
		</aside>
	);
}

function AdoptionQueue({
	campaign,
	onApproval,
	onGuardrail,
}: {
	readonly campaign: AgentCampaignView | undefined;
	readonly onApproval: () => void;
	readonly onGuardrail: () => void;
}) {
	return (
		<section
			data-slot="adoption"
			aria-label="采纳队列"
			className="min-h-0 overflow-y-auto border-r border-(--color-border-subtle) bg-(--color-surface-panel-base) [grid-area:adoption]"
		>
			<PanelHeading title="采纳队列" meta={campaign ? "1 active" : "0"} />
			<div className="space-y-2 p-3">
				{!campaign && <p className="text-xs text-(--color-foreground-tertiary)">暂无待处理项</p>}
				{campaign?.status === "draft" && (
					<button
						type="button"
						className="w-full rounded-(--radius-sm) border border-(--color-risk-medium-fg) p-2 text-left"
						onClick={onApproval}
					>
						<div className="text-xs font-medium text-(--color-foreground)">{campaign.campaignId} · 等待精确审批</div>
						<div className="mt-1 text-xs text-(--color-risk-medium-fg)">授权前不会启动搜索</div>
					</button>
				)}
				{campaign?.guardrail?.status === "blocked" && (
					<button
						type="button"
						className="w-full rounded-(--radius-sm) border border-(--color-risk-critical-fg) p-2 text-left"
						onClick={onGuardrail}
					>
						<div className="text-xs font-medium text-(--color-foreground)">{campaign.campaignId} · 策略阻断</div>
						<div className="mt-1 text-xs text-(--color-risk-critical-fg)">
							{campaign.guardrail.reasonCode ?? "原因未提供"}
						</div>
					</button>
				)}
			</div>
		</section>
	);
}

function ExperimentGraph({
	campaign,
	onArtifact,
}: {
	readonly campaign: AgentCampaignView | undefined;
	readonly onArtifact: (ref: string) => void;
}) {
	return (
		<section
			data-slot="graph"
			aria-label="实验图"
			className="min-h-0 overflow-y-auto border-(--color-border-subtle) bg-(--color-surface-panel-base) [grid-area:graph]"
		>
			<PanelHeading title="Experiment Graph" meta="lineage" />
			<div className="flex min-w-max items-center gap-2 p-3">
				{["假设", "Campaign", "Evidence"].map((label) => (
					<div key={label} className="flex items-center gap-2">
						<div className="rounded-(--radius-sm) border border-(--color-border) bg-(--color-surface-panel-elevated) px-3 py-2 text-xs">
							{label}
						</div>
						<span aria-hidden="true" className="text-(--color-foreground-disabled)">
							→
						</span>
					</div>
				))}
				{campaign?.artifactRefs.length ? (
					campaign.artifactRefs.map((ref) => (
						<Button key={ref} size="xs" variant="outline" aria-label={`预览 ${ref}`} onClick={() => onArtifact(ref)}>
							{ref}
						</Button>
					))
				) : (
					<div className="rounded-(--radius-sm) border border-dashed border-(--color-border) px-3 py-2 text-xs text-(--color-foreground-tertiary)">
						Artifact 待生成
					</div>
				)}
			</div>
		</section>
	);
}

function AlphaCandidateDeepDiveDrawer({
	campaign,
	open,
	onClose,
}: {
	readonly campaign: AgentCampaignView | undefined;
	readonly open: boolean;
	readonly onClose: () => void;
}) {
	return (
		<Drawer open={open} onClose={onClose} title={`候选深入 · ${campaign?.campaignId ?? "未选择"}`}>
			<div className="space-y-4 pb-4">
				<Meta label="公式" value="Campaign projection 未提供候选公式" mono />
				<Meta label="Primary metric" value={campaign ? formatMetric(campaign.bestPrimaryMetricValue) : "未提供"} mono />
				<Meta label="Source snapshot" value={campaign?.sourceSnapshotId ?? "未提供"} mono />
				<Meta label="Evidence" value={campaign?.evidenceRefs.join(", ") || "无"} mono />
				<Meta
					label="Tool trace"
					value={campaign?.toolRecords.map((record) => record.toolName).join(", ") || "无"}
					mono
				/>
			</div>
		</Drawer>
	);
}

function AlphaArtifactPreviewDrawer({
	refId,
	open,
	onClose,
}: {
	readonly refId: string | undefined;
	readonly open: boolean;
	readonly onClose: () => void;
}) {
	return (
		<Drawer open={open} onClose={onClose} title={`产物预览 · ${refId ?? "未选择"}`}>
			<p>这里只显示稳定 artifact identity；内容、图表和指标必须由对应 artifact read projection 提供。</p>
		</Drawer>
	);
}

function AlphaGuardrailDetailDrawer({
	campaign,
	open,
	onClose,
}: {
	readonly campaign: AgentCampaignView | undefined;
	readonly open: boolean;
	readonly onClose: () => void;
}) {
	return (
		<Drawer open={open} onClose={onClose} title="Guardrail 阻断详情">
			<div className="space-y-3">
				<Meta label="状态" value={campaign?.guardrail?.status ?? "未提供"} />
				<Meta label="原因" value={campaign?.guardrail?.reasonCode ?? "未提供"} mono />
				<p>恢复前不会扩大工具权限、预算或数据可见范围。</p>
			</div>
		</Drawer>
	);
}

function AlphaCopilotContextDrawer({
	campaign,
	open,
	onClose,
}: {
	readonly campaign: AgentCampaignView | undefined;
	readonly open: boolean;
	readonly onClose: () => void;
}) {
	return (
		<Drawer open={open} onClose={onClose} title="Copilot · Alpha 上下文">
			<div className="space-y-3">
				<Meta label="Campaign" value={campaign?.campaignId ?? "未选择"} mono />
				<Meta label="Objective" value={campaign?.objective ?? "未提供"} />
				<Meta label="Source snapshot" value={campaign?.sourceSnapshotId ?? "未提供"} mono />
				<Meta label="结构化输出" value={campaign?.artifactRefs.join(", ") || "暂无 artifact"} mono />
			</div>
		</Drawer>
	);
}

export function AlphaExplorerPageView({
	campaigns,
	selectedCampaign,
	state,
	errorMessage,
	onSelectCampaign,
	onOpenApproval,
}: AlphaExplorerPageViewProps) {
	const [overlay, setOverlay] = useState<OverlayState>(null);
	return (
		<div className="flex h-full min-h-0 flex-col bg-(--color-surface-app) pb-(--height-status-bar)">
			<div className="grid min-h-0 flex-1 grid-cols-[var(--shell-alpha-source-width)_minmax(0,1fr)_var(--shell-alpha-inspector-width)] grid-rows-[minmax(0,1fr)_var(--height-studio-bottom)] overflow-hidden [grid-template-areas:'source_main_inspector'_'adoption_graph_inspector']">
				<SearchSpacePanel campaign={selectedCampaign} />
				<ExplorationMain
					campaigns={campaigns}
					selectedCampaign={selectedCampaign}
					state={state}
					errorMessage={errorMessage}
					onSelectCampaign={onSelectCampaign}
					onDeepDive={() => setOverlay({ kind: "deep-dive" })}
				/>
				<CandidateInspector
					campaign={selectedCampaign}
					onArtifact={(ref) => setOverlay({ kind: "artifact", ref })}
					onGuardrail={() => setOverlay({ kind: "guardrail" })}
					onCopilot={() => setOverlay({ kind: "copilot" })}
					onApproval={onOpenApproval}
				/>
				<AdoptionQueue
					campaign={selectedCampaign}
					onApproval={onOpenApproval}
					onGuardrail={() => setOverlay({ kind: "guardrail" })}
				/>
				<ExperimentGraph campaign={selectedCampaign} onArtifact={(ref) => setOverlay({ kind: "artifact", ref })} />
			</div>
			<AlphaCandidateDeepDiveDrawer
				campaign={selectedCampaign}
				open={overlay?.kind === "deep-dive"}
				onClose={() => setOverlay(null)}
			/>
			<AlphaArtifactPreviewDrawer
				refId={overlay?.kind === "artifact" ? overlay.ref : undefined}
				open={overlay?.kind === "artifact"}
				onClose={() => setOverlay(null)}
			/>
			<AlphaGuardrailDetailDrawer
				campaign={selectedCampaign}
				open={overlay?.kind === "guardrail"}
				onClose={() => setOverlay(null)}
			/>
			<AlphaCopilotContextDrawer
				campaign={selectedCampaign}
				open={overlay?.kind === "copilot"}
				onClose={() => setOverlay(null)}
			/>
			<StatusBar />
		</div>
	);
}

/** @contract-handoff AlphaExplorerPage */
export function AlphaExplorerPage({ search = {}, onSearchChange }: AlphaExplorerPageProps) {
	const [draftOpen, setDraftOpen] = useState(false);
	const [approvalOpen, setApprovalOpen] = useState(false);
	const capability = useAgentCapability();
	const campaignList = useAgentCampaigns({ limit: 50 });
	const campaigns = campaignList.data?.items ?? [];
	const firstCampaignId = campaigns[0]?.campaignId;
	const selectedId = search.selected ?? campaigns[0]?.campaignId ?? "";
	const campaignDetail = useAgentCampaign(selectedId);
	const selectedCampaign = campaignDetail.data ?? campaigns.find((campaign) => campaign.campaignId === selectedId);
	const mode = search.mode ?? "copilot";
	const streamState = useAgentEventNotifications(
		"campaigns",
		selectedCampaign?.campaignId ?? "",
		selectedCampaign?.eventCursor ?? 0,
		Boolean(selectedCampaign && !TERMINAL_STATUSES.has(selectedCampaign.status)),
	);

	useEffect(() => {
		if (!search.selected && firstCampaignId) {
			onSearchChange?.({ mode: search.mode, selected: firstCampaignId });
		}
	}, [firstCampaignId, onSearchChange, search.mode, search.selected]);

	const state = useMemo<AlphaExplorerPageViewProps["state"]>(() => {
		if (capability.isLoading || campaignList.isLoading || (selectedId && campaignDetail.isLoading)) return "loading";
		if (capability.error || campaignList.error || campaignDetail.error) return "error";
		return campaigns.length === 0 ? "empty" : "ready";
	}, [
		campaignDetail.error,
		campaignDetail.isLoading,
		campaignList.error,
		campaignList.isLoading,
		campaigns.length,
		capability.error,
		capability.isLoading,
		selectedId,
	]);
	const error = capability.error ?? campaignList.error ?? campaignDetail.error;

	return (
		<>
			<ShellHeaderExtension>
				<AlphaWorkspaceToolbar
					capability={capability.data}
					selectedCampaign={selectedCampaign}
					mode={mode}
					isStale={Boolean(capability.isStale || campaignList.isStale || campaignDetail.isStale)}
					streamState={streamState}
					onModeChange={(nextMode) =>
						onSearchChange?.({ ...search, mode: nextMode, selected: selectedId || undefined })
					}
					onOpenCreate={() => setDraftOpen(true)}
				/>
			</ShellHeaderExtension>
			<AlphaExplorerPageView
				campaigns={campaigns}
				selectedCampaign={selectedCampaign}
				state={state}
				errorMessage={error ? displayError(error) : undefined}
				onSelectCampaign={(campaignId) => onSearchChange?.({ ...search, mode, selected: campaignId })}
				onOpenApproval={() => setApprovalOpen(true)}
			/>
			<AgentCampaignDraftSheet
				open={draftOpen}
				onOpenChange={setDraftOpen}
				onCreated={(campaign) => {
					setDraftOpen(false);
					onSearchChange?.({ ...search, mode, selected: campaign.campaignId });
				}}
			/>
			{selectedCampaign && (
				<AgentCampaignApprovalDialog campaign={selectedCampaign} open={approvalOpen} onOpenChange={setApprovalOpen} />
			)}
		</>
	);
}
