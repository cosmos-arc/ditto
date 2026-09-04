import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogFooter,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import {
	useApproveAgentCampaign,
	useCancelAgentCampaign,
	useCancelAgentRun,
	useCreateAgentCampaign,
	useCreateAgentRun,
	useDecideAgentApproval,
	useValidateAgentCampaign,
} from "../hooks";
import type {
	AgentApprovalView,
	AgentCampaignManifestInput,
	AgentCampaignValidationInput,
	AgentCampaignValidationView,
	AgentCampaignView,
	AgentCapabilityView,
	AgentRunView,
} from "../types";

const INPUT_CLASS =
	"h-8 w-full rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-1) px-2 font-data text-xs text-(--color-foreground) outline-none focus-visible:border-(--color-focus-border) focus-visible:ring-3 focus-visible:ring-(--color-focus-ring)";
const TEXTAREA_CLASS = `${INPUT_CLASS} h-24 resize-y py-2`;

function isExpired(value: string | null): boolean {
	if (!value) return true;
	const timestamp = Date.parse(value);
	return !Number.isFinite(timestamp) || timestamp <= Date.now();
}

function idempotencyKey(prefix: string): string {
	return `${prefix}:${crypto.randomUUID()}`;
}

function isAwareDateTime(value: string): boolean {
	const normalized = value.trim();
	return /(?:Z|[+-]\d{2}:\d{2})$/u.test(normalized) && Number.isFinite(Date.parse(normalized));
}

function Field({
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
			<span className={mono ? "break-all font-data" : "break-words"}>{value}</span>
		</div>
	);
}

function JsonPreview({ label, value }: { readonly label: string; readonly value: unknown }) {
	return (
		<div>
			<p className="mb-1 text-xs text-(--color-foreground-tertiary)">{label}</p>
			<pre className="max-h-64 overflow-auto rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-strip) p-3 font-data text-xs whitespace-pre-wrap text-(--color-foreground-secondary)">
				{JSON.stringify(value, null, 2)}
			</pre>
		</div>
	);
}

function MutationError({ error }: { readonly error: Error | null }) {
	if (!error) return null;
	return (
		<p role="alert" className="text-xs text-(--color-risk-critical-fg)">
			{error.message}
		</p>
	);
}

export function AgentRunCreateSheet({
	capability,
	contextId = "",
	contextType = "",
	initialObjective = "",
	onCreated,
	onOpenChange,
	open,
}: {
	readonly capability: AgentCapabilityView | undefined;
	readonly contextId?: string;
	readonly contextType?: string;
	readonly initialObjective?: string;
	readonly onCreated: (run: AgentRunView) => void;
	readonly onOpenChange: (open: boolean) => void;
	readonly open: boolean;
}) {
	const create = useCreateAgentRun();
	const [objective, setObjective] = useState(initialObjective);
	const [retentionClass, setRetentionClass] = useState<"ephemeral" | "standard" | "audit">("standard");
	const [profile, setProfile] = useState<"balanced" | "quality">(capability?.defaultProfile ?? "balanced");
	const [maxTokens, setMaxTokens] = useState(12_000);
	const [maxSpend, setMaxSpend] = useState("3.00");
	const [localContextType, setLocalContextType] = useState(contextType);
	const [localContextId, setLocalContextId] = useState(contextId);
	const [decisionTime, setDecisionTime] = useState("");
	const [knowledgeCutoff, setKnowledgeCutoff] = useState("");
	const [publicationCutoff, setPublicationCutoff] = useState("");
	const [sourceSnapshotId, setSourceSnapshotId] = useState("");
	const [allowedUniverse, setAllowedUniverse] = useState("");
	const [maxOutputTokens, setMaxOutputTokens] = useState(1024);
	const profiles = capability?.availableProfiles ?? [];
	const modelExecutionAvailable = capability?.runtimeState === "available";
	const normalizedUniverse = allowedUniverse
		.split(",")
		.map((item) => item.trim())
		.filter((item, index, values) => item.length > 0 && values.indexOf(item) === index);
	useEffect(() => {
		if (!open) return;
		setObjective(initialObjective);
		setLocalContextType(contextType);
		setLocalContextId(contextId);
	}, [contextId, contextType, initialObjective, open]);
	useEffect(() => {
		if (!open || profiles.includes(profile)) return;
		const nextProfile = capability?.defaultProfile ?? profiles[0];
		if (nextProfile) setProfile(nextProfile);
	}, [capability?.defaultProfile, open, profile, profiles]);
	const canCreate =
		capability?.enabled === true &&
		profiles.includes(profile) &&
		objective.trim().length > 0 &&
		maxTokens > 0 &&
		maxOutputTokens > 0 &&
		maxOutputTokens <= maxTokens &&
		Number(maxSpend) > 0 &&
		isAwareDateTime(decisionTime) &&
		isAwareDateTime(knowledgeCutoff) &&
		isAwareDateTime(publicationCutoff) &&
		Date.parse(publicationCutoff) <= Date.parse(knowledgeCutoff) &&
		Date.parse(knowledgeCutoff) <= Date.parse(decisionTime) &&
		sourceSnapshotId.trim().length > 0 &&
		normalizedUniverse.length > 0 &&
		!create.isPending;

	function submit(executeImmediately: boolean): void {
		if (!canCreate) return;
		create.mutate(
			{
				context:
					localContextType.trim() && localContextId.trim()
						? { contextType: localContextType.trim(), contextId: localContextId.trim() }
						: null,
				idempotencyKey: idempotencyKey("agent-run"),
				executeImmediately,
				executionScope: {
					allowedUniverse: normalizedUniverse,
					decisionTime: decisionTime.trim(),
					knowledgeCutoff: knowledgeCutoff.trim(),
					maxOutputTokens,
					publicationCutoff: publicationCutoff.trim(),
					sourceSnapshotId: sourceSnapshotId.trim(),
				},
				maxModelSpendUsd: maxSpend,
				maxModelTokens: maxTokens,
				modelProfile: profile,
				objective: objective.trim(),
				retentionClass,
				sessionId: "",
			},
			{
				onSuccess: (run) => {
					onCreated(run);
					onOpenChange(false);
				},
			},
		);
	}

	return (
		<Sheet open={open} onOpenChange={(next) => !create.isPending && onOpenChange(next)}>
			<SheetContent side="right" className="w-full overflow-y-auto p-6 sm:max-w-xl">
				<SheetHeader>
					<SheetTitle>创建 governed run</SheetTitle>
					<SheetDescription>目标、稳定上下文、后端白名单 profile 与硬预算会进入 exact authority。</SheetDescription>
				</SheetHeader>
				<div className="flex flex-col gap-4 py-4">
					{capability?.enabled !== true && (
						<p
							role="alert"
							className="rounded-(--radius-sm) bg-(--color-risk-warning-bg) p-3 text-xs text-(--color-risk-warning-fg)"
						>
							runtime 当前不可创建：{capability?.degradationReason ?? "capability unavailable"}
						</p>
					)}
					{capability?.enabled === true && !modelExecutionAvailable && (
						<p
							role="alert"
							className="rounded-(--radius-sm) bg-(--color-risk-warning-bg) p-3 text-xs text-(--color-risk-warning-fg)"
						>
							模型执行不可用：{capability.degradationReason ?? "model lane unavailable"}。可先仅创建并保留 queued run。
						</p>
					)}
					<label className="text-xs text-(--color-foreground-secondary)">
						<span className="mb-1 block">Objective</span>
						<textarea
							aria-label="Run objective"
							className={TEXTAREA_CLASS}
							value={objective}
							onChange={(event) => setObjective(event.currentTarget.value)}
						/>
					</label>
					<div className="grid gap-3 sm:grid-cols-2">
						<label className="text-xs text-(--color-foreground-secondary)">
							<span className="mb-1 block">Context type</span>
							<input
								aria-label="Context type"
								className={INPUT_CLASS}
								value={localContextType}
								onChange={(event) => setLocalContextType(event.currentTarget.value)}
							/>
						</label>
						<label className="text-xs text-(--color-foreground-secondary)">
							<span className="mb-1 block">Context identity</span>
							<input
								aria-label="Context identity"
								className={INPUT_CLASS}
								value={localContextId}
								onChange={(event) => setLocalContextId(event.currentTarget.value)}
							/>
						</label>
					</div>
					<div className="grid gap-3 sm:grid-cols-2">
						<label className="text-xs text-(--color-foreground-secondary)">
							<span className="mb-1 block">Retention</span>
							<select
								aria-label="Retention class"
								className={INPUT_CLASS}
								value={retentionClass}
								onChange={(event) => setRetentionClass(event.currentTarget.value as typeof retentionClass)}
							>
								<option value="ephemeral">ephemeral</option>
								<option value="standard">standard</option>
								<option value="audit">audit</option>
							</select>
						</label>
						<label className="text-xs text-(--color-foreground-secondary)">
							<span className="mb-1 block">Model profile</span>
							<select
								aria-label="Model profile"
								className={INPUT_CLASS}
								value={profile}
								onChange={(event) => setProfile(event.currentTarget.value as typeof profile)}
							>
								{profiles.map((item) => (
									<option key={item} value={item}>
										{item}
									</option>
								))}
							</select>
						</label>
					</div>
					<section className="rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-strip) p-3">
						<div className="mb-3">
							<p className="text-xs font-medium text-(--color-foreground)">PIT 执行范围</p>
							<p className="mt-1 text-xs text-(--color-foreground-tertiary)">
								服务端会把这些时间边界、数据快照和只读工具白名单绑定为 authority。
							</p>
						</div>
						<div className="grid gap-3 sm:grid-cols-2">
							<label className="text-xs text-(--color-foreground-secondary)">
								<span className="mb-1 block">Decision time (UTC/offset)</span>
								<input
									aria-label="Decision time"
									className={INPUT_CLASS}
									placeholder="2026-08-25T08:00:00Z"
									value={decisionTime}
									onChange={(event) => setDecisionTime(event.currentTarget.value)}
								/>
							</label>
							<label className="text-xs text-(--color-foreground-secondary)">
								<span className="mb-1 block">Knowledge cutoff</span>
								<input
									aria-label="Knowledge cutoff"
									className={INPUT_CLASS}
									placeholder="2026-08-25T07:55:00Z"
									value={knowledgeCutoff}
									onChange={(event) => setKnowledgeCutoff(event.currentTarget.value)}
								/>
							</label>
							<label className="text-xs text-(--color-foreground-secondary)">
								<span className="mb-1 block">Publication cutoff</span>
								<input
									aria-label="Publication cutoff"
									className={INPUT_CLASS}
									placeholder="2026-08-25T07:50:00Z"
									value={publicationCutoff}
									onChange={(event) => setPublicationCutoff(event.currentTarget.value)}
								/>
							</label>
							<label className="text-xs text-(--color-foreground-secondary)">
								<span className="mb-1 block">Source snapshot</span>
								<input
									aria-label="Source snapshot"
									className={INPUT_CLASS}
									placeholder="snapshot-certified-..."
									value={sourceSnapshotId}
									onChange={(event) => setSourceSnapshotId(event.currentTarget.value)}
								/>
							</label>
							<label className="text-xs text-(--color-foreground-secondary)">
								<span className="mb-1 block">Allowed universe</span>
								<input
									aria-label="Allowed universe"
									className={INPUT_CLASS}
									placeholder="510300.SH, 510500.SH"
									value={allowedUniverse}
									onChange={(event) => setAllowedUniverse(event.currentTarget.value)}
								/>
							</label>
							<label className="text-xs text-(--color-foreground-secondary)">
								<span className="mb-1 block">Max output tokens</span>
								<input
									aria-label="Max output tokens"
									className={INPUT_CLASS}
									type="number"
									min={1}
									max={maxTokens}
									value={maxOutputTokens}
									onChange={(event) => setMaxOutputTokens(event.currentTarget.valueAsNumber)}
								/>
							</label>
						</div>
					</section>
					<details>
						<summary className="cursor-pointer text-xs text-(--color-foreground-secondary)">覆盖硬预算</summary>
						<div className="mt-3 grid gap-3 sm:grid-cols-2">
							<label className="text-xs text-(--color-foreground-secondary)">
								<span className="mb-1 block">Max model tokens</span>
								<input
									aria-label="Max model tokens"
									className={INPUT_CLASS}
									type="number"
									min={1}
									value={maxTokens}
									onChange={(event) => setMaxTokens(event.currentTarget.valueAsNumber)}
								/>
							</label>
							<label className="text-xs text-(--color-foreground-secondary)">
								<span className="mb-1 block">Max spend USD</span>
								<input
									aria-label="Max model spend USD"
									className={INPUT_CLASS}
									inputMode="decimal"
									value={maxSpend}
									onChange={(event) => setMaxSpend(event.currentTarget.value)}
								/>
							</label>
						</div>
					</details>
					<MutationError error={create.error} />
				</div>
				<SheetFooter className="mt-auto">
					<Button type="button" variant="outline" disabled={create.isPending} onClick={() => onOpenChange(false)}>
						取消
					</Button>
					<Button type="button" variant="outline" disabled={!canCreate} onClick={() => submit(false)}>
						仅创建
					</Button>
					<Button type="button" disabled={!canCreate || !modelExecutionAvailable} onClick={() => submit(true)}>
						创建并执行
					</Button>
				</SheetFooter>
			</SheetContent>
		</Sheet>
	);
}

export function AgentRunCancelDialog({
	onOpenChange,
	onSuccess,
	open,
	run,
}: {
	readonly onOpenChange: (open: boolean) => void;
	readonly onSuccess?: (run: AgentRunView) => void;
	readonly open: boolean;
	readonly run: AgentRunView;
}) {
	const cancel = useCancelAgentRun();
	const [confirmation, setConfirmation] = useState("");
	const phrase = `run:cancel:${run.runId}:revision:${run.revision}`;
	return (
		<Dialog open={open} onOpenChange={(next) => !cancel.isPending && onOpenChange(next)}>
			<DialogContent>
				<DialogHeader>
					<DialogTitle>取消 Run</DialogTitle>
					<DialogDescription>停止后端允许的新工具动作，并等待权威终态；不会删除已有证据。</DialogDescription>
				</DialogHeader>
				<Field label="run" value={run.runId} mono />
				<Field label="status" value={run.status} />
				<Field label="revision" value={String(run.revision)} mono />
				<label className="text-xs text-(--color-foreground-secondary)">
					<span className="mb-1 block">输入「{phrase}」</span>
					<input
						aria-label="Run cancel confirmation"
						className={INPUT_CLASS}
						value={confirmation}
						onChange={(event) => setConfirmation(event.currentTarget.value)}
					/>
				</label>
				<MutationError error={cancel.error} />
				<DialogFooter>
					<Button type="button" variant="outline" disabled={cancel.isPending} onClick={() => onOpenChange(false)}>
						返回
					</Button>
					<Button
						type="button"
						variant="destructive"
						disabled={confirmation !== phrase || cancel.isPending}
						onClick={() =>
							cancel.mutate(run, {
								onSuccess: (result) => {
									onSuccess?.(result);
									onOpenChange(false);
								},
							})
						}
					>
						确认取消
					</Button>
				</DialogFooter>
			</DialogContent>
		</Dialog>
	);
}

export function AgentApprovalExactActionDialog({
	approval,
	onOpenChange,
	open,
}: {
	readonly approval: AgentApprovalView;
	readonly onOpenChange: (open: boolean) => void;
	readonly open: boolean;
}) {
	const decide = useDecideAgentApproval();
	const [operatorId, setOperatorId] = useState("operator");
	const [reason, setReason] = useState("");
	const [confirmation, setConfirmation] = useState("");
	const phrase = `approval:${approval.actionHash}`;
	const exactLoaded =
		Object.keys(approval.actionPayload).length > 0 &&
		approval.actionHash.length === 64 &&
		approval.expiresAt.length > 0;
	const expired = isExpired(approval.expiresAt);
	const canDecide =
		exactLoaded &&
		!expired &&
		approval.status === "pending" &&
		operatorId.trim().length > 0 &&
		confirmation === phrase &&
		!decide.isPending;
	function submit(decision: "approve" | "reject"): void {
		if (!canDecide) return;
		decide.mutate(
			{
				actionHash: approval.actionHash,
				approvalId: approval.approvalId,
				decision,
				operatorId: operatorId.trim(),
				reason: reason.trim() || null,
			},
			{ onSuccess: () => onOpenChange(false) },
		);
	}
	return (
		<Dialog open={open} onOpenChange={(next) => !decide.isPending && onOpenChange(next)}>
			<DialogContent className="max-h-[90vh] max-w-2xl overflow-y-auto">
				<DialogHeader>
					<DialogTitle>审查精确动作</DialogTitle>
					<DialogDescription>决定仅绑定当前 action hash；projection 变化后必须重新审查。</DialogDescription>
				</DialogHeader>
				<Field label="target" value={approval.targetIdentity} mono />
				<Field label="action" value={approval.actionType} mono />
				<JsonPreview label="Exact action payload" value={approval.actionPayload} />
				<Field label="action hash" value={approval.actionHash || "missing"} mono />
				<Field label="expires at" value={approval.expiresAt || "missing"} mono />
				{expired && (
					<p role="alert" className="text-xs text-(--color-risk-critical-fg)">
						approval 已过期，不能提交决定。
					</p>
				)}
				{!exactLoaded && (
					<p role="alert" className="text-xs text-(--color-risk-critical-fg)">
						payload、hash 或 expiry 不完整；已 fail closed。
					</p>
				)}
				<div className="grid gap-3 sm:grid-cols-2">
					<label className="text-xs text-(--color-foreground-secondary)">
						<span className="mb-1 block">Operator</span>
						<input
							aria-label="Approval operator"
							className={INPUT_CLASS}
							value={operatorId}
							onChange={(event) => setOperatorId(event.currentTarget.value)}
						/>
					</label>
					<label className="text-xs text-(--color-foreground-secondary)">
						<span className="mb-1 block">Reason</span>
						<input
							aria-label="Approval reason"
							className={INPUT_CLASS}
							value={reason}
							onChange={(event) => setReason(event.currentTarget.value)}
						/>
					</label>
				</div>
				<label className="text-xs text-(--color-foreground-secondary)">
					<span className="mb-1 block">输入「{phrase}」</span>
					<input
						aria-label="Exact approval confirmation"
						className={INPUT_CLASS}
						value={confirmation}
						onChange={(event) => setConfirmation(event.currentTarget.value)}
					/>
				</label>
				<MutationError error={decide.error} />
				<DialogFooter>
					<Button type="button" variant="outline" disabled={!canDecide} onClick={() => submit("reject")}>
						拒绝
					</Button>
					<Button type="button" disabled={!canDecide} onClick={() => submit("approve")}>
						批准当前 hash
					</Button>
				</DialogFooter>
			</DialogContent>
		</Dialog>
	);
}

function DetailDrawer({
	children,
	description,
	onOpenChange,
	open,
	title,
}: {
	readonly children: React.ReactNode;
	readonly description: string;
	readonly onOpenChange: (open: boolean) => void;
	readonly open: boolean;
	readonly title: string;
}) {
	return (
		<Sheet open={open} onOpenChange={onOpenChange}>
			<SheetContent side="right" className="w-full overflow-y-auto p-6 sm:max-w-xl">
				<SheetHeader>
					<SheetTitle>{title}</SheetTitle>
					<SheetDescription>{description}</SheetDescription>
				</SheetHeader>
				<div className="flex flex-col gap-4 py-4">{children}</div>
			</SheetContent>
		</Sheet>
	);
}

export function AgentEvidenceDetailDrawer(props: {
	readonly evidenceRef: string;
	readonly open: boolean;
	readonly onOpenChange: (open: boolean) => void;
}) {
	return (
		<DetailDrawer
			open={props.open}
			onOpenChange={props.onOpenChange}
			title="Evidence detail"
			description="只显示 projection 提供的可核对 identity。"
		>
			<Field label="evidence" value={props.evidenceRef} mono />
			<p className="text-xs text-(--color-foreground-secondary)">
				来源正文、cutoff 或 snapshot 未在展示契约中提供时，不从 identity 或 hash 推断。
			</p>
		</DetailDrawer>
	);
}

export function AgentArtifactPreviewDrawer(props: {
	readonly artifactRef: string;
	readonly open: boolean;
	readonly onOpenChange: (open: boolean) => void;
}) {
	return (
		<DetailDrawer
			open={props.open}
			onOpenChange={props.onOpenChange}
			title="Artifact preview"
			description="权威产物引用；未提供下载合同。"
		>
			<Field label="artifact" value={props.artifactRef} mono />
			<p className="text-xs text-(--color-foreground-secondary)">内容未在展示契约中提供。</p>
		</DetailDrawer>
	);
}

export function AgentGuardrailDetailDrawer(props: {
	readonly reasonCode: string | null;
	readonly status: string;
	readonly open: boolean;
	readonly onOpenChange: (open: boolean) => void;
}) {
	return (
		<DetailDrawer
			open={props.open}
			onOpenChange={props.onOpenChange}
			title="Guardrail detail"
			description="服务端 guardrail projection。"
		>
			<Field label="status" value={props.status} />
			<Field label="reason" value={props.reasonCode ?? "not provided"} mono />
		</DetailDrawer>
	);
}

type DraftForm = {
	campaignId: string;
	objective: string;
	primaryMetricId: string;
	hypothesis: string;
	mechanism: string;
	universeHash: string;
	expectedSignal: string;
	failureCondition: string;
	baselineCandidateId: string;
	baselineCodeHash: string;
	dataRequirementHash: string;
	snapshotId: string;
	foldProtocolId: string;
	foldProtocolHash: string;
	validationObjectiveHash: string;
	costModelHash: string;
	searchSpaceHash: string;
	lineageRoot: string;
	stoppingRule: string;
	allowedTools: string;
	prohibitedActions: string;
	searchAxis: "factor_code" | "model_code" | "parameters";
};

const EMPTY_DRAFT: DraftForm = {
	campaignId: "",
	objective: "",
	primaryMetricId: "",
	hypothesis: "",
	mechanism: "",
	universeHash: "",
	expectedSignal: "",
	failureCondition: "",
	baselineCandidateId: "",
	baselineCodeHash: "",
	dataRequirementHash: "",
	snapshotId: "",
	foldProtocolId: "",
	foldProtocolHash: "",
	validationObjectiveHash: "",
	costModelHash: "",
	searchSpaceHash: "",
	lineageRoot: "",
	stoppingRule: "no_improvement_generations>=3",
	allowedTools: "factor_evidence,experiment_runner",
	prohibitedActions: "trade,deploy,write_production",
	searchAxis: "parameters",
};

function toManifest(form: DraftForm): AgentCampaignManifestInput {
	return {
		campaign_id: form.campaignId.trim(),
		objective: form.objective.trim(),
		primary_metric_id: form.primaryMetricId.trim(),
		hypothesis: {
			statement: form.hypothesis.trim(),
			mechanism: form.mechanism.trim(),
			universe_hash: form.universeHash.trim(),
			expected_signal: form.expectedSignal.trim(),
			failure_condition: form.failureCondition.trim(),
		},
		baseline_candidate: {
			candidate_id: form.baselineCandidateId.trim(),
			ordinal: 1,
			parameters: {},
			factor_code_hash: form.searchAxis === "factor_code" ? form.baselineCodeHash.trim() : null,
			model_code_hash: form.searchAxis === "model_code" ? form.baselineCodeHash.trim() : null,
			data_requirement_hashes: [form.dataRequirementHash.trim()],
		},
		experiment_plan: {
			fold_protocol_id: form.foldProtocolId.trim(),
			fold_protocol_version: 1,
			fold_protocol_hash: form.foldProtocolHash.trim(),
			snapshot_id: form.snapshotId.trim(),
			validation_objective_hash: form.validationObjectiveHash.trim(),
			cost_model_hash: form.costModelHash.trim(),
			seed: 20260818,
			purge_sessions: 5,
			embargo_sessions: 5,
		},
		budget: {
			candidate_limit: 12,
			fold_run_limit: 48,
			generation_limit: 4,
			concurrent_sandbox_limit: 2,
			wall_time_limit_seconds: 3600,
			temporary_storage_limit_bytes: 1_073_741_824,
			model_spend_limit_usd_micros: 5_000_000,
			sandbox_resource_limits: {
				cpu_count: 2,
				memory_bytes: 2_147_483_648,
				process_limit: 32,
				temporary_storage_bytes: 536_870_912,
				wall_time_seconds: 900,
				output_bytes: 10_485_760,
			},
		},
		search_axis: form.searchAxis,
		search_space_hash: form.searchSpaceHash.trim(),
		lineage_root: form.lineageRoot.trim(),
		stopping_rule: form.stoppingRule.trim(),
		allowed_tools: form.allowedTools
			.split(",")
			.map((item) => item.trim())
			.filter(Boolean),
		prohibited_actions: form.prohibitedActions
			.split(",")
			.map((item) => item.trim())
			.filter(Boolean),
	};
}

function requiredDraftValues(form: DraftForm): readonly string[] {
	return [
		form.campaignId,
		form.objective,
		form.primaryMetricId,
		form.hypothesis,
		form.mechanism,
		form.universeHash,
		form.expectedSignal,
		form.failureCondition,
		form.baselineCandidateId,
		form.dataRequirementHash,
		form.searchAxis === "parameters" ? "not-required" : form.baselineCodeHash,
		form.snapshotId,
		form.foldProtocolId,
		form.foldProtocolHash,
		form.validationObjectiveHash,
		form.costModelHash,
		form.searchSpaceHash,
		form.lineageRoot,
		form.stoppingRule,
		form.allowedTools,
		form.prohibitedActions,
	];
}

type WizardStep = 1 | 2 | 3 | 4;

function validationInput(step: WizardStep, manifest: AgentCampaignManifestInput): AgentCampaignValidationInput {
	if (step === 1) {
		return {
			step: "hypothesis",
			campaign_id: manifest.campaign_id,
			objective: manifest.objective,
			primary_metric_id: manifest.primary_metric_id,
			hypothesis: manifest.hypothesis,
		};
	}
	if (step === 2) {
		return {
			step: "experiment_plan",
			search_axis: manifest.search_axis,
			baseline_candidate: manifest.baseline_candidate,
			experiment_plan: manifest.experiment_plan,
		};
	}
	if (step === 3) {
		return {
			step: "governance",
			budget: manifest.budget,
			search_space_hash: manifest.search_space_hash,
			lineage_root: manifest.lineage_root,
			stopping_rule: manifest.stopping_rule,
			allowed_tools: manifest.allowed_tools,
			prohibited_actions: manifest.prohibited_actions,
		};
	}
	return { step: "manifest", manifest };
}

function mutationError(value: unknown): Error {
	return value instanceof Error ? value : new Error("Campaign 后端校验失败");
}

export function AgentCampaignDraftSheet({
	open,
	onOpenChange,
	onCreated,
}: {
	readonly open: boolean;
	readonly onOpenChange: (open: boolean) => void;
	readonly onCreated: (campaign: AgentCampaignView) => void;
}) {
	const create = useCreateAgentCampaign();
	const validate = useValidateAgentCampaign();
	const [step, setStep] = useState<WizardStep>(1);
	const [form, setForm] = useState<DraftForm>(EMPTY_DRAFT);
	const [validationError, setValidationError] = useState<Error | null>(null);
	const [lastValidation, setLastValidation] = useState<AgentCampaignValidationView | null>(null);
	const [finalValidation, setFinalValidation] = useState<AgentCampaignValidationView | null>(null);
	const manifest = useMemo(() => toManifest(form), [form]);
	const complete = requiredDraftValues(form).every((value) => value.trim().length > 0);
	function update<K extends keyof DraftForm>(key: K, value: DraftForm[K]): void {
		setForm((current) => ({ ...current, [key]: value }));
		setValidationError(null);
		setFinalValidation(null);
		validate.reset();
	}
	async function validateStep(): Promise<void> {
		setValidationError(null);
		try {
			const result = await validate.mutateAsync(validationInput(step, manifest));
			setLastValidation(result);
			if (step === 4) {
				setFinalValidation(result);
				return;
			}
			setStep((step + 1) as WizardStep);
		} catch (error) {
			setValidationError(mutationError(error));
		}
	}
	const fields: ReadonlyArray<{ key: keyof DraftForm; label: string }> =
		step === 1
			? [
					{ key: "campaignId", label: "Campaign identity" },
					{ key: "objective", label: "Objective" },
					{ key: "primaryMetricId", label: "Primary metric" },
					{ key: "hypothesis", label: "Hypothesis statement" },
					{ key: "mechanism", label: "Mechanism" },
					{ key: "expectedSignal", label: "Expected signal" },
					{ key: "failureCondition", label: "Failure condition" },
					{ key: "universeHash", label: "Universe hash" },
				]
			: step === 2
				? [
						{ key: "baselineCandidateId", label: "Baseline candidate" },
						{ key: "dataRequirementHash", label: "Data requirement hash" },
						...(form.searchAxis === "parameters"
							? []
							: [{ key: "baselineCodeHash" as const, label: "Baseline code hash" }]),
						{ key: "snapshotId", label: "Snapshot identity" },
						{ key: "foldProtocolId", label: "Fold protocol" },
						{ key: "foldProtocolHash", label: "Fold protocol hash" },
						{ key: "validationObjectiveHash", label: "Validation objective hash" },
						{ key: "costModelHash", label: "Cost model hash" },
					]
				: step === 3
					? [
							{ key: "searchSpaceHash", label: "Search-space hash" },
							{ key: "lineageRoot", label: "Lineage root" },
							{ key: "stoppingRule", label: "Stopping rule" },
							{ key: "allowedTools", label: "Allowed tools (comma-separated)" },
							{ key: "prohibitedActions", label: "Prohibited actions (comma-separated)" },
						]
					: [];
	return (
		<Sheet open={open} onOpenChange={(next) => !create.isPending && !validate.isPending && onOpenChange(next)}>
			<SheetContent side="right" className="w-full overflow-y-auto p-6 sm:max-w-2xl">
				<SheetHeader>
					<SheetTitle>Campaign Draft Wizard</SheetTitle>
					<SheetDescription>步骤 {step}/4 · 构造 immutable manifest；JSON 仅作为只读预览。</SheetDescription>
				</SheetHeader>
				<div className="flex flex-col gap-4 py-4">
					{step === 2 && (
						<label htmlFor="campaign-search-axis" className="text-xs text-(--color-foreground-secondary)">
							<span className="mb-1 block">唯一 search axis</span>
							<select
								id="campaign-search-axis"
								aria-label="Campaign search axis"
								className={INPUT_CLASS}
								value={form.searchAxis}
								onChange={(event) => update("searchAxis", event.currentTarget.value as DraftForm["searchAxis"])}
							>
								<option value="parameters">parameters</option>
								<option value="factor_code">factor_code</option>
								<option value="model_code">model_code</option>
							</select>
						</label>
					)}
					{fields.map((field) => (
						<label
							htmlFor={`campaign-draft-${field.key}`}
							key={field.key}
							className="text-xs text-(--color-foreground-secondary)"
						>
							<span className="mb-1 block">{field.label}</span>
							{field.key === "objective" || field.key === "hypothesis" || field.key === "mechanism" ? (
								<textarea
									id={`campaign-draft-${field.key}`}
									aria-label={field.label}
									className={TEXTAREA_CLASS}
									value={form[field.key]}
									onChange={(event) => update(field.key, event.currentTarget.value)}
								/>
							) : (
								<input
									id={`campaign-draft-${field.key}`}
									aria-label={field.label}
									className={INPUT_CLASS}
									value={form[field.key]}
									onChange={(event) => update(field.key, event.currentTarget.value)}
								/>
							)}
						</label>
					))}
					{lastValidation && (
						<p role="status" className="text-xs text-(--color-led-success)">
							{lastValidation.step} 后端校验通过
						</p>
					)}
					{step === 4 && (
						<>
							<div className="rounded-(--radius-sm) border border-(--color-border-subtle) p-3">
								<p className="text-xs font-medium">Finite hard budget</p>
								<p className="mt-1 text-xs text-(--color-foreground-secondary)">
									12 candidates · 48 folds · 4 generations · 2 concurrent sandboxes · 3600s · $5 model cap
								</p>
							</div>
							<JsonPreview label="Read-only input manifest" value={manifest} />
							{finalValidation?.canonicalManifest && (
								<JsonPreview label="Backend canonical manifest" value={finalValidation.canonicalManifest} />
							)}
							{finalValidation?.manifestHash && (
								<Field label="manifest hash" value={finalValidation.manifestHash} mono />
							)}
							<p
								role="status"
								className={complete ? "text-xs text-(--color-led-success)" : "text-xs text-(--color-risk-warning-fg)"}
							>
								{complete
									? "输入完整；创建前仍需完整 manifest 后端校验。"
									: "仍有必填 identity/hash 缺失；不能创建 draft。"}
							</p>
						</>
					)}
					<MutationError error={validationError} />
					<MutationError error={create.error} />
				</div>
				<SheetFooter className="mt-auto">
					<Button
						type="button"
						variant="outline"
						disabled={step === 1 || create.isPending || validate.isPending}
						onClick={() => setStep((value) => Math.max(1, value - 1) as WizardStep)}
					>
						上一步
					</Button>
					{step < 4 ? (
						<Button type="button" disabled={validate.isPending} onClick={() => void validateStep()}>
							{validate.isPending ? "后端校验中…" : "下一步"}
						</Button>
					) : (
						<>
							<Button
								type="button"
								variant="outline"
								disabled={!complete || validate.isPending}
								onClick={() => void validateStep()}
							>
								{validate.isPending ? "后端校验中…" : "校验完整 Manifest"}
							</Button>
							<Button
								type="button"
								disabled={
									!complete ||
									finalValidation?.step !== "manifest" ||
									finalValidation.valid !== true ||
									!finalValidation.manifestHash ||
									!finalValidation.canonicalManifest ||
									create.isPending
								}
								onClick={() =>
									create.mutate(
										{ manifest, idempotencyKey: idempotencyKey("agent-campaign") },
										{
											onSuccess: (campaign) => {
												onCreated(campaign);
												onOpenChange(false);
											},
										},
									)
								}
							>
								创建 Draft
							</Button>
						</>
					)}
				</SheetFooter>
			</SheetContent>
		</Sheet>
	);
}

function defaultCampaignAuthorizationExpiry(): string {
	const expiry = new Date(Date.now() + 24 * 60 * 60 * 1000);
	const local = new Date(expiry.getTime() - expiry.getTimezoneOffset() * 60 * 1000);
	return local.toISOString().slice(0, 16);
}

export function AgentCampaignApprovalDialog({
	campaign,
	open,
	onOpenChange,
}: {
	readonly campaign: AgentCampaignView;
	readonly open: boolean;
	readonly onOpenChange: (open: boolean) => void;
}) {
	const approve = useApproveAgentCampaign();
	const [operatorId, setOperatorId] = useState("operator");
	const [expiresAt, setExpiresAt] = useState(defaultCampaignAuthorizationExpiry);
	const [confirmation, setConfirmation] = useState("");
	const phrase = `campaign:approve:${campaign.manifestHash}`;
	const canApprove =
		campaign.status === "draft" &&
		campaign.manifestHash.length === 64 &&
		Object.keys(campaign.canonicalManifest).length > 0 &&
		operatorId.trim().length > 0 &&
		Date.parse(expiresAt) > Date.now() &&
		confirmation === phrase &&
		!approve.isPending;
	return (
		<Dialog open={open} onOpenChange={(next) => !approve.isPending && onOpenChange(next)}>
			<DialogContent className="max-h-[90vh] max-w-2xl overflow-y-auto">
				<DialogHeader>
					<DialogTitle>Campaign 精确审批</DialogTitle>
					<DialogDescription>批准 draft，不假定 campaign 已开始运行。</DialogDescription>
				</DialogHeader>
				<JsonPreview label="Canonical manifest" value={campaign.canonicalManifest} />
				<Field label="manifest hash" value={campaign.manifestHash || "missing"} mono />
				<label className="text-xs text-(--color-foreground-secondary)">
					<span className="mb-1 block">Operator</span>
					<input
						aria-label="Campaign approval operator"
						className={INPUT_CLASS}
						value={operatorId}
						onChange={(event) => setOperatorId(event.currentTarget.value)}
					/>
				</label>
				<label className="text-xs text-(--color-foreground-secondary)">
					<span className="mb-1 block">Authorization expiry</span>
					<input
						aria-label="Campaign authorization expiry"
						className={INPUT_CLASS}
						type="datetime-local"
						value={expiresAt}
						onChange={(event) => setExpiresAt(event.currentTarget.value)}
					/>
				</label>
				<label className="text-xs text-(--color-foreground-secondary)">
					<span className="mb-1 block">输入「{phrase}」</span>
					<input
						aria-label="Campaign approval confirmation"
						className={INPUT_CLASS}
						value={confirmation}
						onChange={(event) => setConfirmation(event.currentTarget.value)}
					/>
				</label>
				<MutationError error={approve.error} />
				<DialogFooter>
					<Button
						type="button"
						disabled={!canApprove}
						onClick={() =>
							approve.mutate(
								{
									campaignId: campaign.campaignId,
									manifestHash: campaign.manifestHash,
									operatorId: operatorId.trim(),
									expiresAt: new Date(expiresAt).toISOString(),
									idempotencyKey: idempotencyKey("campaign-approve"),
								},
								{ onSuccess: () => onOpenChange(false) },
							)
						}
					>
						批准当前 manifest
					</Button>
				</DialogFooter>
			</DialogContent>
		</Dialog>
	);
}

export function AgentCampaignCancelDialog({
	campaign,
	open,
	onOpenChange,
}: {
	readonly campaign: AgentCampaignView;
	readonly open: boolean;
	readonly onOpenChange: (open: boolean) => void;
}) {
	const cancel = useCancelAgentCampaign();
	const [confirmation, setConfirmation] = useState("");
	const phrase = `campaign:cancel:${campaign.authorizationHash ?? "missing"}`;
	const canCancel = Boolean(campaign.authorizationHash) && confirmation === phrase && !cancel.isPending;
	return (
		<Dialog open={open} onOpenChange={(next) => !cancel.isPending && onOpenChange(next)}>
			<DialogContent>
				<DialogHeader>
					<DialogTitle>取消 Campaign</DialogTitle>
					<DialogDescription>取消绑定 exact authorization hash，并等待后端最终 projection。</DialogDescription>
				</DialogHeader>
				<Field label="campaign" value={campaign.campaignId} mono />
				<Field label="status" value={campaign.status} />
				<Field label="authority" value={campaign.authorizationHash ?? "missing"} mono />
				<label className="text-xs text-(--color-foreground-secondary)">
					<span className="mb-1 block">输入「{phrase}」</span>
					<input
						aria-label="Campaign cancel confirmation"
						className={INPUT_CLASS}
						value={confirmation}
						onChange={(event) => setConfirmation(event.currentTarget.value)}
					/>
				</label>
				<MutationError error={cancel.error} />
				<DialogFooter>
					<Button
						type="button"
						variant="destructive"
						disabled={!canCancel}
						onClick={() => {
							if (!campaign.authorizationHash) return;
							cancel.mutate(
								{
									campaignId: campaign.campaignId,
									authorizationHash: campaign.authorizationHash,
									idempotencyKey: idempotencyKey("campaign-cancel"),
								},
								{ onSuccess: () => onOpenChange(false) },
							);
						}}
					>
						确认取消
					</Button>
				</DialogFooter>
			</DialogContent>
		</Dialog>
	);
}
