/**
 * Review-detail 只读 section 组件（presentational）。
 *
 * 全部消费 `@/types/review` 的 camelCase view-model，绝不伪造 gate 结果——
 * `hard_review_blocked` 是后端聚合裁决，单 gate `outcome` 原样渲染。
 */
import type { ReactElement } from "react";
import { ContextSection } from "@/components/domain/context-section";
import { type BadgeVariant, StatusBadge } from "@/components/status/status-badge";
import type { ReviewPacket } from "@/types/review";
import type { SpecChange } from "@/types/strategy";

const GATE_OUTCOME_VARIANT: Record<string, BadgeVariant> = {
	pass: "healthy",
	fail: "critical",
	warn: "warning",
};

function gateVariant(outcome: string): BadgeVariant {
	return GATE_OUTCOME_VARIANT[outcome] ?? "idle";
}

/** 单行内容寻址 hash（mono + 截断展示，可复制）。 */
function HashRow({ label, hash }: { readonly label: string; readonly hash: string }): ReactElement {
	const head = hash.slice(0, 12);
	const tail = hash.slice(-8);
	return (
		<div className="flex items-center justify-between gap-2 text-xs">
			<span className="text-(--color-foreground-tertiary)">{label}</span>
			<code className="font-mono text-(--color-foreground-secondary)" title={hash}>
				{head}…{tail}
			</code>
		</div>
	);
}

interface BannerProps {
	readonly strategyId: string;
	readonly version: number;
	readonly experimentId: string;
	readonly state: string;
	readonly reviewOutcome: string;
	readonly hardReviewBlocked: boolean;
}

/** 顶部裁决条：版本身份 + 状态 + review_outcome + hard-gate 聚合裁决。 */
export function ReviewDecisionBanner({
	strategyId,
	version,
	experimentId,
	state,
	reviewOutcome,
	hardReviewBlocked,
}: BannerProps): ReactElement {
	return (
		<ContextSection title="Decision Banner">
			<div className="flex flex-wrap items-center gap-3 p-(--density-panel-padding) text-sm">
				<span className="font-medium text-(--color-foreground)">
					{strategyId} · v{version}
				</span>
				<StatusBadge variant="research" size="sm" label={`experiment ${experimentId}`} />
				<StatusBadge
					variant={hardReviewBlocked ? "critical" : "healthy"}
					size="sm"
					label={hardReviewBlocked ? "hard-gate 阻断" : "hard-gate 通过"}
				/>
				<span className="text-(--color-foreground-tertiary)">
					状态 {state} · 结论 {reviewOutcome}
				</span>
			</div>
		</ContextSection>
	);
}

/** 11 hard-gate 明细表（rule_id / layer / outcome 原样来自后端）。 */
export function HardGateList({ packet }: { readonly packet: ReviewPacket }): ReactElement {
	return (
		<ContextSection title="Hard Gates" count={packet.gateOutcomes.length}>
			<div className="flex flex-col gap-1 p-(--density-panel-padding)">
				{packet.gateOutcomes.map((gate) => (
					<div key={gate.ruleId} className="flex items-center justify-between gap-2 text-xs">
						<code className="font-mono text-(--color-foreground-secondary)">{gate.ruleId}</code>
						<div className="flex items-center gap-2">
							<span className="text-(--color-foreground-tertiary)">{gate.layer}</span>
							<StatusBadge variant={gateVariant(gate.outcome)} size="sm" label={gate.outcome} />
						</div>
					</div>
				))}
			</div>
		</ContextSection>
	);
}

/** 统计证据（内容 hash，非 metric 值）。 */
export function EvidenceHashes({ packet }: { readonly packet: ReviewPacket }): ReactElement {
	return (
		<ContextSection title="Statistical Evidence">
			<div className="flex flex-col gap-1.5 p-(--density-panel-padding)">
				<p className="text-xs text-(--color-foreground-tertiary)">Evidence only · no automatic PASS</p>
				<HashRow label="objective" hash={packet.objectivePayloadHash} />
				{packet.comparisonPayloadHash && <HashRow label="comparison" hash={packet.comparisonPayloadHash} />}
			</div>
		</ContextSection>
	);
}

/** 血统：spec/parameter/snapshot/registry hash + fold/attempt + selection-trace refs。 */
export function LineagePanel({ packet }: { readonly packet: ReviewPacket }): ReactElement {
	return (
		<ContextSection title="Lineage/Artifacts">
			<div className="flex flex-col gap-1.5 p-(--density-panel-padding)">
				<HashRow label="spec" hash={packet.specHash} />
				<HashRow label="resolved_spec" hash={packet.resolvedSpecHash} />
				<HashRow label="parameter" hash={packet.parameterHash} />
				<HashRow label="snapshot" hash={packet.snapshotHash} />
				<HashRow label="registry" hash={packet.registryHash} />
				<div className="mt-1 text-xs text-(--color-foreground-tertiary)">
					folds: {packet.foldIds.join(", ") || "—"} · attempts: {packet.attemptIds.join(", ") || "—"}
				</div>
				{packet.selectionTraceArtifactRefs.map((ref) => (
					<HashRow key={ref.artifactId} label={`trace ${ref.artifactKind}`} hash={ref.contentHash} />
				))}
			</div>
		</ContextSection>
	);
}

/** 候选入选理由。 */
export function CandidateRationale({ rationale }: { readonly rationale: string }): ReactElement {
	return (
		<ContextSection title="Candidate Rationale">
			<p className="p-(--density-panel-padding) text-sm text-(--color-foreground-secondary)">{rationale}</p>
		</ContextSection>
	);
}

/** 版本 vs parent 的 canonical spec diff。 */
export function SpecDiffView({ changes }: { readonly changes: readonly SpecChange[] }): ReactElement {
	return (
		<ContextSection title="Spec Diff" count={changes.length}>
			<div className="flex flex-col gap-1 p-(--density-panel-padding)">
				{changes.length === 0 ? (
					<span className="text-xs text-(--color-foreground-tertiary)">无字段变更（与 parent 同 canonical hash）</span>
				) : (
					changes.map((change) => (
						<div key={`${change.path}-${change.op}`} className="flex items-center gap-2 text-xs">
							<code className="font-mono text-(--color-foreground-secondary)">{change.path}</code>
							<span className="text-(--color-foreground-tertiary)">{change.op}</span>
							<span className="text-(--color-foreground-tertiary)">
								{String(change.old)} → {String(change.new)}
							</span>
						</div>
					))
				)}
			</div>
		</ContextSection>
	);
}

export function SelectionExposureEvidence({ packet }: { readonly packet: ReviewPacket }): ReactElement {
	const exposure = packet.selectionExposure;
	return (
		<ContextSection title="Selection/Exposure Evidence">
			<div className="flex flex-col gap-2 p-(--density-panel-padding) text-xs">
				<p>
					selection artifact {packet.selectionEvidenceArtifactId ?? "—"} · holdout claim {packet.holdoutClaimId ?? "—"}
				</p>
				{exposure ? (
					<>
						<p>
							{exposure.lane} · {exposure.applicability}
						</p>
						<div className="grid gap-2 sm:grid-cols-2">
							<div>
								<p className="text-(--color-foreground-tertiary)">Industry exposure</p>
								{exposure.industryWeights.map((entry) => (
									<p key={entry.key} className="font-data">
										{entry.key} {entry.weight}
									</p>
								))}
							</div>
							<div>
								<p className="text-(--color-foreground-tertiary)">Size exposure</p>
								{exposure.sizeBucketWeights.map((entry) => (
									<p key={entry.key} className="font-data">
										{entry.key} {entry.weight}
									</p>
								))}
							</div>
						</div>
						{exposure.artifactRefs.map((ref) => (
							<HashRow key={ref.artifactId} label={`exposure ${ref.artifactKind}`} hash={ref.contentHash} />
						))}
					</>
				) : (
					<p className="text-(--color-foreground-tertiary)">No selection exposure payload.</p>
				)}
			</div>
		</ContextSection>
	);
}

export function R1ImpactEvidence({ packet }: { readonly packet: ReviewPacket }): ReactElement {
	return (
		<ContextSection title="R1 Impact">
			<div className="p-(--density-panel-padding)">
				{packet.r1ImpactPayloadHash ? (
					<HashRow label="r1-impact" hash={packet.r1ImpactPayloadHash} />
				) : (
					<p className="text-xs text-(--color-foreground-tertiary)">No R1 impact evidence was persisted.</p>
				)}
			</div>
		</ContextSection>
	);
}
