import { useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";
import {
	useAgentApproval,
	useAgentApprovals,
	useAgentCampaign,
	useAgentCampaigns,
	useAgentCapability,
	useAgentEventNotifications,
	useAgentRun,
	useAgentRuns,
	useAgentSessions,
} from "../hooks";
import type {
	AgentApprovalView,
	AgentCampaignStatus,
	AgentCampaignView,
	AgentPage,
	AgentRunStatus,
	AgentRunView,
	AgentSessionView,
	AgentTab,
} from "../types";
import { AgentAuthorPreview } from "./agent-author-preview";
import {
	AgentApprovalExactActionDialog,
	AgentArtifactPreviewDrawer,
	AgentCampaignApprovalDialog,
	AgentCampaignCancelDialog,
	AgentCampaignDraftSheet,
	AgentEvidenceDetailDrawer,
	AgentGuardrailDetailDrawer,
	AgentRunCancelDialog,
	AgentRunCreateSheet,
} from "./agent-overlays";

export type AgentConsoleSearch = {
	readonly tab?: AgentTab;
	readonly status?: string;
	readonly selected?: string;
	readonly sessionId?: string;
	readonly sessionOffset?: number;
	readonly offset?: number;
	readonly contextType?: string;
	readonly contextId?: string;
	readonly objective?: string;
};

type InspectorSelection =
	| { readonly kind: "evidence"; readonly value: string }
	| { readonly kind: "artifact"; readonly value: string }
	| { readonly kind: "guardrail"; readonly value: string };

const TERMINAL_RUN = new Set<AgentRunStatus>(["completed", "failed", "cancelled"]);
const TERMINAL_CAMPAIGN = new Set<AgentCampaignStatus>(["completed", "completed_with_failures", "failed", "cancelled"]);
const SELECT_CLASS =
	"h-7 rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-1) px-2 font-data text-xs text-(--color-foreground) outline-none focus-visible:border-(--color-focus-border) focus-visible:ring-3 focus-visible:ring-(--color-focus-ring)";

function formatDate(value: string | null): string {
	if (!value) return "—";
	const date = new Date(value);
	return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN", { hour12: false });
}

function isExpired(value: string): boolean {
	const timestamp = Date.parse(value);
	return !Number.isFinite(timestamp) || timestamp <= Date.now();
}

function hasExactApprovalPayload(approval: AgentApprovalView): boolean {
	return (
		Object.keys(approval.actionPayload).length > 0 && approval.actionHash.length === 64 && approval.expiresAt.length > 0
	);
}

function isApprovalActionable(approval: AgentApprovalView): boolean {
	return approval.status === "pending" && !isExpired(approval.expiresAt) && hasExactApprovalPayload(approval);
}

function remainingDecimal(limit: string, used: string): string {
	const limitValue = Number(limit);
	const usedValue = Number(used);
	if (!Number.isFinite(limitValue) || !Number.isFinite(usedValue)) return "unavailable";
	return Math.max(0, limitValue - usedValue).toFixed(2);
}

function formatInteger(value: number): string {
	return value.toLocaleString("en-US");
}

function StatusBadge({ status }: { readonly status: string }) {
	const critical = status === "failed" || status === "blocked" || status === "expired";
	const warning =
		status.includes("waiting") ||
		status.includes("partial") ||
		status.includes("degraded") ||
		status.includes("paused");
	return (
		<Badge variant={critical ? "destructive" : warning ? "outline" : "secondary"}>{status.replaceAll("_", " ")}</Badge>
	);
}

function Meta({
	label,
	value,
	mono = false,
}: {
	readonly label: string;
	readonly mono?: boolean;
	readonly value: string;
}) {
	return (
		<div className="grid grid-cols-[7rem_minmax(0,1fr)] gap-2 text-xs">
			<span className="text-(--color-foreground-tertiary)">{label}</span>
			<span
				className={
					mono
						? "break-all font-data text-(--color-foreground-secondary)"
						: "break-words text-(--color-foreground-secondary)"
				}
			>
				{value}
			</span>
		</div>
	);
}

function PanelState({
	error,
	isLoading,
	label,
	onRetry,
}: {
	readonly error: Error | null;
	readonly isLoading: boolean;
	readonly label: string;
	readonly onRetry: () => void;
}) {
	if (isLoading)
		return (
			<p role="status" className="p-(--density-panel-padding) text-xs text-(--color-foreground-tertiary)">
				正在加载 {label}…
			</p>
		);
	if (error)
		return (
			<div className="p-(--density-panel-padding)">
				<p role="alert" className="text-xs text-(--color-risk-critical-fg)">
					{label} unavailable · {error.message}
				</p>
				<Button className="mt-3" type="button" size="xs" variant="outline" onClick={onRetry}>
					重试
				</Button>
			</div>
		);
	return null;
}

function PageControls({
	pagination,
	onOffset,
}: {
	readonly pagination: AgentPage<unknown>["pagination"];
	readonly onOffset: (offset: number) => void;
}) {
	return (
		<div className="flex items-center justify-between border-t border-(--color-border-subtle) px-3 py-2 text-xs text-(--color-foreground-tertiary)">
			<span>
				{pagination.total} 项 · {pagination.offset + 1}–
				{Math.min(pagination.offset + pagination.limit, pagination.total)}
			</span>
			<div className="flex gap-1">
				<Button
					type="button"
					size="xs"
					variant="ghost"
					disabled={pagination.offset === 0}
					onClick={() => onOffset(Math.max(0, pagination.offset - pagination.limit))}
				>
					上一页
				</Button>
				<Button
					type="button"
					size="xs"
					variant="ghost"
					disabled={!pagination.hasMore}
					onClick={() => onOffset(pagination.offset + pagination.limit)}
				>
					下一页
				</Button>
			</div>
		</div>
	);
}

type CurrentPageSummaryItem = {
	readonly status: string;
	readonly observedAt?: string;
};

function CurrentPageSummary({
	items,
	total,
}: {
	readonly items: readonly CurrentPageSummaryItem[];
	readonly total: number;
}) {
	const statusCounts = new Map<string, number>();
	for (const item of items) statusCounts.set(item.status, (statusCounts.get(item.status) ?? 0) + 1);
	const statusText = [...statusCounts.entries()]
		.sort(([left], [right]) => left.localeCompare(right))
		.map(([status, count]) => `${status.replaceAll("_", " ")} ${count}`)
		.join(" · ");
	const timestamps = items
		.flatMap((item) => (item.observedAt ? [Date.parse(item.observedAt)] : []))
		.filter(Number.isFinite)
		.sort((left, right) => left - right);
	const timeWindow =
		timestamps.length === 0
			? null
			: `${formatDate(new Date(timestamps[0] ?? 0).toISOString())} → ${formatDate(new Date(timestamps.at(-1) ?? 0).toISOString())}`;

	return (
		<section
			aria-label="Current page summary"
			className="border-b border-(--color-border-subtle) bg-(--color-surface-strip) px-3 py-2 text-[11px] text-(--color-foreground-tertiary)"
		>
			<div className="flex flex-wrap items-center gap-x-3 gap-y-1">
				<span className="font-data">
					{items.length} / {total} loaded
				</span>
				<span>{statusText || "no status on this page"}</span>
			</div>
			{timeWindow && <p className="mt-1 font-data">time window {timeWindow}</p>}
			<p className="mt-1">仅汇总当前已加载页；不是全量账单或成本预测。</p>
		</section>
	);
}

function RunList({
	page,
	selected,
	onSelect,
}: {
	readonly page: AgentPage<AgentRunView>;
	readonly selected: string;
	readonly onSelect: (id: string) => void;
}) {
	if (page.items.length === 0)
		return (
			<p className="p-(--density-panel-padding) text-xs text-(--color-foreground-tertiary)">
				没有符合筛选的 Run。服务不可用与空列表会分别显示。
			</p>
		);
	return (
		<ul aria-label="Run history">
			{page.items.map((run) => (
				<li key={run.runId}>
					<button
						type="button"
						aria-current={selected === run.runId ? "true" : undefined}
						className={cn(
							"w-full border-b border-(--color-border-subtle) p-(--density-panel-padding) text-left transition-colors hover:bg-(--color-interaction-hover-subtle-bg) focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-(--color-focus-ring)",
							selected === run.runId && "bg-(--color-interaction-active-bg)",
						)}
						onClick={() => onSelect(run.runId)}
					>
						<div className="flex items-center justify-between gap-2">
							<span className="truncate font-data text-xs text-(--color-foreground)">{run.runId}</span>
							<StatusBadge status={run.status} />
						</div>
						<p className="mt-2 line-clamp-2 text-xs text-(--color-foreground-secondary)">
							{run.objective ?? "Objective 未在 projection 中提供"}
						</p>
						<div className="mt-2 flex justify-between font-data text-[11px] text-(--color-foreground-tertiary)">
							<span>{run.context ? `${run.context.contextType}:${run.context.contextId}` : "no context"}</span>
							<span>#{run.eventCursor}</span>
						</div>
					</button>
				</li>
			))}
		</ul>
	);
}

function SessionList({
	page,
	selected,
	onSelect,
}: {
	readonly page: AgentPage<AgentSessionView>;
	readonly selected: string;
	readonly onSelect: (id: string) => void;
}) {
	if (page.items.length === 0)
		return (
			<p className="px-3 py-2 text-xs text-(--color-foreground-tertiary)">
				没有历史 Session；新建 Run 时会创建并持久化一个 Session。
			</p>
		);
	return (
		<ul aria-label="Recent Agent sessions" className="max-h-44 overflow-y-auto">
			{page.items.map((session) => (
				<li key={session.sessionId}>
					<button
						type="button"
						aria-label={`Session ${session.sessionId}, retention ${session.retentionClass}`}
						aria-current={selected === session.sessionId ? "true" : undefined}
						className={cn(
							"flex w-full items-center justify-between gap-2 border-b border-(--color-border-subtle) px-3 py-2 text-left hover:bg-(--color-interaction-hover-subtle-bg) focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-(--color-focus-ring)",
							selected === session.sessionId && "bg-(--color-interaction-active-bg)",
						)}
						onClick={() => onSelect(session.sessionId)}
					>
						<span className="min-w-0">
							<span className="block truncate font-data text-[11px] text-(--color-foreground)">
								{session.sessionId}
							</span>
							<span className="block text-xs text-(--color-foreground-tertiary)">{formatDate(session.createdAt)}</span>
						</span>
						<Badge variant="outline">{session.retentionClass}</Badge>
					</button>
				</li>
			))}
		</ul>
	);
}

function CampaignList({
	page,
	selected,
	onSelect,
}: {
	readonly page: AgentPage<AgentCampaignView>;
	readonly selected: string;
	readonly onSelect: (id: string) => void;
}) {
	if (page.items.length === 0)
		return (
			<p className="p-(--density-panel-padding) text-xs text-(--color-foreground-tertiary)">
				没有符合筛选的 Campaign。
			</p>
		);
	return (
		<ul aria-label="Campaign history">
			{page.items.map((campaign) => (
				<li key={campaign.campaignId}>
					<button
						type="button"
						aria-current={selected === campaign.campaignId ? "true" : undefined}
						className={cn(
							"w-full border-b border-(--color-border-subtle) p-(--density-panel-padding) text-left hover:bg-(--color-interaction-hover-subtle-bg) focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-(--color-focus-ring)",
							selected === campaign.campaignId && "bg-(--color-interaction-active-bg)",
						)}
						onClick={() => onSelect(campaign.campaignId)}
					>
						<div className="flex items-center justify-between gap-2">
							<span className="truncate font-data text-xs">{campaign.campaignId}</span>
							<StatusBadge status={campaign.status} />
						</div>
						<p className="mt-2 line-clamp-2 text-xs text-(--color-foreground-secondary)">
							{campaign.objective ?? "Objective 未在 projection 中提供"}
						</p>
						<p className="mt-2 font-data text-[11px] text-(--color-foreground-tertiary)">
							{campaign.statisticalTrialCount}/{campaign.budget.candidateLimit} trials · cursor {campaign.eventCursor}
						</p>
					</button>
				</li>
			))}
		</ul>
	);
}

function ApprovalList({
	page,
	selected,
	onSelect,
}: {
	readonly page: AgentPage<AgentApprovalView>;
	readonly selected: string;
	readonly onSelect: (id: string) => void;
}) {
	if (page.items.length === 0)
		return (
			<p className="p-(--density-panel-padding) text-xs text-(--color-foreground-tertiary)">Approval Inbox 为空。</p>
		);
	return (
		<ul aria-label="Approval inbox">
			{page.items.map((approval) => {
				const status = approval.status === "pending" && isExpired(approval.expiresAt) ? "expired" : approval.status;
				return (
					<li key={approval.approvalId}>
						<button
							type="button"
							aria-current={selected === approval.approvalId ? "true" : undefined}
							className={cn(
								"w-full border-b border-(--color-border-subtle) p-(--density-panel-padding) text-left hover:bg-(--color-interaction-hover-subtle-bg) focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-(--color-focus-ring)",
								selected === approval.approvalId && "bg-(--color-interaction-active-bg)",
							)}
							onClick={() => onSelect(approval.approvalId)}
						>
							<div className="flex items-center justify-between gap-2">
								<span className="truncate font-data text-xs">{approval.approvalId}</span>
								<StatusBadge status={status} />
							</div>
							<p className="mt-2 text-xs text-(--color-foreground-secondary)">{approval.actionType}</p>
							<p className="mt-1 truncate font-data text-[11px] text-(--color-foreground-tertiary)">
								{approval.targetIdentity}
							</p>
						</button>
					</li>
				);
			})}
		</ul>
	);
}

function SpineNode({
	children,
	label,
	status = "recorded",
}: {
	readonly children: React.ReactNode;
	readonly label: string;
	readonly status?: string;
}) {
	return (
		<li className="relative grid grid-cols-[1.25rem_minmax(0,1fr)] gap-3 pb-6 last:pb-0 before:absolute before:top-5 before:bottom-0 before:left-[0.58rem] before:w-px before:bg-(--color-border) last:before:hidden">
			<span
				className="relative z-10 mt-1 h-3 w-3 rounded-full border-2 border-(--color-accent) bg-(--color-surface-2)"
				aria-hidden="true"
			/>
			<div className="min-w-0 rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-panel-base) p-(--density-panel-padding)">
				<div className="mb-2 flex items-center justify-between gap-2">
					<h3 className="text-xs font-medium tracking-wide text-(--color-foreground)">{label}</h3>
					<StatusBadge status={status} />
				</div>
				{children}
			</div>
		</li>
	);
}

function EvidenceSpine({
	run,
	onInspect,
}: {
	readonly run: AgentRunView;
	readonly onInspect: (value: InspectorSelection) => void;
}) {
	return (
		<section aria-labelledby="evidence-spine-title">
			<div className="mb-4 flex items-center justify-between">
				<div>
					<h2 id="evidence-spine-title" className="text-sm font-semibold">
						Evidence Spine
					</h2>
					<p className="text-xs text-(--color-foreground-tertiary)">
						服务端 projection，按可核对证据而非聊天气泡组织。
					</p>
				</div>
				<StatusBadge status={run.projectionState} />
			</div>
			{run.projectionState === "partial" && (
				<p
					role="alert"
					className="mb-4 rounded-(--radius-sm) border border-(--color-risk-warning-fg) bg-(--color-risk-warning-bg) p-(--density-panel-padding) text-xs text-(--color-risk-warning-fg)"
				>
					projection partial · {run.projectionReason ?? "reason not provided"}
				</p>
			)}
			<ol>
				<SpineNode label="Objective">
					<p className="text-sm text-(--color-foreground-secondary)">{run.objective ?? "内容未在展示契约中提供"}</p>
					<Meta label="objective hash" value={run.objectiveHash} mono />
				</SpineNode>
				{run.toolRecords.map((record) => (
					<SpineNode key={record.callId} label={`Tool · ${record.toolName}`}>
						<Meta label="call" value={record.callId} mono />
						<Meta label="arguments" value={record.argumentsHash} mono />
						<Meta label="result" value={record.resultHash} mono />
						{record.evidenceRefs.map((ref) => (
							<Button
								key={ref}
								type="button"
								size="xs"
								variant="link"
								onClick={() => onInspect({ kind: "evidence", value: ref })}
							>
								{ref}
							</Button>
						))}
					</SpineNode>
				))}
				{run.evidenceRefs.map((ref) => (
					<SpineNode key={ref} label="Evidence citation">
						<Button type="button" variant="link" size="xs" onClick={() => onInspect({ kind: "evidence", value: ref })}>
							{ref}
						</Button>
						<p className="mt-1 text-xs text-(--color-foreground-tertiary)">
							cutoff / snapshot 仅在 projection 提供时显示；当前不推断。
						</p>
					</SpineNode>
				))}
				{run.guardrail && (
					<SpineNode label="Guardrail" status={run.guardrail.status}>
						<Button
							type="button"
							variant="link"
							size="xs"
							onClick={() => onInspect({ kind: "guardrail", value: run.guardrail?.reasonCode ?? "not provided" })}
						>
							{run.guardrail.reasonCode ?? "reason not provided"}
						</Button>
					</SpineNode>
				)}
				{run.artifactRefs.map((ref) => (
					<SpineNode key={ref} label="Artifact">
						<Button type="button" variant="link" size="xs" onClick={() => onInspect({ kind: "artifact", value: ref })}>
							{ref}
						</Button>
					</SpineNode>
				))}
				<SpineNode label={TERMINAL_RUN.has(run.status) ? "Completion" : "Current projection"} status={run.status}>
					<p className="text-sm text-(--color-foreground-secondary)">{run.outputSummary ?? "内容未在展示契约中提供"}</p>
					{run.failureCode && <Meta label="failure" value={run.failureCode} mono />}
				</SpineNode>
			</ol>
		</section>
	);
}

function RunDetail({
	run,
	streamState,
	onCancel,
	onInspect,
}: {
	readonly run: AgentRunView;
	readonly streamState: string;
	readonly onCancel: () => void;
	readonly onInspect: (value: InspectorSelection) => void;
}) {
	const cancellable = !TERMINAL_RUN.has(run.status);
	return (
		<div className="flex h-full flex-col">
			<div className="border-b border-(--color-border-subtle) p-(--density-panel-padding)">
				<div className="flex flex-wrap items-start justify-between gap-3">
					<div>
						<p className="font-data text-xs text-(--color-foreground-tertiary)">{run.runId}</p>
						<h1 className="mt-1 text-lg font-semibold">{run.objective ?? "Run projection"}</h1>
					</div>
					<div className="flex items-center gap-2">
						<StatusBadge status={run.status} />
						{cancellable && (
							<Button
								className="hidden xl:inline-flex"
								type="button"
								size="sm"
								variant="destructive"
								onClick={onCancel}
							>
								取消 Run
							</Button>
						)}
					</div>
				</div>
				<div className="mt-3 grid gap-1 sm:grid-cols-2">
					<Meta
						label="context"
						value={run.context ? `${run.context.contextType}:${run.context.contextId}` : "none"}
						mono
					/>
					<Meta label="authority" value={run.authorityHash} mono />
					<Meta label="profile" value={run.modelProfile} />
					<Meta label="stream" value={streamState} />
					<Meta
						label="token budget"
						value={
							run.usage
								? `${formatInteger(run.usage.totalTokens)} used · ${formatInteger(Math.max(0, run.maxModelTokens - run.usage.totalTokens))} tokens remaining · ${formatInteger(run.maxModelTokens)} cap`
								: `usage pending · ${formatInteger(run.maxModelTokens)} cap`
						}
						mono
					/>
					<Meta
						label="spend budget"
						value={
							run.usage
								? `$${run.usage.modelSpendUsd} used · $${remainingDecimal(run.maxModelSpendUsd, run.usage.modelSpendUsd)} remaining · $${run.maxModelSpendUsd} cap`
								: `usage pending · $${run.maxModelSpendUsd} cap`
						}
						mono
					/>
					<Meta label="stop reason" value={run.usage?.exhaustedReason ?? run.failureCode ?? "none"} mono />
				</div>
			</div>
			<div className="min-h-0 flex-1 overflow-y-auto p-(--density-panel-padding)">
				<EvidenceSpine run={run} onInspect={onInspect} />
			</div>
		</div>
	);
}

function CampaignDetail({
	campaign,
	streamState,
	onApprove,
	onCancel,
	onInspect,
}: {
	readonly campaign: AgentCampaignView;
	readonly streamState: string;
	readonly onApprove: () => void;
	readonly onCancel: () => void;
	readonly onInspect: (value: InspectorSelection) => void;
}) {
	const cancellable = !TERMINAL_CAMPAIGN.has(campaign.status) && campaign.status !== "draft";
	return (
		<div className="flex h-full flex-col">
			<div className="border-b border-(--color-border-subtle) p-(--density-panel-padding)">
				<div className="flex flex-wrap items-start justify-between gap-3">
					<div>
						<p className="font-data text-xs text-(--color-foreground-tertiary)">{campaign.campaignId}</p>
						<h1 className="mt-1 text-lg font-semibold">{campaign.objective ?? "Campaign projection"}</h1>
					</div>
					<div className="flex gap-2">
						<StatusBadge status={campaign.status} />
						{campaign.status === "draft" && (
							<Button className="hidden xl:inline-flex" type="button" size="sm" onClick={onApprove}>
								审查并批准
							</Button>
						)}
						{cancellable && (
							<Button
								className="hidden xl:inline-flex"
								type="button"
								size="sm"
								variant="destructive"
								onClick={onCancel}
							>
								取消 Campaign
							</Button>
						)}
					</div>
				</div>
			</div>
			<div className="min-h-0 flex-1 overflow-y-auto p-(--density-panel-padding)">
				<section className="grid gap-(--section-gap) lg:grid-cols-2">
					<div className="rounded-(--radius-sm) border border-(--color-border-subtle) p-(--density-panel-padding)">
						<h2 className="text-sm font-semibold">Progress & hard budget</h2>
						<div className="mt-3 space-y-1">
							<Meta label="trials" value={`${campaign.statisticalTrialCount}/${campaign.budget.candidateLimit}`} mono />
							<Meta
								label="trials remaining"
								value={formatInteger(Math.max(0, campaign.budget.candidateLimit - campaign.statisticalTrialCount))}
								mono
							/>
							<Meta label="attempts" value={String(campaign.operationalAttemptCount)} mono />
							<Meta
								label="generations"
								value={`${campaign.noImprovementGenerations}/${campaign.budget.generationLimit}`}
								mono
							/>
							<Meta
								label="generations remaining"
								value={formatInteger(Math.max(0, campaign.budget.generationLimit - campaign.noImprovementGenerations))}
								mono
							/>
							<Meta label="wall time" value={`${campaign.budget.wallTimeLimitSeconds}s`} mono />
							<Meta
								label="model spend"
								value={`${formatInteger(campaign.usage?.modelSpendUsdMicros ?? 0)} used · ${formatInteger(Math.max(0, campaign.budget.modelSpendLimitUsdMicros - (campaign.usage?.modelSpendUsdMicros ?? 0)))} µUSD remaining · ${formatInteger(campaign.budget.modelSpendLimitUsdMicros)} cap`}
								mono
							/>
							<Meta label="stop reason" value={campaign.usage?.exhaustedReason ?? "none"} />
							<Meta label="stream" value={streamState} />
						</div>
					</div>
					<div className="rounded-(--radius-sm) border border-(--color-border-subtle) p-(--density-panel-padding)">
						<h2 className="text-sm font-semibold">Governance</h2>
						<div className="mt-3 space-y-1">
							<Meta label="search axis" value={campaign.searchAxis} />
							<Meta label="snapshot" value={campaign.sourceSnapshotId} mono />
							<Meta label="manifest hash" value={campaign.manifestHash} mono />
							<Meta label="authority" value={campaign.authorizationHash ?? "not authorized"} mono />
							<Meta label="expiry" value={formatDate(campaign.authorizationExpiresAt)} />
						</div>
					</div>
				</section>
				{campaign.projectionState === "partial" && (
					<p
						role="alert"
						className="mt-4 rounded-(--radius-sm) bg-(--color-risk-warning-bg) p-(--density-panel-padding) text-xs text-(--color-risk-warning-fg)"
					>
						projection partial · {campaign.projectionReason ?? "reason not provided"}
					</p>
				)}
				<section className="mt-4">
					<h2 className="text-sm font-semibold">Canonical manifest</h2>
					<pre className="mt-2 max-h-80 overflow-auto rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-strip) p-(--density-panel-padding) font-data text-xs whitespace-pre-wrap">
						{JSON.stringify(campaign.canonicalManifest, null, 2)}
					</pre>
				</section>
				<section className="mt-4 grid gap-3 sm:grid-cols-3">
					{campaign.evidenceRefs.map((ref) => (
						<Button
							key={ref}
							type="button"
							variant="outline"
							size="sm"
							onClick={() => onInspect({ kind: "evidence", value: ref })}
						>
							Evidence · {ref}
						</Button>
					))}
					{campaign.artifactRefs.map((ref) => (
						<Button
							key={ref}
							type="button"
							variant="outline"
							size="sm"
							onClick={() => onInspect({ kind: "artifact", value: ref })}
						>
							Artifact · {ref}
						</Button>
					))}
					{campaign.guardrail && (
						<Button
							type="button"
							variant="outline"
							size="sm"
							onClick={() => onInspect({ kind: "guardrail", value: campaign.guardrail?.reasonCode ?? "not provided" })}
						>
							Guardrail · {campaign.guardrail.status}
						</Button>
					)}
				</section>
			</div>
		</div>
	);
}

function ApprovalDetail({
	approval,
	onReview,
}: {
	readonly approval: AgentApprovalView;
	readonly onReview: () => void;
}) {
	const expired = isExpired(approval.expiresAt);
	const exactLoaded = hasExactApprovalPayload(approval);
	return (
		<div className="h-full overflow-y-auto p-(--density-panel-padding)">
			<div className="flex flex-wrap items-start justify-between gap-3">
				<div>
					<p className="font-data text-xs text-(--color-foreground-tertiary)">{approval.approvalId}</p>
					<h1 className="mt-1 text-lg font-semibold">{approval.actionType}</h1>
				</div>
				<StatusBadge status={expired && approval.status === "pending" ? "expired" : approval.status} />
			</div>
			<div className="mt-5">
				<AgentAuthorPreview approval={approval} />
			</div>
			<section className="mt-5 rounded-(--radius-sm) border border-(--color-border-subtle) p-(--density-panel-padding)">
				<h2 className="text-sm font-semibold">Exact action payload</h2>
				<pre className="mt-3 max-h-80 overflow-auto rounded-(--radius-sm) bg-(--color-surface-strip) p-(--density-panel-padding) font-data text-xs whitespace-pre-wrap">
					{JSON.stringify(approval.actionPayload, null, 2)}
				</pre>
				<div className="mt-3 space-y-1">
					<Meta label="target" value={approval.targetIdentity} mono />
					<Meta label="run" value={approval.runId} mono />
					<Meta label="action hash" value={approval.actionHash || "missing"} mono />
					<Meta label="expires" value={formatDate(approval.expiresAt)} />
					<Meta label="operator" value={approval.operatorId ?? "not decided"} />
				</div>
			</section>
			{expired && (
				<p role="alert" className="mt-4 text-xs text-(--color-risk-critical-fg)">
					approval 已过期，不能提交决定。
				</p>
			)}
			{!exactLoaded && (
				<p role="alert" className="mt-4 text-xs text-(--color-risk-critical-fg)">
					payload、hash 或 expiry 缺失，审批 fail closed。
				</p>
			)}
			<Button
				className="mt-4 hidden xl:inline-flex"
				type="button"
				disabled={!isApprovalActionable(approval)}
				onClick={onReview}
			>
				审查精确动作
			</Button>
		</div>
	);
}

function Inspector({
	selection,
	capability,
	run,
	campaign,
	approval,
	onOpenDrawer,
}: {
	readonly selection: InspectorSelection | null;
	readonly capability: ReturnType<typeof useAgentCapability>["data"];
	readonly run: AgentRunView | undefined;
	readonly campaign: AgentCampaignView | undefined;
	readonly approval: AgentApprovalView | undefined;
	readonly onOpenDrawer: () => void;
}) {
	return (
		<div className="h-full overflow-y-auto p-(--density-panel-padding)">
			<h2 className="text-sm font-semibold">Inspector</h2>
			<p className="mt-1 text-xs text-(--color-foreground-tertiary)">精确 identity、hash、cutoff 和运行边界。</p>
			<section className="mt-4 space-y-1 rounded-(--radius-sm) border border-(--color-border-subtle) p-(--density-panel-padding)">
				<h3 className="mb-2 text-xs font-medium">Runtime</h3>
				<Meta label="state" value={capability?.runtimeState ?? "unavailable"} />
				<Meta label="provider" value={capability?.provider ?? "not configured"} />
				<Meta label="profiles" value={capability?.availableProfiles.join(", ") || "none"} />
				<Meta label="checked" value={formatDate(capability?.checkedAt ?? null)} />
			</section>
			{selection ? (
				<section className="mt-4 rounded-(--radius-sm) border border-(--color-border-subtle) p-(--density-panel-padding)">
					<h3 className="text-xs font-medium">Selected {selection.kind}</h3>
					<p className="mt-2 break-all font-data text-xs text-(--color-foreground-secondary)">{selection.value}</p>
					<Button className="mt-3" type="button" size="xs" variant="outline" onClick={onOpenDrawer}>
						打开详情
					</Button>
				</section>
			) : (
				<p className="mt-4 text-xs text-(--color-foreground-tertiary)">
					从 Evidence Spine 选择 evidence、artifact 或 guardrail。
				</p>
			)}
			<section className="mt-4 space-y-1 rounded-(--radius-sm) border border-(--color-border-subtle) p-(--density-panel-padding)">
				<h3 className="mb-2 text-xs font-medium">Audit identity</h3>
				{run && (
					<>
						<Meta label="manifest" value={run.manifestHash} mono />
						<Meta label="revision" value={String(run.revision)} mono />
						<Meta label="cursor" value={String(run.eventCursor)} mono />
					</>
				)}
				{campaign && (
					<>
						<Meta label="manifest" value={campaign.manifestHash} mono />
						<Meta label="revision" value={String(campaign.revision)} mono />
						<Meta label="cursor" value={String(campaign.eventCursor)} mono />
					</>
				)}
				{approval && (
					<>
						<Meta label="approval" value={approval.approvalId} mono />
						<Meta label="action hash" value={approval.actionHash} mono />
					</>
				)}
				{!run && !campaign && !approval && (
					<p className="text-xs text-(--color-foreground-tertiary)">尚未选择 projection。</p>
				)}
			</section>
		</div>
	);
}

function normalizeSearch(
	value: AgentConsoleSearch,
): Required<Pick<AgentConsoleSearch, "tab" | "offset" | "sessionOffset">> & AgentConsoleSearch {
	return {
		...value,
		tab: value.tab ?? "runs",
		offset: Math.max(0, value.offset ?? 0),
		sessionOffset: Math.max(0, value.sessionOffset ?? 0),
	};
}

export function AgentConsolePage({
	initialSearch = {},
	search: controlledSearch,
	onSearchChange,
}: {
	readonly initialSearch?: AgentConsoleSearch;
	readonly search?: AgentConsoleSearch;
	readonly onSearchChange?: (search: AgentConsoleSearch) => void;
}) {
	const [localSearch, setLocalSearch] = useState(() => normalizeSearch(initialSearch));
	const search = normalizeSearch(controlledSearch ?? localSearch);
	const updateSearch = (patch: Partial<AgentConsoleSearch>): void => {
		const next = normalizeSearch({ ...search, ...patch });
		if (!controlledSearch) setLocalSearch(next);
		onSearchChange?.(next);
	};
	const [runCreateOpen, setRunCreateOpen] = useState(false);
	const [runCancelOpen, setRunCancelOpen] = useState(false);
	const [approvalOpen, setApprovalOpen] = useState(false);
	const [campaignDraftOpen, setCampaignDraftOpen] = useState(false);
	const [campaignApprovalOpen, setCampaignApprovalOpen] = useState(false);
	const [campaignCancelOpen, setCampaignCancelOpen] = useState(false);
	const selectionOwner = `${search.tab}:${search.selected ?? ""}`;
	const [inspectorState, setInspectorState] = useState<{
		readonly owner: string;
		readonly selection: InspectorSelection;
	} | null>(null);
	const inspectorSelection = inspectorState?.owner === selectionOwner ? inspectorState.selection : null;
	const setInspectorSelection = (selection: InspectorSelection): void => {
		setInspectorState({ owner: selectionOwner, selection });
	};
	const [drawerOpen, setDrawerOpen] = useState(false);
	const capability = useAgentCapability();
	const sessionList = useAgentSessions(search.sessionOffset);
	const runList = useAgentRuns({
		status: search.tab === "runs" && search.status ? (search.status as AgentRunStatus) : undefined,
		sessionId: search.tab === "runs" ? search.sessionId : undefined,
		contextType: search.tab === "runs" && search.contextType && search.contextId ? search.contextType : undefined,
		contextId: search.tab === "runs" && search.contextType && search.contextId ? search.contextId : undefined,
		offset: search.offset,
	});
	const campaignList = useAgentCampaigns({
		status: search.tab === "campaigns" && search.status ? (search.status as AgentCampaignStatus) : undefined,
		offset: search.offset,
	});
	const approvalList = useAgentApprovals({
		status: search.tab === "approvals" && search.status ? (search.status as AgentApprovalView["status"]) : undefined,
		offset: search.offset,
	});
	const selectedId = search.selected ?? "";
	const runDetail = useAgentRun(search.tab === "runs" ? selectedId : "");
	const campaignDetail = useAgentCampaign(search.tab === "campaigns" ? selectedId : "");
	const approvalDetail = useAgentApproval(search.tab === "approvals" ? selectedId : "");
	const run = runDetail.data;
	const campaign = campaignDetail.data;
	const approval = approvalDetail.data;
	const runStream = useAgentEventNotifications(
		"runs",
		run?.runId ?? "",
		run?.eventCursor ?? 0,
		Boolean(run && !TERMINAL_RUN.has(run.status)),
	);
	const campaignStream = useAgentEventNotifications(
		"campaigns",
		campaign?.campaignId ?? "",
		campaign?.eventCursor ?? 0,
		Boolean(campaign && !TERMINAL_CAMPAIGN.has(campaign.status)),
	);
	const activeList = search.tab === "runs" ? runList : search.tab === "campaigns" ? campaignList : approvalList;
	const runtimeMessage = capability.data?.degradationReason ?? (capability.isError ? capability.error.message : null);

	const statusOptions = useMemo(
		() =>
			search.tab === "runs"
				? ["", "queued", "running", "waiting_approval", "completed", "failed", "cancelled"]
				: search.tab === "campaigns"
					? ["", "draft", "authorized", "running", "paused", "completed", "failed", "cancelled"]
					: ["", "pending", "expired", "approved", "rejected"],
		[search.tab],
	);
	const selectedProjectionStatus = run?.status ?? campaign?.status ?? approval?.status ?? "none";
	const streamState =
		search.tab === "runs" ? runStream : search.tab === "campaigns" ? campaignStream : "not applicable";
	const runCancellable = Boolean(run && !TERMINAL_RUN.has(run.status));
	const campaignCancellable = Boolean(
		campaign && !TERMINAL_CAMPAIGN.has(campaign.status) && campaign.status !== "draft",
	);
	const hasMobileActions = runCancellable || campaign?.status === "draft" || campaignCancellable || Boolean(approval);
	const currentPageSummary =
		search.tab === "runs" && runList.data
			? {
					items: runList.data.items.map((item) => ({ status: item.status, observedAt: item.createdAt })),
					total: runList.data.pagination.total,
				}
			: search.tab === "campaigns" && campaignList.data
				? {
						items: campaignList.data.items.map((item) => ({ status: item.status })),
						total: campaignList.data.pagination.total,
					}
				: search.tab === "approvals" && approvalList.data
					? {
							items: approvalList.data.items.map((item) => ({
								status: item.status,
								observedAt: item.requestedAt,
							})),
							total: approvalList.data.pagination.total,
						}
					: null;

	return (
		<section
			data-slot="shell"
			aria-label="Agent Console"
			className="flex h-full min-h-0 flex-col overflow-y-auto bg-(--color-surface-1) text-(--color-foreground) xl:overflow-hidden"
		>
			<header
				data-slot="agent-header"
				data-info-level="l1"
				className="agent-header border-b border-(--color-border-subtle) bg-(--color-surface-2) px-4 py-3"
			>
				<div className="flex flex-wrap items-center justify-between gap-3">
					<div>
						<p className="text-[11px] font-medium tracking-[0.18em] text-(--color-platform-accent-text) uppercase">
							R5 · Governed Research
						</p>
						<h1 className="mt-1 text-lg font-semibold">Agent Console</h1>
					</div>
					<div className="flex flex-wrap items-center gap-2 text-xs">
						<StatusBadge status={capability.data?.runtimeState ?? (capability.isLoading ? "loading" : "unavailable")} />
						<span className="font-data text-(--color-foreground-secondary)">
							provider {capability.data?.provider ?? "not configured"}
						</span>
						<span className="font-data text-(--color-foreground-secondary)">
							profiles {capability.data?.availableProfiles.join("/") || "none"}
						</span>
						<span className="text-(--color-foreground-tertiary)">
							checked {formatDate(capability.data?.checkedAt ?? null)}
						</span>
					</div>
				</div>
				{runtimeMessage && (
					<p role="status" className="mt-2 text-xs text-(--color-risk-warning-fg)">
						{runtimeMessage} · 历史 projection 保持可读；新建动作已禁用。
					</p>
				)}
			</header>
			<div
				data-slot="task-toolbar"
				className="flex flex-col items-stretch gap-3 border-b border-(--color-border-subtle) bg-(--color-surface-panel-base) px-4 py-2 sm:flex-row sm:items-center sm:justify-between"
			>
				<Tabs
					value={search.tab}
					onValueChange={(value) =>
						updateSearch({
							tab: value as AgentTab,
							selected: undefined,
							sessionId: undefined,
							status: undefined,
							offset: 0,
						})
					}
				>
					<TabsList className="agent-tabs" variant="line" aria-label="Agent task views">
						<TabsTrigger value="runs">Runs</TabsTrigger>
						<TabsTrigger value="campaigns">Campaigns</TabsTrigger>
						<TabsTrigger value="approvals">Approvals</TabsTrigger>
					</TabsList>
				</Tabs>
				<div className="flex flex-wrap items-center justify-end gap-2">
					{search.tab === "runs" && (
						<>
							<label>
								<span className="sr-only">Context type</span>
								<input
									aria-label="Context type"
									className={`${SELECT_CLASS} w-28`}
									placeholder="context type"
									value={search.contextType ?? ""}
									onChange={(event) =>
										updateSearch({
											contextType: event.currentTarget.value || undefined,
											offset: 0,
											selected: undefined,
										})
									}
								/>
							</label>
							<label>
								<span className="sr-only">Context identity</span>
								<input
									aria-label="Context identity"
									className={`${SELECT_CLASS} w-40`}
									placeholder="context identity"
									value={search.contextId ?? ""}
									onChange={(event) =>
										updateSearch({ contextId: event.currentTarget.value || undefined, offset: 0, selected: undefined })
									}
								/>
							</label>
							{(search.contextType || search.contextId) && (
								<Button
									type="button"
									size="xs"
									variant="ghost"
									onClick={() =>
										updateSearch({ contextType: undefined, contextId: undefined, offset: 0, selected: undefined })
									}
								>
									清除上下文
								</Button>
							)}
						</>
					)}
					<select
						aria-label="Status filter"
						className={SELECT_CLASS}
						value={search.status ?? ""}
						onChange={(event) =>
							updateSearch({ status: event.currentTarget.value || undefined, offset: 0, selected: undefined })
						}
					>
						{statusOptions.map((status) => (
							<option key={status || "all"} value={status}>
								{status ? status.replaceAll("_", " ") : "all status"}
							</option>
						))}
					</select>
					{search.tab === "runs" && (
						<Button
							type="button"
							size="sm"
							disabled={capability.data?.enabled !== true}
							onClick={() => setRunCreateOpen(true)}
						>
							新建 Run
						</Button>
					)}
					{search.tab === "campaigns" && (
						<Button
							type="button"
							size="sm"
							disabled={capability.data?.enabled !== true}
							onClick={() => setCampaignDraftOpen(true)}
						>
							新建 Campaign
						</Button>
					)}
				</div>
			</div>
			<div
				data-slot="workspace"
				className="grid min-h-0 flex-none grid-cols-1 xl:flex-1 xl:grid-cols-[18rem_minmax(0,1fr)_20rem]"
			>
				<aside
					data-slot="source"
					aria-label="Agent projections"
					className="list-panel min-h-40 overflow-y-auto border-b border-(--color-border-subtle) bg-(--color-surface-panel-base) xl:border-r xl:border-b-0"
				>
					<div className="border-b border-(--color-border-subtle) px-3 py-2">
						<p className="text-xs font-medium">
							{search.tab === "runs"
								? "Run history"
								: search.tab === "campaigns"
									? "Campaign history"
									: "Approval Inbox"}
						</p>
						<p className="mt-1 text-[11px] text-(--color-foreground-tertiary)">
							fresh-load recovery · server pagination
						</p>
					</div>
					{currentPageSummary && (
						<CurrentPageSummary items={currentPageSummary.items} total={currentPageSummary.total} />
					)}
					{search.tab === "runs" && (
						<section aria-label="Session recovery" className="border-b border-(--color-border-subtle)">
							<div className="flex items-center justify-between px-3 py-2">
								<p className="text-[11px] font-medium text-(--color-foreground-secondary)">Recent sessions</p>
								{search.sessionId && (
									<Button
										type="button"
										size="xs"
										variant="ghost"
										onClick={() => updateSearch({ sessionId: undefined, offset: 0, selected: undefined })}
									>
										全部 Session
									</Button>
								)}
							</div>
							<PanelState
								error={sessionList.error}
								isLoading={sessionList.isLoading}
								label="sessions"
								onRetry={() => void sessionList.refetch()}
							/>
							{!sessionList.isLoading && !sessionList.error && sessionList.data && (
								<>
									<SessionList
										page={sessionList.data}
										selected={search.sessionId ?? ""}
										onSelect={(sessionId) => updateSearch({ sessionId, offset: 0, selected: undefined })}
									/>
									<PageControls
										pagination={sessionList.data.pagination}
										onOffset={(sessionOffset) => updateSearch({ sessionOffset })}
									/>
								</>
							)}
						</section>
					)}
					<PanelState
						error={activeList.error}
						isLoading={activeList.isLoading}
						label={search.tab}
						onRetry={() => void activeList.refetch()}
					/>
					{!activeList.isLoading && !activeList.error && search.tab === "runs" && runList.data && (
						<>
							<RunList page={runList.data} selected={selectedId} onSelect={(selected) => updateSearch({ selected })} />
							<PageControls
								pagination={runList.data.pagination}
								onOffset={(offset) => updateSearch({ offset, selected: undefined })}
							/>
						</>
					)}
					{!activeList.isLoading && !activeList.error && search.tab === "campaigns" && campaignList.data && (
						<>
							<CampaignList
								page={campaignList.data}
								selected={selectedId}
								onSelect={(selected) => updateSearch({ selected })}
							/>
							<PageControls
								pagination={campaignList.data.pagination}
								onOffset={(offset) => updateSearch({ offset, selected: undefined })}
							/>
						</>
					)}
					{!activeList.isLoading && !activeList.error && search.tab === "approvals" && approvalList.data && (
						<>
							<ApprovalList
								page={approvalList.data}
								selected={selectedId}
								onSelect={(selected) => updateSearch({ selected })}
							/>
							<PageControls
								pagination={approvalList.data.pagination}
								onOffset={(offset) => updateSearch({ offset, selected: undefined })}
							/>
						</>
					)}
				</aside>
				<main data-slot="main" className="main-panel min-h-[30rem] min-w-0 bg-(--color-surface-2)">
					<PanelState
						error={
							search.tab === "runs"
								? runDetail.error
								: search.tab === "campaigns"
									? campaignDetail.error
									: approvalDetail.error
						}
						isLoading={
							Boolean(selectedId) &&
							(search.tab === "runs"
								? runDetail.isLoading
								: search.tab === "campaigns"
									? campaignDetail.isLoading
									: approvalDetail.isLoading)
						}
						label="selected projection"
						onRetry={() =>
							void (search.tab === "runs"
								? runDetail.refetch()
								: search.tab === "campaigns"
									? campaignDetail.refetch()
									: approvalDetail.refetch())
						}
					/>
					{!selectedId && (
						<div className="flex h-full min-h-80 items-center justify-center p-8 text-center">
							<div>
								<p className="text-sm font-medium">
									选择一个 {search.tab === "runs" ? "Run" : search.tab === "campaigns" ? "Campaign" : "Approval"}
								</p>
								<p className="mt-2 text-xs text-(--color-foreground-tertiary)">
									URL 会保存任务视图、筛选、分页和选中 identity。
								</p>
							</div>
						</div>
					)}
					{search.tab === "runs" && run && (
						<RunDetail
							run={run}
							streamState={runStream}
							onCancel={() => setRunCancelOpen(true)}
							onInspect={setInspectorSelection}
						/>
					)}
					{search.tab === "campaigns" && campaign && (
						<CampaignDetail
							campaign={campaign}
							streamState={campaignStream}
							onApprove={() => setCampaignApprovalOpen(true)}
							onCancel={() => setCampaignCancelOpen(true)}
							onInspect={setInspectorSelection}
						/>
					)}
					{search.tab === "approvals" && approval && (
						<ApprovalDetail approval={approval} onReview={() => setApprovalOpen(true)} />
					)}
				</main>
				<aside
					data-slot="inspector"
					aria-label="Projection inspector"
					className="inspector min-h-56 border-t border-(--color-border-subtle) bg-(--color-surface-panel-base) xl:border-t-0 xl:border-l"
				>
					<Inspector
						selection={inspectorSelection}
						capability={capability.data}
						run={run}
						campaign={campaign}
						approval={approval}
						onOpenDrawer={() => setDrawerOpen(true)}
					/>
				</aside>
			</div>
			<div data-slot="mobile-controls" className="sticky bottom-0 z-10 xl:static">
				{hasMobileActions && (
					<nav
						data-slot="mobile-actions"
						aria-label="Selected task actions"
						className="flex gap-2 border-t border-(--color-border-subtle) bg-(--color-surface-panel-base) px-4 py-2 xl:hidden"
					>
						{runCancellable && (
							<Button
								className="flex-1"
								type="button"
								size="sm"
								variant="destructive"
								onClick={() => setRunCancelOpen(true)}
							>
								取消 Run
							</Button>
						)}
						{campaign?.status === "draft" && (
							<Button className="flex-1" type="button" size="sm" onClick={() => setCampaignApprovalOpen(true)}>
								审查并批准
							</Button>
						)}
						{campaignCancellable && (
							<Button
								className="flex-1"
								type="button"
								size="sm"
								variant="destructive"
								onClick={() => setCampaignCancelOpen(true)}
							>
								取消 Campaign
							</Button>
						)}
						{approval && (
							<Button
								className="flex-1"
								type="button"
								size="sm"
								disabled={!isApprovalActionable(approval)}
								onClick={() => setApprovalOpen(true)}
							>
								审查精确动作
							</Button>
						)}
					</nav>
				)}
				<footer
					data-slot="status-bar"
					role="status"
					aria-live="polite"
					className="flex flex-wrap items-center gap-(--section-gap) border-t border-(--color-border-subtle) bg-(--color-surface-0) px-4 py-2 font-data text-[11px] text-(--color-foreground-tertiary)"
				>
					<span>projection {selectedProjectionStatus}</span>
					<span>stream {streamState}</span>
					{run && (
						<>
							<span>cursor {run.eventCursor}</span>
							<span>{run.usage ? `${run.usage.totalTokens}/${run.maxModelTokens} tokens` : "usage pending"}</span>
							<span>{run.usage ? `$${run.usage.modelSpendUsd}/$${run.maxModelSpendUsd}` : "spend pending"}</span>
						</>
					)}
					{campaign && (
						<>
							<span>cursor {campaign.eventCursor}</span>
							<span>
								{campaign.statisticalTrialCount}/{campaign.budget.candidateLimit} trials
							</span>
							<span>revision {campaign.revision}</span>
						</>
					)}
				</footer>
			</div>

			<AgentRunCreateSheet
				open={runCreateOpen}
				onOpenChange={setRunCreateOpen}
				capability={capability.data}
				contextType={search.contextType}
				contextId={search.contextId}
				initialObjective={search.objective}
				onCreated={(created) => updateSearch({ tab: "runs", selected: created.runId, offset: 0 })}
			/>
			{run && <AgentRunCancelDialog open={runCancelOpen} onOpenChange={setRunCancelOpen} run={run} />}
			{approval && (
				<AgentApprovalExactActionDialog open={approvalOpen} onOpenChange={setApprovalOpen} approval={approval} />
			)}
			<AgentCampaignDraftSheet
				open={campaignDraftOpen}
				onOpenChange={setCampaignDraftOpen}
				onCreated={(created) => updateSearch({ tab: "campaigns", selected: created.campaignId, offset: 0 })}
			/>
			{campaign && (
				<>
					<AgentCampaignApprovalDialog
						open={campaignApprovalOpen}
						onOpenChange={setCampaignApprovalOpen}
						campaign={campaign}
					/>
					<AgentCampaignCancelDialog
						open={campaignCancelOpen}
						onOpenChange={setCampaignCancelOpen}
						campaign={campaign}
					/>
				</>
			)}
			{inspectorSelection?.kind === "evidence" && (
				<AgentEvidenceDetailDrawer
					open={drawerOpen}
					onOpenChange={setDrawerOpen}
					evidenceRef={inspectorSelection.value}
				/>
			)}
			{inspectorSelection?.kind === "artifact" && (
				<AgentArtifactPreviewDrawer
					open={drawerOpen}
					onOpenChange={setDrawerOpen}
					artifactRef={inspectorSelection.value}
				/>
			)}
			{inspectorSelection?.kind === "guardrail" && (
				<AgentGuardrailDetailDrawer
					open={drawerOpen}
					onOpenChange={setDrawerOpen}
					status={run?.guardrail?.status ?? campaign?.guardrail?.status ?? "unknown"}
					reasonCode={inspectorSelection.value === "not provided" ? null : inspectorSelection.value}
				/>
			)}
		</section>
	);
}
